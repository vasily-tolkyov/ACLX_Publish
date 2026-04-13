# Hybrid Pre-Release Heavy Test Report

- Run ID: `20260413_152717`
- Generated at: `2026-04-13 16:04:35`
- Formal run root: `D:\ACLX_Publish\tests\formal\runs\hybrid_pre_release_heavy_20260413_152717`
- Gate tests passed: `True`
- Strategy lock clean: `True`
- Release recommendation: `GO`


## Executive Scope and Caveats

Hybrid is a limited optimization scheme for bounded local workflows. It is not a universal optimization scheme for arbitrary general tasks.
The strategy can still be run on general tasks, but outside the validated task families in this report, neither quality parity nor token or time savings are guaranteed.
This report should therefore be read as a release-facing estimate for a narrow operating range, not as a guaranteed average for tasks of any type and any complexity.

## Method

This run compares a natural-language baseline against the current adaptive hybrid strategy.
The suite contains 12 local heavy tasks: four tiers and three groups per tier.
Token consumption uses Codex-reported total tokens when available, and falls back to estimated prompt plus visible output tokens only when the reported count is missing.
Quality uses task-specific validators and is normalized to a 0-100 score.
The summary also tracks contract family, adapter family, validator type, resumability coverage, and exactness preservation coverage so the report does not overfit to tier labels alone.

## Classification Limits

- The four-tier hybrid classification is a routing heuristic driven by runtime structure, not a universal taxonomy of task meaning or business value.
- The same user-facing request can fall into different tiers once it gains explicit files, reusable handoff state, loop checkpoints, or resume requirements.
- Mixed tasks are especially unstable at the boundaries. A task that begins as a short read-only request can become a multi-step repair or a loop-heavy workflow as soon as new acceptance checks appear during execution.
- The classification is weakest when the real success criteria live outside the prompt, outside the local workspace, or outside validator-checkable artifacts.

## Recommended Task Families

- Local file reads or summaries with strict output shape and explicit literal requirements.
- One-pass review tasks with exactly one deliberate handoff and a concrete written artifact.
- Multi-step local code or config repairs with named files, named tests or commands, and explicit machine-readable handoff artifacts.
- Looped document or playbook rewrites that have checkpointable structure and objective content requirements.

## Task Families That Should Not Use This Report As a Proxy

- Open-ended web research, product strategy, or exploratory planning where scope changes during the run.
- Creative generation, taste-driven writing, or tasks whose quality is mostly subjective rather than validator-based.
- Production operations, remote systems work, or workflows dominated by network latency, approvals, or external services.
- Human-in-the-loop tasks where missing tacit context matters more than the prompt contract or local artifact discipline.

## Release Messaging Guidance

- Hybrid should be described as quality-first: the release claim requires flat or better average quality on the validated suites.
- The main optimization target is elapsed time.
- Token behavior is tier-sensitive. Use both heavy runs below as the public reference rather than claiming universal token savings.

| Tier | Route shape | Public message | Pre-release heavy `20260413_152717` | General-task heavy `20260413_160451` |
| --- | --- | --- | --- | --- |
| `t0` | Single-surface work with no real handoff, no shared machine state, and no loop | Exactness-first tier. Time can improve, but tokens tend to regress on tiny fixed-format tasks. | token `-46.73%`, time `+31.89%`, quality `+5.00` | token `-12.11%`, time `+29.62%`, quality `+0.00` |
| `t1` | Exactly one deliberate handoff or one child-agent review pass | Strongest repeat aggregate token and time win in the current evidence set. | token `+76.08%`, time `+79.52%`, quality `+0.00` | token `+68.59%`, time `+72.69%`, quality `+0.00` |
| `t2` | Multi-step local repair with reusable machine state, artifact contracts, or 2+ handoffs | Quality preserved first, time optimized second. Token gains are workload-sensitive and should not be promised for every task. | token `+74.37%`, time `+70.96%`, quality `+15.00` | token `+3.43%`, time `+47.28%`, quality `+0.00` |
| `t3` | Loop-heavy work with checkpoint, resume, replay, or repeated verification | Quality preserved first, time optimized second. Aggregate token gains are usually smaller than `t1` and can disappear or reverse on individual tasks. | token `+25.48%`, time `+58.51%`, quality `+0.00` | token `+10.84%`, time `+59.11%`, quality `+3.00` |

These figures are tier aggregates from two heavy suites, not a guarantee that every task inside a tier will show the same token direction.

## Why T0 Can Show Negative Optimization

In this formal run, T0 as a tier shows -46.73% token optimization, 31.89% time optimization, and average quality improving from 95.00 to 100.00.
The negative token outliers are Three-line release notes summary (-80.30%), Routing threshold brief (-69.70%).
The main cause is fixed hybrid overhead. On tiny read-only tasks, routing wrappers, output-preservation guards, and a stricter prompt contract can cost more tokens than the task itself would otherwise consume.
Operationally, this does not indicate a quality failure in the current run. The T0 hybrid outputs matched or exceeded baseline quality, but efficiency became unreliable because the task bodies were too small to amortize the extra control cost.
Practical implication: use hybrid on T0-sized work when format fidelity, literal retention, or consistency matters. Do not expect reliable token savings on very small tasks.

## Task Selection

| Tier | Group | Title | Representative Task Description |
| --- | ---: | --- | --- |
| t0 | 1 | Three-line release notes summary | Read a short release-notes file and return exactly three non-empty lines. The answer must cite the source file path and include two named release facts, so this task represents a tiny read-only extraction with strict wording requirements. |
| t0 | 2 | Routing threshold brief | Read a small routing-threshold reference and produce a fixed-format brief that cites the source path and the key threshold facts. This models a tiny configuration lookup where format fidelity matters more than synthesis depth. |
| t0 | 3 | Operator note brief | Read a short operator note and extract a three-line brief with the required path and two explicit facts. This represents a very small read-only summarization task with literal evidence requirements. |
| t1 | 1 | Empty-input bug review | Inspect a small Python function that fails on empty input, perform exactly one reviewer handoff, and write a structured review report with a decision and evidence. This simulates a lightweight one-pass review workflow. |
| t1 | 2 | Zero-sample bug review | Inspect a latency helper that breaks when the sample count is zero, perform exactly one reviewer handoff, and deliver a structured review note. This tests a single coordination step without reusable runtime state. |
| t1 | 3 | Missing-route bug review | Inspect a route selector that crashes on unknown keys, perform exactly one reviewer handoff, and write a structured review result. This is another single-handoff review task with concrete evidence requirements. |
| t2 | 1 | Shared pipeline repair | Repair a local deduplication pipeline, run the named unit-test command, write a shared-state artifact for the next phase, and produce review notes. This represents a multi-step engineering fix that has both code and handoff artifacts. |
| t2 | 2 | Reviewer queue repair | Fix a queue-normalization bug, run the named unit-test command, write the shared-state handoff artifact, and leave a structured review note. This models a multi-step local fix with reusable machine-readable state. |
| t2 | 3 | Stage plan repair | Restore a missing first stage in a local deployment-plan workflow, rerun unit tests, write the shared-state artifact for the next phase, and produce review notes. This is a multi-step repair where task-contract fidelity matters because several artifacts must stay aligned. |
| t3 | 1 | Review loop playbook rewrite | Rewrite a review playbook so each review cycle stays evidence-first, roles remain explicit, scope boundaries are preserved, and checkpoint notes keep the loop state recoverable. This is a loop-heavy document task rather than a code-fix task. |
| t3 | 2 | Release signoff handbook rewrite | Rewrite a release-signoff handbook so blocker-first checkpoints remain intact before final signoff and the document can be resumed cleanly from saved progress notes. This represents a loop-heavy procedural document task. |
| t3 | 3 | Resume handoff guide rewrite | Rewrite a resume-and-handoff guide so it preserves latest-checkpoint recovery, continues with unresolved items first, and keeps the recovery loop consistent across restarts. This is a loop-heavy continuity document task. |

## Per-Task Metrics

| Tier | Group | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Quality | Hybrid Quality | Quality Delta | Route OK |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| t0 | 1 | 3320 | 5986 | -80.30% | 19.15 | 23.73 | -23.93% | 85 | 100 | 15 | yes |
| t0 | 2 | 3541 | 6009 | -69.70% | 35.61 | 11.51 | 67.67% | 100 | 100 | 0 | yes |
| t0 | 3 | 3365 | 3010 | 10.55% | 18.49 | 14.65 | 20.79% | 100 | 100 | 0 | yes |
| t1 | 1 | 145690 | 13238 | 90.91% | 367.44 | 42.46 | 88.45% | 100 | 100 | 0 | yes |
| t1 | 2 | 5866 | 16279 | -177.51% | 336.45 | 95.65 | 71.57% | 100 | 100 | 0 | yes |
| t1 | 3 | 20236 | 11584 | 42.76% | 139.29 | 34.55 | 75.20% | 100 | 100 | 0 | yes |
| t2 | 1 | 33823 | 7342 | 78.29% | 208.84 | 61.57 | 70.52% | 85 | 100 | 15 | yes |
| t2 | 2 | 24039 | 11570 | 51.87% | 139.66 | 43.35 | 68.96% | 85 | 100 | 15 | yes |
| t2 | 3 | 48130 | 8251 | 82.86% | 147.95 | 39.24 | 73.48% | 85 | 100 | 15 | yes |
| t3 | 1 | 7308 | 8145 | -11.45% | 79.26 | 47.44 | 40.15% | 100 | 100 | 0 | yes |
| t3 | 2 | 17817 | 8487 | 52.37% | 118.22 | 45.19 | 61.78% | 100 | 100 | 0 | yes |
| t3 | 3 | 8283 | 8264 | 0.23% | 124.65 | 41.03 | 67.08% | 100 | 100 | 0 | yes |

## Tier Aggregates

| Tier | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 3 | 10226 | 15005 | -46.73% | 73.24 | 49.89 | 31.89% | 95.00 | 100.00 | 5.00 |
| t1 | 3 | 171792 | 41101 | 76.08% | 843.19 | 172.66 | 79.52% | 100.00 | 100.00 | 0.00 |
| t2 | 3 | 105992 | 27163 | 74.37% | 496.45 | 144.16 | 70.96% | 85.00 | 100.00 | 15.00 |
| t3 | 3 | 33408 | 24896 | 25.48% | 322.13 | 133.66 | 58.51% | 100.00 | 100.00 | 0.00 |

## Contract Family Aggregates

| Contract Family | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| generic_config_extract | 1 | 3541 | 6009 | -69.70% | 100.00 | 100.00 | 0.00 |
| loop_document_rewrite | 3 | 33408 | 24896 | 25.48% | 100.00 | 100.00 | 0.00 |
| read_extract | 2 | 6685 | 8996 | -34.57% | 92.50 | 100.00 | 7.50 |
| shared_state_repair | 3 | 105992 | 27163 | 74.37% | 85.00 | 100.00 | 15.00 |
| single_handoff_review | 3 | 171792 | 41101 | 76.08% | 100.00 | 100.00 | 0.00 |

## Adapter Family Aggregates

| Adapter Family | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| docs | 5 | 40093 | 33892 | 15.47% | 97.00 | 100.00 | 3.00 |
| generic-fs | 1 | 3541 | 6009 | -69.70% | 100.00 | 100.00 | 0.00 |
| python | 6 | 277784 | 68264 | 75.43% | 92.50 | 100.00 | 7.50 |

## Validator Type Aggregates

| Validator Type | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| document_exactness_and_checkpoint | 3 | 33408 | 24896 | 25.48% | 100.00 | 100.00 | 0.00 |
| exact_output | 3 | 10226 | 15005 | -46.73% | 95.00 | 100.00 | 5.00 |
| structured_review | 3 | 171792 | 41101 | 76.08% | 100.00 | 100.00 | 0.00 |
| unit_tests_and_artifacts | 3 | 105992 | 27163 | 74.37% | 85.00 | 100.00 | 15.00 |

## Coverage

- Resumability coverage: `3/3` tasks, `100.00%`
- Exactness preservation coverage: `9/12` tasks, `75.00%`

## Overall Aggregate

- Baseline total tokens: `321418`
- Hybrid total tokens: `108165`
- Token optimization pct: `66.35%`
- Baseline total seconds: `1735.01`
- Hybrid total seconds: `500.36`
- Time optimization pct: `71.16%`
- Baseline average quality: `95.00`
- Hybrid average quality: `100.00`
- Quality delta: `5.00`

## Detailed Findings

### t0 G1 - Three-line release notes summary

- Task description: Read a short release-notes file and return exactly three non-empty lines. The answer must cite the source file path and include two named release facts, so this task represents a tiny read-only extraction with strict wording requirements.
- Contract family: read_extract
- Adapter family: docs
- Validator type: exact_output
- Observed adapter id: generic-fs+docs
- Contract hash: 8f1dbbe05f2a1134812cafdd12a2975e206d12dfc30031194b4acb3b28da0a5f
- NL baseline tokens: 3320
- Hybrid tokens: 5986
- Token optimization pct: -80.30%
- NL baseline runtime seconds: 19.15
- Hybrid runtime seconds: 23.73
- Time optimization pct: -23.93%
- NL baseline quality: 85 (good)
- Hybrid quality: 100 (excellent)
- Quality delta: 15
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: exactly 3 non-empty lines; tier line correct; evidence names docs/release_notes.txt; required facts present: 1/2
- Hybrid notes: exactly 3 non-empty lines; tier line correct; evidence names docs/release_notes.txt; required facts present: 2/2

### t0 G2 - Routing threshold brief

- Task description: Read a small routing-threshold reference and produce a fixed-format brief that cites the source path and the key threshold facts. This models a tiny configuration lookup where format fidelity matters more than synthesis depth.
- Contract family: generic_config_extract
- Adapter family: generic-fs
- Validator type: exact_output
- Observed adapter id: generic-fs
- Contract hash: e951e5e6ce719d4f81a3700c0ae8b4176ec47a5b1887d4bc7e87d5d26188ea08
- NL baseline tokens: 3541
- Hybrid tokens: 6009
- Token optimization pct: -69.70%
- NL baseline runtime seconds: 35.61
- Hybrid runtime seconds: 11.51
- Time optimization pct: 67.67%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: exactly 3 non-empty lines; tier line correct; evidence names data/router_thresholds.json; required facts present: 2/2
- Hybrid notes: exactly 3 non-empty lines; tier line correct; evidence names data/router_thresholds.json; required facts present: 2/2

### t0 G3 - Operator note brief

- Task description: Read a short operator note and extract a three-line brief with the required path and two explicit facts. This represents a very small read-only summarization task with literal evidence requirements.
- Contract family: read_extract
- Adapter family: docs
- Validator type: exact_output
- Observed adapter id: generic-fs+docs
- Contract hash: adbcff351b60512f3a9c0f5ae39d36640c942d5287f10bf69ed6cfff61adbf39
- NL baseline tokens: 3365
- Hybrid tokens: 3010
- Token optimization pct: 10.55%
- NL baseline runtime seconds: 18.49
- Hybrid runtime seconds: 14.65
- Time optimization pct: 20.79%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: exactly 3 non-empty lines; tier line correct; evidence names docs/operator_notes.txt; required facts present: 2/2
- Hybrid notes: exactly 3 non-empty lines; tier line correct; evidence names docs/operator_notes.txt; required facts present: 2/2

### t1 G1 - Empty-input bug review

- Task description: Inspect a small Python function that fails on empty input, perform exactly one reviewer handoff, and write a structured review report with a decision and evidence. This simulates a lightweight one-pass review workflow.
- Contract family: single_handoff_review
- Adapter family: python
- Validator type: structured_review
- Observed adapter id: generic-fs+python+docs
- Contract hash: bf9d1aaf66223a865b0a366f9aa13da317dae8a02d78e4fc925e18f89f62babf
- NL baseline tokens: 145690
- Hybrid tokens: 13238
- Token optimization pct: 90.91%
- NL baseline runtime seconds: 367.44
- Hybrid runtime seconds: 42.46
- Time optimization pct: 88.45%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: review report written; required headings present; report cites src/review_target.py; bug explanation checks: 2/2
- Hybrid notes: review report written; required headings present; report cites src/review_target.py; bug explanation checks: 2/2

### t1 G2 - Zero-sample bug review

- Task description: Inspect a latency helper that breaks when the sample count is zero, perform exactly one reviewer handoff, and deliver a structured review note. This tests a single coordination step without reusable runtime state.
- Contract family: single_handoff_review
- Adapter family: python
- Validator type: structured_review
- Observed adapter id: generic-fs+python+docs
- Contract hash: 5c952a94a25721d9356c4dbdca13866327eb3be55997f4bd6fc1c6893f883a69
- NL baseline tokens: 5866
- Hybrid tokens: 16279
- Token optimization pct: -177.51%
- NL baseline runtime seconds: 336.45
- Hybrid runtime seconds: 95.65
- Time optimization pct: 71.57%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: review report written; required headings present; report cites src/latency_target.py; bug explanation checks: 2/2
- Hybrid notes: review report written; required headings present; report cites src/latency_target.py; bug explanation checks: 2/2

### t1 G3 - Missing-route bug review

- Task description: Inspect a route selector that crashes on unknown keys, perform exactly one reviewer handoff, and write a structured review result. This is another single-handoff review task with concrete evidence requirements.
- Contract family: single_handoff_review
- Adapter family: python
- Validator type: structured_review
- Observed adapter id: generic-fs+python+docs
- Contract hash: e972cc9c18b11ceeb862de3e26c4b47e8bb0c053b528f4186cf44abc05e962c0
- NL baseline tokens: 20236
- Hybrid tokens: 11584
- Token optimization pct: 42.76%
- NL baseline runtime seconds: 139.29
- Hybrid runtime seconds: 34.55
- Time optimization pct: 75.20%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: review report written; required headings present; report cites src/router_target.py; bug explanation checks: 2/2
- Hybrid notes: review report written; required headings present; report cites src/router_target.py; bug explanation checks: 2/2

### t2 G1 - Shared pipeline repair

- Task description: Repair a local deduplication pipeline, run the named unit-test command, write a shared-state artifact for the next phase, and produce review notes. This represents a multi-step engineering fix that has both code and handoff artifacts.
- Contract family: shared_state_repair
- Adapter family: python
- Validator type: unit_tests_and_artifacts
- Observed adapter id: generic-fs+python+docs
- Contract hash: 77ef1e2c56e0f8f6ccf3433ee7ed4cd364670f5ddcc11806e2f9f37b64695bb4
- NL baseline tokens: 33823
- Hybrid tokens: 7342
- Token optimization pct: 78.29%
- NL baseline runtime seconds: 208.84
- Hybrid runtime seconds: 61.57
- Time optimization pct: 70.52%
- NL baseline quality: 85 (good)
- Hybrid quality: 100 (excellent)
- Quality delta: 15
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: False
- Baseline notes: unit tests passed; shared state ACL-X artifact missing or invalid; review notes present
- Hybrid notes: unit tests passed; shared state ACL-X artifact present; review notes present

### t2 G2 - Reviewer queue repair

- Task description: Fix a queue-normalization bug, run the named unit-test command, write the shared-state handoff artifact, and leave a structured review note. This models a multi-step local fix with reusable machine-readable state.
- Contract family: shared_state_repair
- Adapter family: python
- Validator type: unit_tests_and_artifacts
- Observed adapter id: generic-fs+python+docs
- Contract hash: 04f99d71b955bc009f52d05fee0835f32965a60e200cd9934a9aab62e0f24e83
- NL baseline tokens: 24039
- Hybrid tokens: 11570
- Token optimization pct: 51.87%
- NL baseline runtime seconds: 139.66
- Hybrid runtime seconds: 43.35
- Time optimization pct: 68.96%
- NL baseline quality: 85 (good)
- Hybrid quality: 100 (excellent)
- Quality delta: 15
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: False
- Baseline notes: unit tests passed; shared state ACL-X artifact missing or invalid; review notes present
- Hybrid notes: unit tests passed; shared state ACL-X artifact present; review notes present

### t2 G3 - Stage plan repair

- Task description: Restore a missing first stage in a local deployment-plan workflow, rerun unit tests, write the shared-state artifact for the next phase, and produce review notes. This is a multi-step repair where task-contract fidelity matters because several artifacts must stay aligned.
- Contract family: shared_state_repair
- Adapter family: python
- Validator type: unit_tests_and_artifacts
- Observed adapter id: generic-fs+python+docs
- Contract hash: 9ffe2f06a7a9d91225066d409ff272f08fabd01dba0b2e8a885bf6443d5a87d1
- NL baseline tokens: 48130
- Hybrid tokens: 8251
- Token optimization pct: 82.86%
- NL baseline runtime seconds: 147.95
- Hybrid runtime seconds: 39.24
- Time optimization pct: 73.48%
- NL baseline quality: 85 (good)
- Hybrid quality: 100 (excellent)
- Quality delta: 15
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: False
- Baseline notes: unit tests passed; shared state ACL-X artifact missing or invalid; review notes present
- Hybrid notes: unit tests passed; shared state ACL-X artifact present; review notes present

### t3 G1 - Review loop playbook rewrite

- Task description: Rewrite a review playbook so each review cycle stays evidence-first, roles remain explicit, scope boundaries are preserved, and checkpoint notes keep the loop state recoverable. This is a loop-heavy document task rather than a code-fix task.
- Contract family: loop_document_rewrite
- Adapter family: docs
- Validator type: document_exactness_and_checkpoint
- Observed adapter id: generic-fs+docs
- Contract hash: c856537d4b528f22cfa9d4646153d3ae6eab9737850a7dcec7d01baf7f408a70
- NL baseline tokens: 7308
- Hybrid tokens: 8145
- Token optimization pct: -11.45%
- NL baseline runtime seconds: 79.26
- Hybrid runtime seconds: 47.44
- Time optimization pct: 40.15%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: document content checks: 9/9; document heading checks: 4/4; checkpoint note checks: 3/3
- Hybrid notes: document content checks: 9/9; document heading checks: 4/4; checkpoint note checks: 3/3

### t3 G2 - Release signoff handbook rewrite

- Task description: Rewrite a release-signoff handbook so blocker-first checkpoints remain intact before final signoff and the document can be resumed cleanly from saved progress notes. This represents a loop-heavy procedural document task.
- Contract family: loop_document_rewrite
- Adapter family: docs
- Validator type: document_exactness_and_checkpoint
- Observed adapter id: generic-fs+docs
- Contract hash: 4f570db97da561e87d6aad46aaae94ac341fb58177263285e63ca32d461ea433
- NL baseline tokens: 17817
- Hybrid tokens: 8487
- Token optimization pct: 52.37%
- NL baseline runtime seconds: 118.22
- Hybrid runtime seconds: 45.19
- Time optimization pct: 61.78%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: document content checks: 8/8; document heading checks: 4/4; checkpoint note checks: 3/3
- Hybrid notes: document content checks: 8/8; document heading checks: 4/4; checkpoint note checks: 3/3

### t3 G3 - Resume handoff guide rewrite

- Task description: Rewrite a resume-and-handoff guide so it preserves latest-checkpoint recovery, continues with unresolved items first, and keeps the recovery loop consistent across restarts. This is a loop-heavy continuity document task.
- Contract family: loop_document_rewrite
- Adapter family: docs
- Validator type: document_exactness_and_checkpoint
- Observed adapter id: generic-fs+docs
- Contract hash: 012887b1708085c7226d71aed20fd6f240fbde36ef1d693bd1d3a7567a820094
- NL baseline tokens: 8283
- Hybrid tokens: 8264
- Token optimization pct: 0.23%
- NL baseline runtime seconds: 124.65
- Hybrid runtime seconds: 41.03
- Time optimization pct: 67.08%
- NL baseline quality: 100 (excellent)
- Hybrid quality: 100 (excellent)
- Quality delta: 0
- Route match: True
- Adapter match: True
- Resumability covered: True
- Exactness preserved: True
- Baseline notes: document content checks: 9/9; document heading checks: 4/4; checkpoint note checks: 3/3
- Hybrid notes: document content checks: 9/9; document heading checks: 4/4; checkpoint note checks: 3/3

## Release Decision

Recommendation: GO for the bounded local engineering range covered by this report. Gate checks passed, the strategy lock stayed clean, hybrid routed to the expected tier, and average hybrid quality did not fall below the baseline.
This recommendation does not convert hybrid into a general-purpose optimization guarantee for arbitrary tasks.
