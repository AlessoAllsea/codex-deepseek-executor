#!/usr/bin/env python3
"""Initialize isolated Harness state using an existing managed credential file."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from _runtime import DEFAULT_STATE, PROFILE, clean, config_paths, digest, discover_cli, environment, patch_text, preflight, require_platform, require_private_file, runtime_version, save_json


def initialize(state_dir, cli, credentials):
    require_platform()
    state_dir = Path(state_dir).expanduser().resolve()
    credentials = Path(credentials).expanduser().resolve(strict=True)
    require_private_file(credentials)  # Inspect metadata only; never read key contents.
    cli = discover_cli(cli)
    harness_home = state_dir / "harness"
    version = runtime_version(cli, harness_home)
    if (state_dir / "config.json").exists():
        config = preflight(state_dir)
        if config["cli"] != str(cli) or config["credentials_file"] != str(credentials):
            raise ValueError("Existing state uses different paths. Choose a new --state-dir; nothing was overwritten.")
        return config
    if state_dir.exists() and any(state_dir.iterdir()):
        raise ValueError("State directory is nonempty or setup was interrupted. Choose a fresh --state-dir.")
    if credentials == state_dir or state_dir in credentials.parents:
        raise ValueError("Keep managed credentials outside the executor state directory.")
    state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    state_dir.chmod(0o700)
    lock = state_dir / ".setup.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        harness_home.mkdir(mode=0o700)
        result = subprocess.run([str(cli), "--profile", PROFILE, "--from-default-profile", "headless", "--dump-default-config"], cwd=state_dir, env=environment(harness_home), capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError("Harness profile initialization failed: " + clean(result.stderr[-4000:]))
        policy = harness_home / "profiles" / PROFILE / "cordis.patch.yml"
        policy.write_text(patch_text(credentials), encoding="utf-8")
        policy.chmod(0o600)
        config = {"schema": 1, "version": version, "cli": str(cli), "credentials_file": str(credentials), "harness_home": str(harness_home), "files": {str(p): digest(p) for p in config_paths(harness_home)}}
        save_json(state_dir / "config.json", config)
        preflight(state_dir)
        return config
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsh", help="Existing official dsh executable; PATH and the macOS app are checked otherwise")
    parser.add_argument("--credentials-file", type=Path, default=Path.home()/".dsh/.credentials.yaml", help="Existing managed credential file; only its path and permissions are inspected")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    config = initialize(args.state_dir, args.dsh, args.credentials_file)
    print(json.dumps({"configured": True, "state_dir": str(args.state_dir.expanduser().resolve()), "runtime": config["version"], "provider": "deepseek-official", "model": "deepseek-flash", "credential_validity": "not tested; setup makes no model request"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(clean(exc), file=sys.stderr)
        sys.exit(2)
