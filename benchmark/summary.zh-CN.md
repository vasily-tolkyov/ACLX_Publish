# Benchmark 总览

英文版见 [summary.md](summary.md)。

## 当前结论

公开发布结论：`GO`

最新通过验证的运行：

- 预发布重型：`20260413_152717`
- 通用任务重型：`20260415_110636_t2_refresh`

## 总体结果

| 套件 | 任务数 | 基线 Tokens | Hybrid Tokens | Token 优化 | 基线耗时 | Hybrid 耗时 | 时间优化 | 基线平均质量 | Hybrid 平均质量 | 质量差值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 预发布重型 | 12 | 321418 | 108165 | 66.35% | 1735.01s | 500.36s | 71.16% | 95.00 | 100.00 | 5.00 |
| 通用任务重型 | 12 | 167281 | 114125 | 31.78% | 686.96s | 315.18s | 54.12% | 99.25 | 100.00 | 0.75 |

## 分层发布口径

- 对外应将 hybrid 视为“质量优先”的策略。只有验证集上的平均输出质量持平或更好时，release claim 才成立。
- 主要优化目标是耗时。
- token 表现是次级目标，而且严格依赖 tier。下面的表是推荐对外使用的统一口径。

| 层级 | 路由类型 | 推荐表述 | 预发布重型 `20260413_152717` | 通用任务重型 `20260415_110636_t2_refresh` |
| --- | --- | --- | --- | --- |
| `t0` | 无真实 handoff、无共享机器状态、无循环的单表面任务 | 精确性优先层。聚合收益可能存在，但在极小固定格式任务上仍然对噪声敏感。 | token `-46.73%`，time `+31.89%`，quality `+5.00` | token `+7.21%`，time `+3.38%`，quality `+0.00` |
| `t1` | 恰好一次真实 handoff 或一次子代理审查 | 当前公开证据中最稳定、最低风险的 token 与时间双重优化层。 | token `+76.08%`，time `+79.52%`，quality `+0.00` | token `+40.79%`，time `+66.79%`，quality `+0.00` |
| `t2` | 带可复用机器状态、工件契约或 2+ handoff 的多步本地修复任务 | 当显式工件契约和验证器存在时，这一层已经可以支撑更强的公开效率表述。时间仍是主目标，但新的公开通用任务结果里 token 也有较强收益。 | token `+74.37%`，time `+70.96%`，quality `+15.00` | token `+48.26%`，time `+61.36%`，quality `+0.00` |
| `t3` | 带 checkpoint、resume、replay 或 repeated verification 的循环型任务 | 时间优先层，并以质量保护为前提。聚合 token 收益仍小于 `t1` 和当前刷新后的 `t2`。 | token `+25.48%`，time `+58.51%`，quality `+0.00` | token `+7.84%`，time `+39.15%`，quality `+3.00` |

这些数字是两轮重型测试的 tier 聚合结果，不代表同一 tier 内每个任务都会在 token 上朝同一方向变化。对外不要把 hybrid 描述成“普遍性的 token 优化器”。当前更准确的公开口径是：`t1` 仍是最稳的双重优化层，`t2` 已经可以支撑更强的效率叙事，`t3` 仍以时间优化为主。

## 文件地图

- [summary.md](summary.md)：最新英文 benchmark 总览
- [hybrid_general_task_heavy_latest.json](hybrid_general_task_heavy_latest.json)：最新通用任务重型机器可读汇总
- [hybrid_general_task_heavy_latest_formal_report.md](hybrid_general_task_heavy_latest_formal_report.md)：最新通用任务正式报告
- [hybrid_general_task_public_report_en_latest.md](hybrid_general_task_public_report_en_latest.md)：最新英文公开报告
- [hybrid_general_task_public_report_en_latest.pdf](hybrid_general_task_public_report_en_latest.pdf)：最新英文 PDF
- [hybrid_general_task_public_report_zh_latest.md](hybrid_general_task_public_report_zh_latest.md)：最新中文公开报告
- [hybrid_general_task_public_report_zh_latest.pdf](hybrid_general_task_public_report_zh_latest.pdf)：最新中文 PDF
- [../docs/release_update_v0.3.4.zh-CN.md](../docs/release_update_v0.3.4.zh-CN.md)：`v0.3.4` 正式更新说明
- [../docs/release_update_v0.3.4.md](../docs/release_update_v0.3.4.md)：`v0.3.4` release update notes
- [hybrid_pre_release_heavy_latest.json](hybrid_pre_release_heavy_latest.json)：最新预发布重型机器可读汇总
- [../docs/release_validation_latest.zh-CN.md](../docs/release_validation_latest.zh-CN.md)：权威的最新中文预发布重型报告
- [../docs/release_validation_latest.md](../docs/release_validation_latest.md)：权威的最新英文预发布重型报告
- [hybrid_pre_release_heavy_latest.pdf](hybrid_pre_release_heavy_latest.pdf)：最新预发布重型 PDF
