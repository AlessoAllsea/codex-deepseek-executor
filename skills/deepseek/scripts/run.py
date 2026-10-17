#!/usr/bin/env python3
"""Run a bounded DeepSeek task. Task text goes over stdin, never through a shell."""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from _runtime import DEFAULT_STATE, PROFILE, clean, environment, preflight

MAX_TASK_BYTES = 65536
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
CONTRACT = ("You are the execution agent for Codex. Complete the bounded task independently, then report changed files, checks actually run, and unresolved issues. Follow workspace AGENTS.md and preserve unrelated user changes. Never access or print secrets, credential stores, environment files, browser data, or private home configuration. Do not change permissions, sandbox, approval policies, or runtime configuration. If an action is denied or approval is unavailable, stop and report it; do not work around the restriction. Do not commit, push, deploy, send messages, install software, or spawn additional agents unless the user task explicitly authorizes it.\n\nTASK:\n")


def stop_group(proc):
    # The leader can already have exited while descendants still hold pipes.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=2)


def numeric_usage(value):
    keys = ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens", "reasoningTokens", "totalTokens")
    return {k: v for k, v in value.items() if k in keys and type(v) in (int, float) and v >= 0} if isinstance(value, dict) else {}


def execute(config, workspace, task, timeout):
    result = {"runtime": config["version"], "provider": "deepseek-official", "model": "deepseek-flash", "session_id": None, "tool_calls": [], "tool_errors": 0, "usage_by_step": [], "final": "", "errors": []}
    started = time.monotonic()
    proc = subprocess.Popen([config["cli"], "--profile", PROFILE, "--json", "-"], cwd=workspace, env=environment(config["harness_home"]), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    payload = (CONTRACT + task).encode("utf-8")
    offset = 0
    total = 0
    buffer = b""
    diagnostic_tail = b""
    timed_out = False
    protocol_error = False
    selector = selectors.DefaultSelector()
    try:
        for stream, event in ((proc.stdin, selectors.EVENT_WRITE), (proc.stdout, selectors.EVENT_READ), (proc.stderr, selectors.EVENT_READ)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, event)
        while selector.get_map() or proc.poll() is None:
            if time.monotonic() - started >= timeout:
                timed_out = True
                break
            for key, _ in selector.select(timeout=0.2):
                stream = key.fileobj
                if stream is proc.stdin:
                    try:
                        offset += os.write(key.fd, payload[offset:offset + 4096])
                    except BrokenPipeError:
                        protocol_error = True
                        offset = len(payload)
                    if offset == len(payload):
                        selector.unregister(stream)
                        stream.close()
                    continue
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(stream)
                    continue
                total += len(chunk)
                if total > MAX_OUTPUT_BYTES:
                    raise ValueError("Harness output limit exceeded. Stopped without retry.")
                if stream is proc.stderr:
                    diagnostic_tail = (diagnostic_tail + chunk)[-8192:]
                    continue
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ValueError("Expected an event object")
                    except (ValueError, UnicodeDecodeError):
                        protocol_error = True
                        continue
                    kind = event.get("type")
                    if kind == "session":
                        result["session_id"] = clean(event.get("sessionId"))
                    elif kind == "tool_call":
                        result["tool_calls"].append(clean(event.get("tool")))
                    elif kind == "tool_result" and event.get("status") == "error":
                        result["tool_errors"] += 1
                    elif kind == "status":
                        if event.get("phase") == "turn_end":
                            reason = event.get("reason")
                            result["turn_reason"] = reason.get("kind") if isinstance(reason, dict) else None
                        if "usage" in event:
                            result["usage_by_step"].append(numeric_usage(event["usage"]))
                    elif kind == "final":
                        result["final"] = clean(event.get("text", ""))
                    elif kind == "error":
                        result["errors"].append(clean(event.get("message", "Unknown Harness error")))
                    # Do not retain thinking, raw tool arguments or tool results.
        if buffer.strip():
            protocol_error = True  # The supported protocol is newline-delimited.
    finally:
        stop_group(proc)
        selector.close()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
    result.update(exit_code=proc.returncode, timed_out=timed_out, protocol_error=protocol_error, elapsed_seconds=round(time.monotonic()-started, 2))
    result["completed"] = (proc.returncode == 0 and not timed_out and not protocol_error and result.get("turn_reason") == "completed" and bool(result["final"]))
    if not result["completed"]:
        result["diagnostics"] = clean(diagnostic_tail.decode(errors="replace"))
    return result


def validate_workspace(workspace, state_dir, credentials):
    workspace = Path(workspace).expanduser().resolve(strict=True)
    home = Path.home().resolve()
    state_dir = Path(state_dir).expanduser().resolve()
    credential_dir = Path(credentials).parent.resolve()
    forbidden = {Path("/"), home, *home.parents, home/".codex", home/".dsh", home/".ssh"}
    if not workspace.is_dir() or workspace in forbidden:
        raise ValueError("Use a specific project directory, not a home, system or configuration root.")
    if workspace == state_dir or state_dir in workspace.parents or workspace in state_dir.parents:
        raise ValueError("Workspace must not contain or be inside executor state.")
    if workspace == credential_dir or credential_dir in workspace.parents or workspace in credential_dir.parents:
        raise ValueError("Workspace must not contain or be inside the managed credential directory.")
    return workspace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check local configuration; no model request")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--task-file", type=Path, help="UTF-8 task file; omit to read stdin")
    parser.add_argument("--result", type=Path, help="New private JSON file; existing paths are never overwritten")
    parser.add_argument("--timeout", type=int, default=900, help="Wall-clock seconds, 10–3600; not a spending cap")
    args = parser.parse_args(argv)
    config = preflight(args.state_dir)
    if args.check:
        print(json.dumps({"ready": True, "runtime": config["version"], "provider": "deepseek-official", "model": "deepseek-flash", "sandbox": "workspace-write", "approval": "ask", "credential_validity": "not tested"}))
        return 0
    if args.workspace is None or not 10 <= args.timeout <= 3600:
        raise ValueError("Provide --workspace and a timeout between 10 and 3600 seconds.")
    workspace = validate_workspace(args.workspace, args.state_dir, config["credentials_file"])
    if args.task_file:
        with args.task_file.open("rb") as handle:
            payload = handle.read(MAX_TASK_BYTES + 1)
    else:
        payload = sys.stdin.buffer.read(MAX_TASK_BYTES + 1)
    if len(payload) > MAX_TASK_BYTES or not payload.strip():
        raise ValueError("Task must be nonempty and at most 64 KiB. Never include credentials.")
    task = payload.decode("utf-8")
    # Reserve the result path before starting a paid task, and reject symlinks.
    handle = None
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.result, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8")
    try:
        result = execute(config, workspace, task, args.timeout)
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if handle:
            handle.write(encoded)
        print(encoded, end="")
        return 0 if result["completed"] else 1
    finally:
        if handle:
            handle.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Cancelled; executor process group stopped.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(clean(exc), file=sys.stderr)
        sys.exit(2)
