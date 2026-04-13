# Security Policy

## Supported Scope

Security reports are most useful when they are specific to:

- ACL-X prompt assembly or routing behavior that can leak or corrupt visible runtime state
- artifact-contract handling, checkpoint handling, or resumability behavior
- unsafe file or process assumptions in the public scripts under `scripts/` or `tests/formal/`

## Reporting

Do not open a public issue for credential exposure, private path leakage, or exploitable behavior that could affect real environments.

Instead, prepare a private report with:

- affected file paths and functions
- the exact trigger or reproduction steps
- expected behavior vs observed behavior
- impact assessment
- any proposed mitigation

If a private channel is not available yet, open a minimal public issue that states a security report is pending without disclosing exploit details.

## Disclosure Expectations

- give maintainers reasonable time to validate and patch
- avoid publishing working exploit details before a fix is available
- include version or commit context when possible
