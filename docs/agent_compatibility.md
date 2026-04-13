# Agent Compatibility

This document defines what "default hybrid installation" means in the public ACL-X release.

Chinese version: [agent_compatibility.zh-CN.md](agent_compatibility.zh-CN.md).

## Executive Summary

- The current share-pack installer enables adaptive hybrid as a default runtime policy for Codex.
- The repository also exposes reusable protocol, prompt, and runtime components that other agent hosts can integrate manually.
- The public release does not currently ship a one-click default installer for arbitrary non-Codex agent hosts.

## What Is Default-On Today

Default-on support in this repository is scoped to Codex-hosted runs.

The release package installs or renders the default policy through:

- `CODEX_HOME/AGENTS.md`
- `CODEX_HOME/config.toml`
- the vendored `aclx-runtime` skill
- the local Codex plugin cache path used by the runtime guide
- the isolated launcher `start_hybrid_codex.ps1`

The shipped share pack copies stable Codex home items into an isolated home, writes a Codex-specific `AGENTS.md`, and starts Codex with `CODEX_HOME` redirected to that isolated environment.

## What This Means Operationally

If a machine installs the share pack exactly as documented, the target Codex host can pick up this strategy as its default visible runtime policy for new sessions launched through the installed launcher.

This does not automatically make every AI agent on the machine use ACL-X hybrid by default.

## What Other Agent Hosts Can Reuse

Other hosts can still reuse the project manually.

Portable pieces include:

- ACL-X handoff encoding and decoding
- compact delegation payload generation
- hybrid prompt building
- the `t0/t1/t2/t3` routing semantics
- runtime contract wording for `Machine contract` and `Loop invariants`
- checkpoint and resumable-state conventions

The CLI surfaces several of these reusable pieces directly:

- `aclx handoff`
- `aclx handoff-json`
- `aclx delegate`
- `aclx delegate-aclx`
- `aclx hybrid-prompt`

## What Other Agent Hosts Do Not Get Automatically

For non-Codex hosts, this repository does not currently provide:

- a packaged default-on installer
- a host-specific launcher
- a host-specific persistent settings writer
- a host-specific plugin or skill installer
- a verified default policy injection path equivalent to Codex `AGENTS.md` plus `CODEX_HOME`

Examples of hosts that therefore require manual integration work include:

- generic OpenAI agent runtimes
- custom orchestration frameworks
- agent SDK wrappers
- editor-integrated assistants
- other CLI-first agent shells

## Manual Integration Requirements For Other Hosts

To adopt the strategy outside Codex, the target host needs its own wiring for at least:

1. persistent top-level instructions or system policy
2. optional skill or plugin discovery
3. delegation and handoff injection
4. reusable machine-state storage for `t2/t3`
5. checkpoint and resume prompt reconstruction
6. any launcher or environment bootstrap needed to make that policy the host default

Until that host-specific wiring exists, ACL-X should be described as "portable by manual integration" rather than "default-installed" on that host.

## Recommended Release Wording

Use wording like this in public release material:

- "Codex gets default-on installation support in the current release."
- "Other agent hosts can adopt the strategy manually, but they do not yet have a packaged default installer in this repository."
- "ACL-X hybrid is currently Codex-default, not universal-host-default."
