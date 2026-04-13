# Benchmark Summary

Chinese version: [summary.zh-CN.md](summary.zh-CN.md).

## Current Verdict

Public release verdict: `GO`

Latest validated runs:

- pre-release heavy: `20260413_152717`
- general-task heavy: `20260413_160451`

## Aggregate Results

| Suite | Tasks | Baseline Tokens | Hybrid Tokens | Token Improvement | Baseline Time | Hybrid Time | Time Improvement | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-release heavy | 12 | 321418 | 108165 | 66.35% | 1735.01s | 500.36s | 71.16% | 95.00 | 100.00 | 5.00 |
| General-task heavy | 12 | 219253 | 116487 | 46.87% | 1780.31s | 617.57s | 65.31% | 99.25 | 100.00 | 0.75 |

## Release Messaging By Tier

- Hybrid should be messaged as quality-first. A release claim requires average quality to stay flat or improve on the validated suites.
- The primary optimization target is elapsed time.
- Token behavior is secondary and tier-sensitive. The table below is the recommended public wording anchor.

| Tier | Route shape | Public message | Pre-release heavy `20260413_152717` | General-task heavy `20260413_160451` |
| --- | --- | --- | --- | --- |
| `t0` | Single-surface work with no real handoff, no shared machine state, and no loop | Exactness-first tier. Time often improves, but tokens tend to regress on tiny fixed-format work. | token `-46.73%`, time `+31.89%`, quality `+5.00` | token `-12.11%`, time `+29.62%`, quality `+0.00` |
| `t1` | Exactly one deliberate handoff or one child-agent review pass | Strongest repeat aggregate token and time win in the current public evidence. | token `+76.08%`, time `+79.52%`, quality `+0.00` | token `+68.59%`, time `+72.69%`, quality `+0.00` |
| `t2` | Multi-step local repair with reusable machine state, artifact contracts, or 2+ handoffs | Time-first tier with quality protection. Token gains are workload-sensitive and not guaranteed for every task. | token `+74.37%`, time `+70.96%`, quality `+15.00` | token `+3.43%`, time `+47.28%`, quality `+0.00` |
| `t3` | Loop-heavy work with checkpoint, resume, replay, or repeated verification | Time-first tier with quality protection. Aggregate token gains are usually smaller than `t1` and can reverse on individual tasks. | token `+25.48%`, time `+58.51%`, quality `+0.00` | token `+10.84%`, time `+59.11%`, quality `+3.00` |

These are tier aggregates from two heavy suites, not a promise that every task inside a tier will move in the same token direction. For external release messaging, avoid describing hybrid as a universal token optimizer.

## File Map

- [summary.zh-CN.md](summary.zh-CN.md): latest Chinese benchmark summary
- [hybrid_general_task_heavy_latest.json](hybrid_general_task_heavy_latest.json): latest machine-readable general-task heavy summary
- [hybrid_general_task_heavy_latest_formal_report.md](hybrid_general_task_heavy_latest_formal_report.md): latest formal general-task report
- [hybrid_general_task_public_report_en_latest.md](hybrid_general_task_public_report_en_latest.md): latest English public report
- [hybrid_general_task_public_report_en_latest.pdf](hybrid_general_task_public_report_en_latest.pdf): latest English PDF
- [hybrid_general_task_public_report_zh_latest.md](hybrid_general_task_public_report_zh_latest.md): latest Chinese public report
- [hybrid_general_task_public_report_zh_latest.pdf](hybrid_general_task_public_report_zh_latest.pdf): latest Chinese PDF
- [hybrid_pre_release_heavy_latest.json](hybrid_pre_release_heavy_latest.json): latest machine-readable pre-release heavy summary
- [../docs/release_validation_latest.zh-CN.md](../docs/release_validation_latest.zh-CN.md): canonical latest Chinese pre-release heavy report
- [../docs/release_validation_latest.md](../docs/release_validation_latest.md): canonical latest pre-release heavy report
- [hybrid_pre_release_heavy_latest.pdf](hybrid_pre_release_heavy_latest.pdf): latest pre-release heavy PDF
