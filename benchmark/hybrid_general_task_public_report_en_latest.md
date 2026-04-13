# Hybrid General Task Heavy A/B Public Report

## Executive Summary

This report evaluates the locked hybrid strategy on a fresh 4-tier x 3-task general-purpose benchmark.
The benchmark is intentionally not ACL-X-centric: it covers policy extraction, bug review, repair with reusable artifacts, and loop-heavy document rewrite.
Public release recommendation: **GO**.

## Benchmark Basis

- Run ID: `20260413_160451`
- Strategy lock: `aclx-strategy-freeze-2026-04-13-t3-shell-trimmed`
- Generated at: `2026-04-13 16:44:52`
- Matrix size: `12` tasks across `t0/t1/t2/t3`
- Gate tests passed: `True`
- Strategy lock clean: `True`
- Baseline failed tasks: `0`

## Aggregate Outcome

- Baseline total tokens: `219253`
- Hybrid total tokens: `116487`
- Aggregate token improvement: `46.87%`
- Baseline total time: `1780.31s`
- Hybrid total time: `617.57s`
- Aggregate time improvement: `65.31%`
- Baseline average quality: `99.25`
- Hybrid average quality: `100.00`
- Quality delta: `0.75`

## Release Interpretation

- Tasks with positive token improvement: `8/12`
- Tasks with positive time improvement: `12/12`
- Resumability coverage: `3/3`
- Exactness preservation coverage: `12/12`
- The validated claim is bounded: hybrid is faster and cheaper on aggregate for structured general tasks in this matrix, without average quality regression.
- This is not a guarantee for arbitrary open-ended work. It is evidence for structured tasks with explicit artifacts, validators, and closure conditions.

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

## Tier Aggregates

| Tier | Tasks | Baseline Tokens | Hybrid Tokens | Token Improvement | Baseline Time | Hybrid Time | Time Improvement | Baseline Avg Quality | Hybrid Avg Quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 3 | 13407 | 15031 | -12.11% | 69.70s | 49.05s | 29.62% | 100.00 | 100.00 |
| t1 | 3 | 145412 | 45676 | 68.59% | 1177.31s | 321.49s | 72.69% | 100.00 | 100.00 |
| t2 | 3 | 25600 | 24721 | 3.43% | 244.64s | 128.98s | 47.28% | 100.00 | 100.00 |
| t3 | 3 | 34834 | 31059 | 10.84% | 288.66s | 118.05s | 59.11% | 97.00 | 100.00 |

## Task Matrix

| Tier | Group | Task | Baseline Tokens | Hybrid Tokens | Token Improvement | Baseline Time | Hybrid Time | Time Improvement | Baseline Quality | Hybrid Quality |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 1 | Store pickup brief | 6568 | 6094 | 7.22% | 21.22s | 15.39s | 27.50% | 100 | 100 |
| t0 | 2 | Meeting capacity brief | 3552 | 6020 | -69.48% | 21.74s | 20.56s | 5.41% | 100 | 100 |
| t0 | 3 | Field outage note brief | 3287 | 2917 | 11.26% | 26.74s | 13.11s | 50.98% | 100 | 100 |
| t1 | 1 | Blank shipment code review | 56541 | 11917 | 78.92% | 328.53s | 48.87s | 85.12% | 100 | 100 |
| t1 | 2 | Zero attendee review | 52829 | 17625 | 66.64% | 409.33s | 110.34s | 73.04% | 100 | 100 |
| t1 | 3 | Unknown locker review | 36042 | 16134 | 55.24% | 439.45s | 162.28s | 63.07% | 100 | 100 |
| t2 | 1 | Delivery slot repair | 6492 | 8305 | -27.93% | 89.05s | 45.08s | 49.38% | 100 | 100 |
| t2 | 2 | Maintenance window repair | 6426 | 8376 | -30.35% | 74.52s | 41.83s | 43.87% | 100 | 100 |
| t2 | 3 | Shift label repair | 12682 | 8040 | 36.60% | 81.08s | 42.08s | 48.10% | 100 | 100 |
| t3 | 1 | Warehouse cycle count playbook | 18114 | 14918 | 17.64% | 110.35s | 36.25s | 67.15% | 100 | 100 |
| t3 | 2 | Vendor maintenance handoff guide | 11203 | 8077 | 27.90% | 105.94s | 34.75s | 67.20% | 100 | 100 |
| t3 | 3 | Site readiness manual | 5517 | 8064 | -46.17% | 72.37s | 47.05s | 34.99% | 91 | 100 |

## Conclusion

Hybrid is ready for public release within the validated structured-task range covered by this benchmark. The current locked strategy should be described as quality-first and time-first: it reduced elapsed time across all tiers in this matrix while keeping average quality flat or better, and its token behavior remained tier-dependent rather than universal.
