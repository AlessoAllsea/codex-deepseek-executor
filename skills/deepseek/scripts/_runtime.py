"""Local state, policy templates and preflight checks. No credential reads."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess

TESTED_VERSION = "0.2.1-rc.2"
PROFILE = "codex-executor"
DEFAULT_STATE = Path.home() / ".local/share/codex-deepseek-executor"
APP_CLI = Path("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh")


def clean(value):
    text = str(value)
    text = re.sub(r"(?i)\b(?:sk-|Bearer\s+)[A-Za-z0-9_./+\-=]{12,}", "[REDACTED]", text)
    return re.sub(r"(?i)((?:api[_-]?key|authorization|access[_-]?token|password)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)


def environment(harness_home):
    allowed = ("HOME", "USER", "LOGNAME", "PATH", "TMPDIR", "LANG", "LC_ALL", "TZ")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["DSH_HOME"] = str(harness_home)
    env["DSH_PERMISSION_MODE"] = "workspace-write"
    return env


def require_platform():
    if platform.system() != "Darwin":
        raise ValueError("This release supports macOS only; no unsandboxed fallback is provided.")
    if not Path("/usr/bin/sandbox-exec").is_file():
        raise ValueError("macOS sandbox-exec is unavailable. Stop and review sandbox support.")


def discover_cli(explicit=None):
    candidate = explicit or shutil.which("dsh") or (str(APP_CLI) if APP_CLI.is_file() else None)
    if not candidate:
        raise ValueError("Official dsh CLI not found. Install Harness or pass --dsh /absolute/path/to/dsh.")
    cli = Path(candidate).expanduser().resolve(strict=True)
    if not cli.is_file() or not os.access(cli, os.X_OK):
        raise ValueError("The selected dsh CLI is not an executable file.")
    return cli


def runtime_version(cli, harness_home):
    result = subprocess.run([str(cli), "--version"], env=environment(harness_home), capture_output=True, text=True, timeout=10)
    version = result.stdout.strip()
    if result.returncode or version != TESTED_VERSION:
        raise ValueError("Unsupported Harness runtime. Tested version: " + TESTED_VERSION + ". Review and test newer releases before updating the version gate.")
    return version


def require_private_file(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Managed credentials/config must be an owner-only regular file: " + str(path))


def patch_text(credentials):
    return """# Generated executor policy. Credential values are never copied here.
- id: credentials
  disabled: false
  config:
    path: %s
    watch: false
- id: agent-default-model
  config:
    provider: deepseek-official
    model: deepseek-flash
    reasoningEffort: high
- id: llm-deepseek
  config:
    baseURL: https://api.deepseek.com/anthropic
    apiKeyEnv: DEEPSEEK_API_KEY
    maxTokens: 8192
- id: sandbox-policy
  config:
    mode: workspace-write
    workspaceRoot: !!js process.cwd()
- id: approval
  config:
    policy: ask
- id: tool-plugin-manager
  disabled: true
- id: session-title-llm
  disabled: true
""" % json.dumps(str(credentials), ensure_ascii=False)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def config_paths(harness_home):
    profile = harness_home / "profiles" / PROFILE
    return [profile / name for name in ("package.json", "cordis.yml", "cordis.patch.yml")] + [harness_home / "cordis.patch.yml", harness_home / ".env"]


def save_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def preflight(state_dir):
    require_platform()
    state_dir = Path(state_dir).expanduser().resolve()
    path = state_dir / "config.json"
    if not path.is_file():
        raise ValueError("Executor is not configured. Run this plugin's scripts/setup.py first.")
    require_private_file(path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != 1 or config.get("version") != TESTED_VERSION:
        raise ValueError("Unsupported local configuration. Use a new state directory after reviewing the runtime.")
    harness_home = state_dir / "harness"
    if config.get("harness_home") != str(harness_home):
        raise ValueError("State was moved; initialize a new state directory instead of editing its paths.")
    paths = config_paths(harness_home)
    expected = config.get("files", {})
    if set(expected) != {str(p) for p in paths}:
        raise ValueError("Configuration fingerprint inventory changed. Stop and review.")
    for item in paths:
        if item.is_symlink() or digest(item) != expected[str(item)]:
            raise ValueError("Executor configuration changed; review it before creating fresh state: " + str(item))
    credentials = Path(config["credentials_file"])
    require_private_file(credentials)
    if (harness_home / "profiles" / PROFILE / "cordis.patch.yml").read_text(encoding="utf-8") != patch_text(credentials):
        raise ValueError("Executor policy differs from the bundled template.")
    runtime_version(Path(config["cli"]), harness_home)
    return config
