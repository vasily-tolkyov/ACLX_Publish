# Contributing

Chinese version: [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md).

## Before You Open An Issue

Please include enough information to reproduce the routing or runtime behavior locally:

- the exact task text, or a minimal redacted equivalent
- the expected tier and the actual routed tier
- any `outputs`, `constraints`, `stop_conditions`, `expected_handoffs`, `expected_rounds`, or `child_agents` values you supplied
- the command you ran
- the relevant artifact path, prompt snippet, or benchmark/report path

Good issues usually include one of:

- a minimal fixture under `tests/fixtures/`
- a failing unit test
- a concrete mismatch between the generated prompt and the documented contract

## Pull Requests

- Keep PRs scoped to one behavior change when possible.
- Add or update tests for every routing, prompt-shaping, or artifact-contract change.
- If you change release-facing docs, keep the matching `zh-CN` mirror aligned.
- If you touch `configs/hybrid_router_map.yaml`, `src/aclx/hybrid.py`, or `src/aclx/supervisor.py`, rerun the routing and supervisor tests.
- If you intentionally change the lock-covered strategy files, update `configs/strategy_lock.json` and say why in the PR description.
- Do not commit large transient scratch directories from `artifacts/`, `tmp/`, `output/`, or `tests/formal/runs/`. Commit only the curated files staged under `benchmark/` and `docs/`.

## Local Setup

Editable install:

```powershell
python -m pip install -e .
```

Optional report extras:

```powershell
python -m pip install -e ".[formal,reports]"
```

## Test Commands

Full unit gate:

```powershell
python -m unittest discover -s tests -q
```

Targeted routing gate:

```powershell
python -m unittest tests.test_hybrid tests.test_supervisor tests.test_strategy_lock tests.test_t23_real_ab_runner -q
```

Lightweight release validation:

```powershell
python scripts/release_validation_ab.py
```

Heavy pre-release run:

```powershell
python tests/formal/run_hybrid_pre_release_heavy.py
```

Heavy general-task run:

```powershell
python tests/formal/run_hybrid_general_task_heavy.py
```

Render public bilingual reports from a general-task summary:

```powershell
python tests/formal/render_hybrid_general_task_public_reports.py benchmark/hybrid_general_task_heavy_latest.json
```

## Benchmark Changes

If your PR changes routing semantics or prompt packaging, include:

- what changed
- which tiers are expected to move
- whether the headline benchmark numbers should change
- which report you reran

Use [benchmark/summary.md](benchmark/summary.md) as the index for curated public benchmark artifacts.

## Packaging Note

- `python -m pip install -e .` is a supported public workflow.
- If you change packaging, verify the editable install still works and rerun the full unit gate.
- Wheel portability is not the primary validated release path yet; source checkout and editable install are the reference workflows.
- The packaged default-on installation path is currently Codex-specific. If you change share-pack installation behavior or host defaults, update `docs/agent_compatibility.md` and `docs/agent_compatibility.zh-CN.md`.
