# Hybrid General-Task Heavy A/B Formal Report

## Scope

This report uses a heavy 4-tier x 3-group A/B matrix built from tasks whose semantic outputs are intentionally not ACL-X-centric.
The task corpus covers generic policy extraction, bug review, code repair, incident and operations document rewrite, and machine-readable handoff packages in ordinary JSON or Markdown.
The objective is to re-measure the current hybrid strategy on more general task semantics, with primary attention to token optimization, runtime optimization, and output quality preservation or improvement.

## Run Metadata

- Run ID: `20260413_160451`
- Generated at: `2026-04-13 16:44:52`
- Run root: `D:\ACLX_Publish\tests\formal\runs\hybrid_general_task_heavy_20260413_160451`
- Task count: `12`
- Gate tests passed: `True`
- Strategy lock clean: `True`
- Release recommendation: `GO`

## Overall Metrics

- Baseline total tokens: `219253`
- Hybrid total tokens: `116487`
- Token optimization vs baseline: `46.87%`
- Baseline total time: `1780.31s`
- Hybrid total time: `617.57s`
- Time optimization vs baseline: `65.31%`
- Baseline average quality: `99.25`
- Hybrid average quality: `100.00`
- Quality delta: `0.75`

## Tier Aggregates

| Tier | Tasks | Baseline Tokens | Hybrid Tokens | Token Opt | Baseline Time (s) | Hybrid Time (s) | Time Opt | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 3 | 13407 | 15031 | -12.11% | 69.70 | 49.05 | 29.62% | 100.00 | 100.00 | 0.00 |
| t1 | 3 | 145412 | 45676 | 68.59% | 1177.31 | 321.49 | 72.69% | 100.00 | 100.00 | 0.00 |
| t2 | 3 | 25600 | 24721 | 3.43% | 244.64 | 128.98 | 47.28% | 100.00 | 100.00 | 0.00 |
| t3 | 3 | 34834 | 31059 | 10.84% | 288.66 | 118.05 | 59.11% | 97.00 | 100.00 | 3.00 |

## Coverage

- Resumability coverage: `3/3` tasks, `100.00%`
- Exactness preservation coverage: `12/12` tasks, `100.00%`

## Per-Task Findings

### t0 G1 - Store pickup brief

- Description: Single-surface extraction from a generic store-pickup note with fixed evidence wording.
- Contract family: `generic_policy_extract`
- Adapter family: `docs`
- Validator type: `exact_output`
- Baseline tokens: `6568`
- Hybrid tokens: `6094`
- Token optimization: `7.22%`
- Baseline time: `21.22s`
- Hybrid time: `15.39s`
- Time optimization: `27.50%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t0`, observed `t0`
- Observed adapter id: `generic-fs+docs`
- Baseline notes: exactly 3 non-empty lines; tier line correct; evidence names docs/store_pickup_rules.txt; required facts present: 2/2
- Hybrid notes: exactly 3 non-empty lines; tier line correct; evidence names docs/store_pickup_rules.txt; required facts present: 2/2

### t0 G2 - Meeting capacity brief

- Description: Single-surface extraction from a generic meeting-capacity config with fixed-format output.
- Contract family: `generic_threshold_extract`
- Adapter family: `generic-fs`
- Validator type: `exact_output`
- Baseline tokens: `3552`
- Hybrid tokens: `6020`
- Token optimization: `-69.48%`
- Baseline time: `21.74s`
- Hybrid time: `20.56s`
- Time optimization: `5.41%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t0`, observed `t0`
- Observed adapter id: `generic-fs`
- Baseline notes: exactly 3 non-empty lines; tier line correct; evidence names data/room_capacity_thresholds.json; required facts present: 2/2
- Hybrid notes: exactly 3 non-empty lines; tier line correct; evidence names data/room_capacity_thresholds.json; required facts present: 2/2

### t0 G3 - Field outage note brief

- Description: Single-surface extraction from a generic field-outage note with literal evidence requirements.
- Contract family: `generic_ops_note_extract`
- Adapter family: `docs`
- Validator type: `exact_output`
- Baseline tokens: `3287`
- Hybrid tokens: `2917`
- Token optimization: `11.26%`
- Baseline time: `26.74s`
- Hybrid time: `13.11s`
- Time optimization: `50.98%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t0`, observed `t0`
- Observed adapter id: `generic-fs+docs`
- Baseline notes: exactly 3 non-empty lines; tier line correct; evidence names docs/field_outage_note.txt; required facts present: 2/2
- Hybrid notes: exactly 3 non-empty lines; tier line correct; evidence names docs/field_outage_note.txt; required facts present: 2/2

### t1 G1 - Blank shipment code review

- Description: Exactly one review handoff over a shipment helper that breaks when no valid shipment codes remain.
- Contract family: `single_handoff_review`
- Adapter family: `python`
- Validator type: `structured_review`
- Baseline tokens: `56541`
- Hybrid tokens: `11917`
- Token optimization: `78.92%`
- Baseline time: `328.53s`
- Hybrid time: `48.87s`
- Time optimization: `85.12%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t1`, observed `t1`
- Observed adapter id: `generic-fs+python+docs`
- Baseline notes: review report written; required headings present; report cites src/shipment_target.py; bug explanation checks: 2/2
- Hybrid notes: review report written; required headings present; report cites src/shipment_target.py; bug explanation checks: 2/2

### t1 G2 - Zero attendee review

- Description: Exactly one review handoff over a facility helper with a zero-room failure mode.
- Contract family: `single_handoff_review`
- Adapter family: `python`
- Validator type: `structured_review`
- Baseline tokens: `52829`
- Hybrid tokens: `17625`
- Token optimization: `66.64%`
- Baseline time: `409.33s`
- Hybrid time: `110.34s`
- Time optimization: `73.04%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t1`, observed `t1`
- Observed adapter id: `generic-fs+python+docs`
- Baseline notes: review report written; required headings present; report cites src/attendance_target.py; bug explanation checks: 2/2
- Hybrid notes: review report written; required headings present; report cites src/attendance_target.py; bug explanation checks: 2/2

### t1 G3 - Unknown locker review

- Description: Exactly one review handoff over a lookup helper that crashes on unknown locker ids.
- Contract family: `single_handoff_review`
- Adapter family: `python`
- Validator type: `structured_review`
- Baseline tokens: `36042`
- Hybrid tokens: `16134`
- Token optimization: `55.24%`
- Baseline time: `439.45s`
- Hybrid time: `162.28s`
- Time optimization: `63.07%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t1`, observed `t1`
- Observed adapter id: `generic-fs+python+docs`
- Baseline notes: review report written; required headings present; report cites src/locker_target.py; bug explanation checks: 2/2
- Hybrid notes: review report written; required headings present; report cites src/locker_target.py; bug explanation checks: 2/2

### t2 G1 - Delivery slot repair

- Description: Multi-step repair of a generic delivery-slot collector with reusable handoff state and validator-backed notes.
- Contract family: `generic_shared_state_repair`
- Adapter family: `python`
- Validator type: `unit_tests_and_generic_artifacts`
- Baseline tokens: `6492`
- Hybrid tokens: `8305`
- Token optimization: `-27.93%`
- Baseline time: `89.05s`
- Hybrid time: `45.08s`
- Time optimization: `49.38%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t2`, observed `t2`
- Observed adapter id: `generic-fs+python+docs`
- Baseline notes: unit tests passed; context keys present: 3/3; repair note headings: 2/2
- Hybrid notes: unit tests passed; context keys present: 3/3; repair note headings: 2/2

### t2 G2 - Maintenance window repair

- Description: Multi-step repair of a generic maintenance-window collector with machine-readable next-phase context.
- Contract family: `generic_shared_state_repair`
- Adapter family: `python`
- Validator type: `unit_tests_and_generic_artifacts`
- Baseline tokens: `6426`
- Hybrid tokens: `8376`
- Token optimization: `-30.35%`
- Baseline time: `74.52s`
- Hybrid time: `41.83s`
- Time optimization: `43.87%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t2`, observed `t2`
- Observed adapter id: `generic-fs+python+docs`
- Baseline notes: unit tests passed; context keys present: 3/3; repair note headings: 2/2
- Hybrid notes: unit tests passed; context keys present: 3/3; repair note headings: 2/2

### t2 G3 - Shift label repair

- Description: Multi-step repair of a generic shift-label helper with reusable machine-readable handoff state.
- Contract family: `generic_shared_state_repair`
- Adapter family: `python`
- Validator type: `unit_tests_and_generic_artifacts`
- Baseline tokens: `12682`
- Hybrid tokens: `8040`
- Token optimization: `36.60%`
- Baseline time: `81.08s`
- Hybrid time: `42.08s`
- Time optimization: `48.10%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t2`, observed `t2`
- Observed adapter id: `generic-fs+python+docs`
- Baseline notes: unit tests passed; context keys present: 3/3; repair note headings: 2/2
- Hybrid notes: unit tests passed; context keys present: 3/3; repair note headings: 2/2

### t3 G1 - Warehouse cycle count playbook

- Description: Loop-heavy rewrite of a generic warehouse cycle-count playbook with resumable checkpoints and discrepancy-first ordering.
- Contract family: `loop_document_rewrite`
- Adapter family: `docs`
- Validator type: `document_exactness_and_checkpoint`
- Baseline tokens: `18114`
- Hybrid tokens: `14918`
- Token optimization: `17.64%`
- Baseline time: `110.35s`
- Hybrid time: `36.25s`
- Time optimization: `67.15%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t3`, observed `t3`
- Observed adapter id: `generic-fs+docs`
- Baseline notes: document content checks: 7/7; document heading checks: 4/4; checkpoint note checks: 3/3
- Hybrid notes: document content checks: 7/7; document heading checks: 4/4; checkpoint note checks: 3/3

### t3 G2 - Vendor maintenance handoff guide

- Description: Loop-heavy rewrite of a generic vendor-maintenance handoff guide with checkpoint continuity and unresolved-first ordering.
- Contract family: `loop_document_rewrite`
- Adapter family: `docs`
- Validator type: `document_exactness_and_checkpoint`
- Baseline tokens: `11203`
- Hybrid tokens: `8077`
- Token optimization: `27.90%`
- Baseline time: `105.94s`
- Hybrid time: `34.75s`
- Time optimization: `67.20%`
- Baseline quality: `100` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `0`
- Routed tier: expected `t3`, observed `t3`
- Observed adapter id: `generic-fs+docs`
- Baseline notes: document content checks: 7/7; document heading checks: 4/4; checkpoint note checks: 3/3
- Hybrid notes: document content checks: 7/7; document heading checks: 4/4; checkpoint note checks: 3/3

### t3 G3 - Site readiness manual

- Description: Loop-heavy rewrite of a generic site-readiness manual with explicit roles, blocker-first sequencing, and resumable checkpoints.
- Contract family: `loop_document_rewrite`
- Adapter family: `docs`
- Validator type: `document_exactness_and_checkpoint`
- Baseline tokens: `5517`
- Hybrid tokens: `8064`
- Token optimization: `-46.17%`
- Baseline time: `72.37s`
- Hybrid time: `47.05s`
- Time optimization: `34.99%`
- Baseline quality: `91` (excellent)
- Hybrid quality: `100` (excellent)
- Quality delta: `9`
- Routed tier: expected `t3`, observed `t3`
- Observed adapter id: `generic-fs+docs`
- Baseline notes: document content checks: 6/7; document heading checks: 4/4; checkpoint note checks: 3/3
- Hybrid notes: document content checks: 7/7; document heading checks: 4/4; checkpoint note checks: 3/3

## Interpretation

- Tasks with hybrid quality gains: `1/12`
- Tasks with positive token optimization: `8/12`
- Tasks with positive time optimization: `12/12`
- The result should be interpreted as evidence about bounded, validator-checkable general tasks, not as a guarantee for arbitrary open-ended work.
- If t0 remains weak on token savings while preserving quality, that is consistent with fixed routing overhead on very small tasks rather than a failure of semantic generalization.
- If t2 or t3 retain quality while improving tokens or time on generic repairs and looped documents, that is the strongest signal that the current hybrid design is no longer overfit to ACL-X-specific project surfaces.

## Conclusion

Recommendation: GO for the bounded local general-task range covered by this report. The current hybrid strategy preserved or improved quality on average while staying within the validated task families in this matrix.
