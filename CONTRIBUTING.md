# Contributing

Small fixes and documentation improvements are welcome. Explain the observable problem, the change, and how you verified it. Use synthetic fixtures; never attach real credentials, sessions or private source code.

Run the offline checks from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q skills tests
```

The Python runtime uses only the standard library. Mock runtime tests verify the wrapper's protocol and process behavior; they do not prove a real Harness sandbox is working. Real API checks are manual, opt-in and billable.

Before supporting another Harness version or operating system, inspect its current help, provider/credential behavior and native sandbox implementation, then verify a real coding task plus a denied write outside the test workspace. Do not remove the version/platform gate or switch to full access to make tests pass. Update the tested compatibility table and record what was actually verified.

This repository packages original integration code, a skill and an original icon. Do not vendor Harness, third-party secrets or model binaries. Their licenses and terms remain separate.
