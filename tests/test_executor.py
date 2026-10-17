"""Offline protocol/process tests. No model request or real credential access."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/deepseek/scripts"
sys.path.insert(0, str(SCRIPTS))
import _runtime
import run
import setup


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "project with spaces"
        self.workspace.mkdir()
        self.state = self.root / "executor-state"
        self.credentials = self.root / "private" / ".credentials.yaml"
        self.credentials.parent.mkdir()
        self.credentials.write_text("synthetic fixture only\n", encoding="utf-8")
        self.credentials.chmod(0o600)
        self.cli = self.root / "fake dsh"
        self.cli.write_text("#!" + sys.executable + "\n" + '''
import json,os,sys,time
from pathlib import Path
if '--version' in sys.argv:
    print('0.2.1-rc.2');sys.exit(0)
if '--dump-default-config' in sys.argv:
    p=Path(os.environ['DSH_HOME'])/'profiles/codex-executor'
    p.mkdir(parents=True)
    for name,contents in [('package.json','{}'),('cordis.yml','[]'),('cordis.patch.yml','[]')]:
        (p/name).write_text(contents)
    print('[]');sys.exit(0)
assert sys.argv[1:]==['--profile','codex-executor','--json','-']
assert 'DEEPSEEK_API_KEY' not in os.environ
assert 'OPENAI_API_KEY' not in os.environ
assert 'NODE_OPTIONS' not in os.environ
mode=Path('mode').read_text() if Path('mode').exists() else 'ok'
if mode=='no-read':
    Path('pid').write_text(str(os.getpid()));time.sleep(60)
task=sys.stdin.read()
Path('received.txt').write_text(task)
if mode=='bad-json':print('not-json')
print(json.dumps({'type':'session','sessionId':'synthetic-session'}))
print(json.dumps({'type':'thinking','text':'private reasoning fixture'}))
print(json.dumps({'type':'tool_call','tool':'bash','input':{'command':'private tool fixture'}}))
print(json.dumps({'type':'tool_result','status':'completed','result':'private output fixture'}))
if mode=='fail':
    print(json.dumps({'type':'status','phase':'turn_end','reason':{'kind':'error'}}))
    print(json.dumps({'type':'final','text':'incomplete'}));sys.exit(1)
print(json.dumps({'type':'status','phase':'step_end','usage':{'inputTokens':2,'outputTokens':1,'unknownSecret':'must not persist'}}))
print(json.dumps({'type':'status','phase':'turn_end','reason':{'kind':'completed'}}))
print(json.dumps({'type':'final','text':'done'}))
''', encoding="utf-8")
        self.cli.chmod(0o700)
        self.config = {"cli": str(self.cli), "version": _runtime.TESTED_VERSION, "harness_home": str(self.root/"harness"), "credentials_file": str(self.credentials)}

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, mode="ok", task="A bounded task", timeout=5):
        (self.workspace/"mode").write_text(mode, encoding="utf-8")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY":"dummy", "OPENAI_API_KEY":"dummy", "NODE_OPTIONS":"dummy"}):
            return run.execute(self.config, self.workspace, task, timeout)

    def test_stdin_is_literal_and_secrets_are_not_inherited(self):
        task="$(touch injected) `touch injected2`; literal text"
        result=self.execute(task=task)
        self.assertTrue(result["completed"])
        self.assertIn(task,(self.workspace/"received.txt").read_text())
        self.assertFalse((self.workspace/"injected").exists())
        self.assertFalse((self.workspace/"injected2").exists())

    def test_summary_excludes_raw_reasoning_and_tool_content(self):
        result=self.execute()
        serialized=json.dumps(result)
        for value in ("private reasoning fixture","private tool fixture","private output fixture","must not persist"):
            self.assertNotIn(value,serialized)
        self.assertEqual(result["tool_calls"],["bash"])
        self.assertEqual(result["usage_by_step"],[{"inputTokens":2,"outputTokens":1}])

    def test_failure_is_not_success(self):
        result=self.execute(mode="fail")
        self.assertFalse(result["completed"])
        self.assertEqual(result["exit_code"],1)

    def test_malformed_protocol_is_not_success(self):
        result=self.execute(mode="bad-json")
        self.assertFalse(result["completed"])
        self.assertTrue(result["protocol_error"])

    def test_timeout_covers_stdin_backpressure_and_stops_child(self):
        result=self.execute(mode="no-read",task="x"*65536,timeout=0.5)
        self.assertTrue(result["timed_out"])
        pid=int((self.workspace/"pid").read_text())
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_existing_result_rejected_before_model_call(self):
        task=self.root/"task.txt";task.write_text("task",encoding="utf-8")
        output=self.root/"result.json";output.write_text("preserve",encoding="utf-8")
        with patch.object(run,"preflight",return_value=self.config),patch.object(run,"execute") as execute:
            with self.assertRaises(FileExistsError):
                run.main(["--workspace",str(self.workspace),"--task-file",str(task),"--result",str(output)])
            execute.assert_not_called()
        self.assertEqual(output.read_text(),"preserve")

    def test_broken_result_symlink_rejected(self):
        task=self.root/"task.txt";task.write_text("task",encoding="utf-8")
        output=self.root/"result.json";output.symlink_to(self.root/"missing")
        with patch.object(run,"preflight",return_value=self.config),patch.object(run,"execute") as execute:
            with self.assertRaises(FileExistsError):
                run.main(["--workspace",str(self.workspace),"--task-file",str(task),"--result",str(output)])
            execute.assert_not_called()
        self.assertFalse((self.root/"missing").exists())

    def test_result_is_private(self):
        task=self.root/"task.txt";task.write_text("task",encoding="utf-8")
        output=self.root/"result.json"
        with patch.object(run,"preflight",return_value=self.config),contextlib.redirect_stdout(io.StringIO()):
            code=run.main(["--workspace",str(self.workspace),"--task-file",str(task),"--result",str(output)])
        self.assertEqual(code,0)
        self.assertEqual(output.stat().st_mode & 0o777,0o600)

    def initialize(self):
        with patch.object(_runtime,"require_platform"),patch.object(setup,"require_platform"):
            return setup.initialize(self.state,self.cli,self.credentials)

    def test_setup_references_credentials_and_is_idempotent(self):
        config=self.initialize()
        self.assertEqual(config["credentials_file"],str(self.credentials))
        self.assertEqual(self.initialize(),config)
        for path in self.state.rglob("*"):
            if path.is_file():self.assertNotIn("synthetic fixture only",path.read_text())

    def test_configuration_drift_rejected(self):
        self.initialize()
        policy=self.state/"harness/profiles/codex-executor/cordis.patch.yml"
        policy.write_text("changed",encoding="utf-8")
        with patch.object(_runtime,"require_platform"):
            with self.assertRaisesRegex(ValueError,"configuration changed"):_runtime.preflight(self.state)

    def test_unrelated_state_never_overwritten(self):
        self.state.mkdir();marker=self.state/"keep";marker.write_text("keep",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"nonempty"):self.initialize()
        self.assertEqual(marker.read_text(),"keep")

    def test_untested_version_rejected(self):
        with patch.object(_runtime.subprocess,"run",return_value=type("Result",(),{"stdout":"future-version","returncode":0})()):
            with self.assertRaisesRegex(ValueError,"Unsupported Harness"):_runtime.runtime_version(self.cli,self.root)

    def test_non_macos_rejected(self):
        with patch.object(_runtime.platform,"system",return_value="Linux"):
            with self.assertRaisesRegex(ValueError,"macOS only"):_runtime.require_platform()

    def test_broad_or_state_workspaces_rejected(self):
        self.state.mkdir()
        for workspace in (Path.home(),Path("/"),self.state):
            with self.assertRaises(ValueError):run.validate_workspace(workspace,self.state,self.credentials)


if __name__=="__main__":unittest.main(verbosity=2)
