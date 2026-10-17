# Security and privacy

Do not open a public issue containing API Keys, private project code, raw Harness sessions, local state or personal paths. Report sensitive problems through the repository's private vulnerability reporting feature if it is enabled; otherwise contact the maintainer through a private channel listed on their GitHub profile. If no private channel is available, open only a non-sensitive request for one.

The plugin never reads credential values or copies them into its state. It references an existing owner-only Harness managed credential file and lets Harness resolve it. The package contains no keys. Plugin setup and `--check` do not make model requests. Actual task execution sends the task and tool-selected project content to DeepSeek, subject to that service's terms and settings.

The fixed `workspace-write` policy is primarily a write boundary. It does not comprehensively confine filesystem reads or outbound network traffic. No claim of complete isolation is made. Do not run untrusted projects or instructions expecting this plugin to contain malicious code.

The wrapper pins a reviewed Harness version and fingerprints generated configuration. These checks detect accidental drift; they are not a cryptographic integrity guarantee for the runtime or for a local user who can edit both state and code. Model-output redaction is best effort. Harness maintains its own session logs, which may include project content and tool results. Keep all local state private.

No protections are disabled automatically. Stop on sandbox or approval failures. Upstream Harness can retry API requests internally; time/output limits are not financial caps.
