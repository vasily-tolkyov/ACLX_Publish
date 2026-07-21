# Hybrid General-Task Heavy A/B Formal Report

## Scope

This report captures the current public general-task heavy benchmark after the repaired `t2` slice was merged back into the latest release-facing summary.
The matrix remains a 4-tier x 3-task structured-task benchmark built to avoid ACL-X-specific output semantics while still requiring explicit artifacts, validators, and closure conditions.

## Run Metadata

- Run ID: `20260415_110636_t2_refresh`
- Generated at: `2026-04-15 11:06:36`
- Task count: `12`
- Gate tests passed: `True`
- Strategy lock clean: `True`
- Release recommendation: `GO`

## Overall Metrics

- Baseline total tokens: `167281`
- Hybrid total tokens: `114125`
- Token optimization vs baseline: `31.78%`
- Baseline total time: `686.96s`
- Hybrid total time: `315.18s`
- Time optimization vs baseline: `54.12%`
- Baseline average quality: `99.25`
- Hybrid average quality: `100.00`
- Quality delta: `0.75`

## Tier Aggregates

| Tier | Tasks | Baseline Tokens | Hybrid Tokens | Token Opt | Baseline Time (s) | Hybrid Time (s) | Time Opt | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 3 | 25563 | 23719 | 7.21% | 52.55 | 50.77 | 3.38% | 100.00 | 100.00 | 0.00 |
| t1 | 3 | 49123 | 29085 | 40.79% | 258.67 | 85.90 | 66.79% | 100.00 | 100.00 | 0.00 |
| t2 | 3 | 59416 | 30742 | 48.26% | 225.69 | 87.20 | 61.36% | 100.00 | 100.00 | 0.00 |
| t3 | 3 | 33179 | 30579 | 7.84% | 150.06 | 91.31 | 39.15% | 97.00 | 100.00 | 3.00 |

## Coverage

- Resumability coverage: `3/3`
- Exactness preservation coverage: `12/12`

## Task Matrix

| Tier | Group | Task | Baseline Tokens | Hybrid Tokens | Token Improvement | Baseline Time | Hybrid Time | Time Improvement | Baseline Quality | Hybrid Quality |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 1 | Store pickup brief | 8476 | 8246 | 2.71% | 20.97s | 17.46s | 16.76% | 100 | 100 |
| t0 | 2 | Meeting capacity brief | 8543 | 8275 | 3.14% | 15.90s | 16.19s | -1.83% | 100 | 100 |
| t0 | 3 | Field outage note brief | 8544 | 7198 | 15.75% | 15.68s | 17.13s | -9.23% | 100 | 100 |
| t1 | 1 | Blank shipment code review | 16009 | 9756 | 39.06% | 75.15s | 29.95s | 60.15% | 100 | 100 |
| t1 | 2 | Zero attendee review | 16124 | 9582 | 40.57% | 98.15s | 30.11s | 69.33% | 100 | 100 |
| t1 | 3 | Unknown locker review | 16990 | 9747 | 42.63% | 85.37s | 25.84s | 69.73% | 100 | 100 |
| t2 | 1 | Delivery slot repair | 22400 | 10388 | 53.62% | 70.95s | 29.55s | 58.35% | 100 | 100 |
| t2 | 2 | Maintenance window repair | 22790 | 10341 | 54.62% | 66.18s | 32.32s | 51.17% | 100 | 100 |
| t2 | 3 | Shift label repair | 14226 | 10013 | 29.61% | 88.56s | 25.33s | 71.40% | 100 | 100 |
| t3 | 1 | Warehouse cycle count playbook | 10354 | 10228 | 1.22% | 49.30s | 27.95s | 43.30% | 100 | 100 |
| t3 | 2 | Vendor maintenance handoff guide | 11560 | 10216 | 11.63% | 51.14s | 31.67s | 38.07% | 100 | 100 |
| t3 | 3 | Site readiness manual | 11265 | 10135 | 10.03% | 49.62s | 31.69s | 36.13% | 91 | 100 |

## Notes

- This release-facing refresh preserves the bounded public claim: on structured general tasks with explicit artifacts, validators, and closure conditions, hybrid is cheaper and faster on aggregate without average quality regression.
- The main change from the previous public general-task benchmark is the repaired `t2` slice, especially `t2_g3`, which removed an anomalous token spike and restored the intended `t2` efficiency profile.
