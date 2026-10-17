# Runtime reference

Use the scripts adjacent to this reference's parent SKILL.md. Resolve their absolute paths from the loaded skill location; never assume a particular username, clone directory or plugin cache layout.

## Setup (no model request)

```sh
python3 /absolute/skill/scripts/setup.py
# If discovery needs help:
python3 /absolute/skill/scripts/setup.py --dsh '/absolute/path/to/dsh'
```

Requires Python 3.9+, macOS and the official Harness CLI `0.2.1-rc.2`. CLI lookup checks PATH, then the standard macOS app location. The dependency is not bundled or installed automatically. The version gate rejects untested versions.

Default credential reference: `~/.dsh/.credentials.yaml`. Save the official API Key through Harness → Settings → Models → DeepSeek first. An account-login provider alone is insufficient. A custom store can be selected with `--credentials-file`; only the file's metadata is inspected by this plugin.

Setup creates private state under `~/.local/share/codex-deepseek-executor`, including a separate `harness/` home and `codex-executor` profile. It enables Harness's native credential provider against the existing file, pins the API endpoint and model, and fingerprints generated config. It does not copy credentials, inherit desktop/home-level Harness patches, edit global AGENTS.md, or change Codex settings. Repeating setup with identical intact state is safe. Nonempty unknown or interrupted state is never overwritten.

`setup.py` and `run.py` both accept `--state-dir /absolute/path`. When you choose a custom path, pass it consistently. After a runtime upgrade or config drift, stop and review compatibility; create fresh state after validation. Do not edit the fingerprints to suppress errors.

## Results and failures

`run.py --check` checks configuration/version/file permissions without a model call. It does not prove the API Key is valid or funded.

Normal invocation reads a nonempty UTF-8 task up to 64 KiB from `--task-file` or stdin. The result contains completion state, native session ID, tool names, protocol errors, usage reported by the provider, final text and bounded diagnostics on failure. Raw reasoning and raw tool arguments/results are omitted. A requested result file is reserved before the paid task, created with 0600 permissions and never overwritten, including symlinks.

Exit codes: 0 = native run completed with final text; 1 = failed/incomplete/timed out; 2 = startup/config/argument error; 130 = user cancellation. Even exit 0 requires Codex's independent review. An existing reserved result file may be empty if startup or execution raises an exception; inspect the process exit and stderr.

The task is passed via a nonblocking stdin pipe with no shell interpolation. Environment variables are allowlisted, timeout covers pipe transmission and execution, and the local process group is stopped on exit/cancellation. These are process controls, not a container or a defense against deliberately malicious programs that detach from the group.

Harness persists its own session logs under the isolated home. Do not publish that state or upload complete logs. Output redaction is best effort; it is not a proof that arbitrary model output contains no sensitive information.

## Permissions and cost

Harness's native macOS sandbox primarily restricts writes. Reads outside the workspace and outbound networking are not comprehensively blocked. Workspace files and allowed temporary directories can be writable. Use trusted projects, review inherited project instructions, and avoid concurrent edits. Parent Codex restrictions still apply.

Keep `approval: ask`. The shipped headless composition has no interactive approval answerer; an action requiring additional permission is rejected. Do not disable the sandbox to make a task succeed.

Default timeout is 900 seconds (allowed 10–3600); model output is capped at 8192 tokens per request. Neither is a monetary spending cap. DeepSeek token usage bills the user's DeepSeek account. Codex planning and review still use Codex allowance; no fixed savings are promised. No automatic model/provider fallback or retry loop is implemented by this wrapper. Harness itself may retry provider requests internally.
