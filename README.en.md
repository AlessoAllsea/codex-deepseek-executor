# Codex DeepSeek Executor

[中文](README.md) · [MIT License](LICENSE)

An opt-in local Codex plugin: **Codex plans and reviews; DeepSeek Harness implements, debugs and tests.** Select **DeepSeek 执行助手** in the composer, then describe your task.

The package includes its Python executor and setup tool. It has no dependency on the author's private scripts, usernames or API Key. This is an unofficial community integration, not an OpenAI or DeepSeek product.

## Compatibility

- macOS; real execution verified on Apple Silicon.
- Python 3.9+, standard library only.
- A Codex desktop/CLI version with local plugin marketplaces; CLI 0.146.0 verified.
- Official DeepSeek Harness **0.2.1-rc.2**. Untested versions are rejected.
- Provider `deepseek-official`, model `deepseek-flash`, reasoning `high`.
- Native `workspace-write` sandbox and `approval: ask` are retained.

Windows, Linux and other Harness versions are not supported by this release. Offline Linux test success does not establish real Linux sandbox support. A local execution environment is required; ordinary web/mobile chats alone are insufficient.

## Install

1. Install [Codex](https://developers.openai.com/codex/) and [official Harness](https://github.com/deepseek-ai/deepseek-harness). Save your own API Key locally in Harness → Settings → Models → DeepSeek, using the official API-key provider. Account sign-in alone is a different provider. No OpenAI API Key is required by this plugin.
2. Install the marketplace and plugin:

   ```sh
   codex plugin marketplace add 18011449431/codex-deepseek-executor
   codex plugin add deepseek-executor@codex-deepseek
   ```

3. Reopen the desktop app and start a new chat. Type `@`, select **DeepSeek 执行助手**, then describe a task. The full skill name is `$deepseek-executor:deepseek`.
4. Ask the plugin to check its local setup. If required, it can run its bundled `setup.py` without making a model request. Manual setup from a clone is also available:

   ```sh
   git clone https://github.com/18011449431/codex-deepseek-executor.git
   cd codex-deepseek-executor
   python3 skills/deepseek/scripts/setup.py
   python3 skills/deepseek/scripts/run.py --check
   ```

CLI discovery checks PATH and the standard macOS app location. Use `setup.py --dsh '/absolute/path/to/dsh'` for another installation. The default managed credential file is `~/.dsh/.credentials.yaml`; it must be owned by you with no group/other access. Use `--credentials-file` for another store. The plugin inspects file metadata, never the credential value.

Setup creates private state at `~/.local/share/codex-deepseek-executor` with an isolated Harness home and executor profile. It references the existing credential store, without copying it or editing desktop settings/global AGENTS.md. Desktop/global Harness patches are not inherited. Both scripts accept `--state-dir`; pass it consistently and keep state/credentials outside your workspace. Unknown nonempty state is never overwritten. Setup and `--check` do not test Key validity or account balance.

See the [official plugin packaging/install documentation](https://developers.openai.com/plugins/build/plugins). Organization marketplace restrictions still apply.

## Use

Example: “Plan this change, delegate its complete implementation and tests to DeepSeek, then review the diff and verify the result.” Selecting the plugin or explicitly requesting DeepSeek authorizes this workflow for the bounded task. Ordinary tasks, feature questions and status checks do not automatically trigger a paid request.

For manual execution, put scope, allowed files, constraints, acceptance criteria and test commands in a UTF-8 task file:

```sh
python3 /absolute/plugin/skills/deepseek/scripts/run.py \
  --workspace '/absolute/project' \
  --task-file '/absolute/task.txt' \
  --result '/absolute/new-result.json' \
  --timeout 900
```

Replace the placeholder paths. Tasks travel over stdin without shell interpolation and are limited to 64 KiB. Result files are created privately with mode 0600 and never overwrite existing paths or symlinks. Omit `--result` for stdout only.

JSON includes native completion state, session ID, tool names, provider-reported token usage, final text and bounded diagnostics on failure. Raw reasoning and raw tool content are omitted. Shell failure does not always increment `tool_errors`. Codex must inspect actual changes and run appropriate verification; native completion is not acceptance.

Exit codes: 0 completed with final text; 1 failed/incomplete/timed out; 2 configuration/startup/argument error; 130 cancellation. An exception may leave an empty reserved result file; check exit status and stderr.

## Limits, privacy and billing

The macOS native policy is primarily a write boundary, not complete filesystem-read/network isolation. Do not expect it to contain hostile projects. Parent Codex restrictions still apply. Extra permission requests fail when the headless runtime has no approval answerer; the plugin does not elevate automatically.

Actual execution sends the task and tool-selected project content to DeepSeek. The wrapper does not read or copy Key values. Output redaction is best effort, not a guarantee. Harness maintains its own session logs inside the isolated home; never publish state or raw sessions.

Default timeout: 900 seconds, configurable from 10–3600. Model output: 8192 tokens per request. **Neither is a financial spending cap.** DeepSeek bills its own API usage; Codex planning and review still consume Codex allowance. No fixed savings are promised. Harness may internally retry provider requests. Check [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) and [Codex usage](https://developers.openai.com/codex/pricing).

Version/config drift fails closed. Review compatibility, rerun real acceptance checks and initialize fresh state before changing supported versions; do not merely update fingerprints. Read the [runtime reference](skills/deepseek/references/runtime.md) and [security notes](SECURITY.md).

To uninstall: `codex plugin remove deepseek-executor@codex-deepseek`. Local state/logs and existing credentials are not automatically deleted. Keep the original Harness credential store and desktop settings when cleaning up executor state.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q skills tests
```

Offline tests use synthetic fixtures and make no API calls. Real model execution and native sandbox checks are separate manual, billable tests. See [CONTRIBUTING.md](CONTRIBUTING.md). Original integration code, skill and icon are MIT-licensed; upstream software/services and trademarks retain their own licenses and terms.
