# Benchmark 总览

英文版见 [summary.md](summary.md)。

## 当前结论

公开发布结论：`GO`

最新通过验证的运行：

- 预发布重型：`20260413_152717`
- 通用任务重型：`20260413_160451`

## 总体结果

| 套件 | 任务数 | 基线 Tokens | Hybrid Tokens | Token 优化 | 基线耗时 | Hybrid 耗时 | 时间优化 | 基线平均质量 | Hybrid 平均质量 | 质量差值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 预发布重型 | 12 | 321418 | 108165 | 66.35% | 1735.01s | 500.36s | 71.16% | 95.00 | 100.00 | 5.00 |
| 通用任务重型 | 12 | 219253 | 116487 | 46.87% | 1780.31s | 617.57s | 65.31% | 99.25 | 100.00 | 0.75 |

## 分层发布口径

- 对外应将 hybrid 视为“质量优先”的策略。只有验证集上的平均输出质量持平或更好时，release claim 才成立。
- 主要优化目标是耗时。
- token 表现是次级目标，而且严格依赖 tier。下面的表是推荐对外使用的统一口径。

| 层级 | 路由类型 | 推荐表述 | 预发布重型 `20260413_152717` | 通用任务重型 `20260413_160451` |
| --- | --- | --- | --- | --- |
| `t0` | 无真实 handoff、无共享机器状态、无循环的单表面任务 | 精确性优先层。耗时经常改善，但在微小固定格式任务上，token 更倾向于退化。 | token `-46.73%`，time `+31.89%`，quality `+5.00` | token `-12.11%`，time `+29.62%`，quality `+0.00` |
| `t1` | 恰好一次真实 handoff 或一次子代理审查 | 当前公开证据中最强的 token 与时间双重优化层。 | token `+76.08%`，time `+79.52%`，quality `+0.00` | token `+68.59%`，time `+72.69%`，quality `+0.00` |
| `t2` | 带可复用机器状态、工件契约或 2+ handoff 的多步本地修复任务 | 时间优先层，并以质量保护为前提。token 收益依赖任务形态，不保证每个任务都优化。 | token `+74.37%`，time `+70.96%`，quality `+15.00` | token `+3.43%`，time `+47.28%`，quality `+0.00` |
| `t3` | 带 checkpoint、resume、replay 或 repeated verification 的循环型任务 | 时间优先层，并以质量保护为前提。聚合 token 收益通常小于 `t1`，单任务也可能回退。 | token `+25.48%`，time `+58.51%`，quality `+0.00` | token `+10.84%`，time `+59.11%`，quality `+3.00` |

这些数字是两轮重型测试的 tier 聚合结果，不代表同一 tier 内每个任务都会在 token 上朝同一方向变化。对外不要把 hybrid 描述成“普遍性的 token 优化器”。

## 文件地图

- [summary.md](summary.md)：最新英文 benchmark 总览
- [hybrid_general_task_heavy_latest.json](hybrid_general_task_heavy_latest.json)：最新通用任务重型机器可读汇总
- [hybrid_general_task_heavy_latest_formal_report.md](hybrid_general_task_heavy_latest_formal_report.md)：最新通用任务正式报告
- [hybrid_general_task_public_report_en_latest.md](hybrid_general_task_public_report_en_latest.md)：最新英文公开报告
- [hybrid_general_task_public_report_en_latest.pdf](hybrid_general_task_public_report_en_latest.pdf)：最新英文 PDF
- [hybrid_general_task_public_report_zh_latest.md](hybrid_general_task_public_report_zh_latest.md)：最新中文公开报告
- [hybrid_general_task_public_report_zh_latest.pdf](hybrid_general_task_public_report_zh_latest.pdf)：最新中文 PDF
- [hybrid_pre_release_heavy_latest.json](hybrid_pre_release_heavy_latest.json)：最新预发布重型机器可读汇总
- [../docs/release_validation_latest.zh-CN.md](../docs/release_validation_latest.zh-CN.md)：权威的最新中文预发布重型报告
- [../docs/release_validation_latest.md](../docs/release_validation_latest.md)：权威的最新英文预发布重型报告
- [hybrid_pre_release_heavy_latest.pdf](hybrid_pre_release_heavy_latest.pdf)：最新预发布重型 PDF
