# ACL-X

ACL-X is a compact communication language and visible runtime boundary for AI agents.

Chinese version: [README.zh-CN.md](README.zh-CN.md).

## Validated Scope

> Hybrid is a limited optimization scheme for bounded local workflows. It is not a universal optimization scheme for arbitrary general tasks.
>
> The strategy can still be run on general tasks, but outside the validated task families in the current heavy reports, neither quality parity nor token or time savings are guaranteed.

Validated task families in the current public benchmark set:

- local file reads or summaries with strict output shape and explicit literal requirements
- one-pass review tasks with exactly one deliberate handoff and a concrete written artifact
- multi-step local code or config repairs with named files, named tests or commands, and explicit machine-readable handoff artifacts
- looped document or playbook rewrites with checkpointable structure and objective content requirements

## Latest Release Evidence

Current public release verdict: `GO`.

Latest heavy reports:

- general-task heavy run `20260413_160451`: `46.87%` aggregate token improvement, `65.31%` aggregate time improvement, `+0.75` quality delta
- pre-release heavy run `20260413_152717`: `66.35%` aggregate token improvement, `71.16%` aggregate time improvement, `+5.00` quality delta

Start with [benchmark/summary.md](benchmark/summary.md), then read the latest public report in [benchmark/hybrid_general_task_public_report_en_latest.md](benchmark/hybrid_general_task_public_report_en_latest.md).

## Launch Note

This is the first formal public release of the current ACL-X hybrid strategy.

- The release message stays quality-first: output quality must not regress on the validated suites.
- The main optimization target for the current version remains elapsed time.
- Follow-up work will continue to strengthen both time optimization and token optimization on top of the current release, with extra attention to improving token behavior beyond the already strong `t1` wins.
- Usage reports, failure cases, and benchmark comparisons are welcome through repository feedback channels.

## Which Tier To Use

| Tier | When to choose it | Bridge mode | Typical task |
| --- | --- | --- | --- |
| `t0` | Single-surface work with no real handoff, no shared machine state, and no loop | `none` | Read a file and return a strict short summary |
| `t1` | Exactly one deliberate handoff or one child-agent review pass | `bundle` | Inspect a target and write one structured review |
| `t2` | Multi-step local repair with reusable machine state, artifact contracts, or 2+ handoffs | `session` | Fix code, rerun tests, and emit a shared-state artifact |
| `t3` | Loop-heavy work with checkpoint, resume, replay, or repeated verification | `session` | Rewrite a playbook or skill while preserving loop invariants |

More routing details live in [STRATEGY.md](STRATEGY.md) and [docs/routing_decision_tree.md](docs/routing_decision_tree.md).

## Quick Start

1. Clone the repository.
2. Install the editable checkout:

   ```powershell
   python -m pip install -e .
   ```

3. If you want PDF-backed formal reports, install the optional extras:

   ```powershell
   python -m pip install -e ".[formal,reports]"
   ```

4. Run one minimal example:

   ```powershell
   python examples/t0_summary.py
   ```

5. Run the full unit gate:

   ```powershell
   python -m unittest discover -s tests -q
   ```

Supported public workflows today:

- source checkout plus `python -m unittest ...`
- editable install via `python -m pip install -e .`

## Agent Compatibility

- Default-on installation in the current release is Codex-specific.
- Other agent hosts can reuse ACL-X protocol, prompt, and runtime pieces manually, but they do not yet get a packaged default installer from this repository.
- Read [docs/agent_compatibility.md](docs/agent_compatibility.md) before describing this release as "default" for any non-Codex host.

## Benchmark Snapshot

| Suite | Run ID | Tokens | Time | Quality | Read this as |
| --- | --- | ---: | ---: | ---: | --- |
| Pre-release heavy | `20260413_152717` | `+66.35%` | `+71.16%` | `+5.00` | bounded local engineering tasks with explicit artifact contracts |
| General-task heavy | `20260413_160451` | `+46.87%` | `+65.31%` | `+0.75` | generic non-ACLX structured tasks with validators and clear closure conditions |

## Optimization Priority

- Public release messaging should treat hybrid as quality-first: the release claim requires flat or better average output quality on the validated suites.
- The main optimization target is elapsed time, not tokens.
- Token behavior is tier-dependent. Use the two heavy runs below as the public reference instead of claiming universal token savings.

| Tier | Route shape | Public message | Pre-release heavy `20260413_152717` | General-task heavy `20260413_160451` |
| --- | --- | --- | --- | --- |
| `t0` | Single-surface work with no real handoff, no shared machine state, and no loop | Exactness-first tier. Time can still improve, but tokens tend to regress on tiny fixed-format tasks. | token `-46.73%`, time `+31.89%`, quality `+5.00` | token `-12.11%`, time `+29.62%`, quality `+0.00` |
| `t1` | Exactly one deliberate handoff or one child-agent review pass | Strongest repeat aggregate token and time win. This is the clearest token-optimization tier in the current evidence set. | token `+76.08%`, time `+79.52%`, quality `+0.00` | token `+68.59%`, time `+72.69%`, quality `+0.00` |
| `t2` | Multi-step local repair with reusable machine state, artifact contracts, or 2+ handoffs | Quality preserved first, time optimized second. Token gains are workload-sensitive and should not be promised for every task. | token `+74.37%`, time `+70.96%`, quality `+15.00` | token `+3.43%`, time `+47.28%`, quality `+0.00` |
| `t3` | Loop-heavy work with checkpoint, resume, replay, or repeated verification | Quality preserved first, time optimized second. Aggregate token gains are usually smaller than `t1` and can disappear or reverse on individual tasks. | token `+25.48%`, time `+58.51%`, quality `+0.00` | token `+10.84%`, time `+59.11%`, quality `+3.00` |

These figures are tier aggregates from two heavy suites, not a guarantee that every task inside the tier will show the same token direction. In release messaging, `t1` is the only tier that currently supports a repeat large token-win claim, `t2` and `t3` should be described as time-first tiers with possible but non-guaranteed token upside, and `t0` should be described as exactness-first rather than token-first.

## Known Limitations

- The four-tier classifier is a runtime heuristic, not a universal taxonomy of task meaning or business value.
- The same request can move across tiers once it gains explicit files, shared machine state, loop checkpoints, or resume requirements.
- Mixed tasks are unstable at the boundaries, especially when acceptance checks appear during execution.
- The benchmark is not a proxy for open-ended web research, creative writing, product strategy, production operations, or workflows dominated by human tacit context.
- ACL-X in this repository governs visible runtime state, not hidden model-internal reasoning.
- `t2` and `t3` require named artifacts and explicit constraints; without them, the supervisor falls back to `t0`.

## Repository Guide

- [benchmark/summary.md](benchmark/summary.md): latest curated benchmark index and file map
- [benchmark/summary.zh-CN.md](benchmark/summary.zh-CN.md): latest Chinese benchmark index and file map
- [benchmark/hybrid_general_task_public_report_en_latest.md](benchmark/hybrid_general_task_public_report_en_latest.md): latest English public heavy report
- [benchmark/hybrid_general_task_public_report_zh_latest.md](benchmark/hybrid_general_task_public_report_zh_latest.md): latest Chinese public heavy report
- [docs/release_validation_latest.zh-CN.md](docs/release_validation_latest.zh-CN.md): latest Chinese release-validation report
- [docs/release_validation_latest.md](docs/release_validation_latest.md): canonical latest pre-release heavy report
- [docs/agent_compatibility.md](docs/agent_compatibility.md): host-compatibility and default-installation boundary
- [docs/agent_compatibility.zh-CN.md](docs/agent_compatibility.zh-CN.md): Chinese host-compatibility guide
- [docs/launch_announcement.md](docs/launch_announcement.md): launch announcement copy pack
- [docs/launch_announcement.zh-CN.md](docs/launch_announcement.zh-CN.md): Chinese launch announcement copy pack
- [STRATEGY.md](STRATEGY.md): tier triggers, bundle caps, bridge modes, and override rules
- [STRATEGY.zh-CN.md](STRATEGY.zh-CN.md): Chinese tier strategy
- [RUNTIME_GUIDE.md](RUNTIME_GUIDE.md): runtime hookup and promotion rules
- [RUNTIME_GUIDE.zh-CN.md](RUNTIME_GUIDE.zh-CN.md): Chinese runtime guide
- [CONTRIBUTING.md](CONTRIBUTING.md): local setup, tests, and benchmark refresh commands
- [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md): Chinese contributor guide
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md): release readiness checklist
- [RELEASE_CHECKLIST.zh-CN.md](RELEASE_CHECKLIST.zh-CN.md): Chinese release readiness checklist
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): collaboration expectations
- [SECURITY.md](SECURITY.md): security reporting process
