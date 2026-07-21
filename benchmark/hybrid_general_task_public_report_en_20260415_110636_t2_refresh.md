# Hybrid General Task Heavy A/B Public Report

## Executive Summary

This report evaluates the locked hybrid strategy on a fresh 4-tier x 3-task general-purpose benchmark.
The benchmark is intentionally not ACL-X-centric: it covers policy extraction, bug review, repair with reusable artifacts, and loop-heavy document rewrite.
Public release recommendation: **GO**.

## Benchmark Basis

- Run ID: `20260415_110636_t2_refresh`
- Strategy lock: `aclx-strategy-freeze-2026-04-14-t0-t1-stable`
- Generated at: `2026-04-15 11:06:36`
- Matrix size: `12` tasks across `t0/t1/t2/t3`
- Gate tests passed: `True`
- Strategy lock clean: `True`
- Baseline failed tasks: `0`

## Aggregate Outcome

- Baseline total tokens: `167281`
- Hybrid total tokens: `114125`
- Aggregate token improvement: `31.78%`
- Baseline total time: `686.96s`
- Hybrid total time: `315.18s`
- Aggregate time improvement: `54.12%`
- Baseline average quality: `99.25`
- Hybrid average quality: `100.00`
- Quality delta: `0.75`

## Release Interpretation

- Tasks with positive token improvement: `12/12`
- Tasks with positive time improvement: `10/12`
- Resumability coverage: `3/3`
- Exactness preservation coverage: `12/12`
- The validated claim is bounded: hybrid is faster and cheaper on aggregate for structured general tasks in this matrix, without average quality regression.
- This is not a guarantee for arbitrary open-ended work. It is evidence for structured tasks with explicit artifacts, validators, and closure conditions.

## Tier Aggregates

| Tier | Tasks | Baseline Tokens | Hybrid Tokens | Token Improvement | Baseline Time | Hybrid Time | Time Improvement | Baseline Avg Quality | Hybrid Avg Quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 3 | 25563 | 23719 | 7.21% | 52.55s | 50.77s | 3.38% | 100.00 | 100.00 |
| t1 | 3 | 49123 | 29085 | 40.79% | 258.67s | 85.90s | 66.79% | 100.00 | 100.00 |
| t2 | 3 | 59416 | 30742 | 48.26% | 225.69s | 87.20s | 61.36% | 100.00 | 100.00 |
| t3 | 3 | 33179 | 30579 | 7.84% | 150.06s | 91.31s | 39.15% | 97.00 | 100.00 |

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

## Conclusion

Hybrid is ready for public release within the validated structured-task range covered by this benchmark. The current locked strategy improved aggregate token and time cost while preserving average output quality.
