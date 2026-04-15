# ACL-X v0.3.3 正式更新说明

英文版见 [release_update_v0.3.3.md](release_update_v0.3.3.md)。

## 摘要

`v0.3.3` 是 ACL-X 当前的正式公开更新版本。这次更新刷新了公开通用任务 benchmark 包，将发布源码树同步到当前锁定 hybrid 策略状态，并补齐了更适合 GitHub 发布的正式更新文案。

## 头部结果

- 通用任务重型运行 `20260415_110636_t2_refresh`：聚合 token 优化 `31.78%`，聚合时间优化 `54.12%`，质量差值 `+0.75`。
- 预发布重型运行 `20260413_152717`：聚合 token 优化 `66.35%`，聚合时间优化 `71.16%`，质量差值 `+5.00`。
- 当前公开发布立场仍然是质量优先、耗时优先。token 收益真实存在，但依旧依赖 tier，而不是普遍保证。

## 主要变化

- 用刷新后的通用任务运行结果替换了此前较弱的公开 `t2` benchmark 切片。
- 在 benchmark 更新的同时发布了当前锁定的源码树、tier 配置、runtime/session 关键面和行为锁定测试。
- 将 README、benchmark 总览、首发文案包、发布核对清单和双语公开报告统一到同一条发布线。

## 对外表述建议

- `t1` 仍然是当前最清晰、最低风险的 token 与时间双重优化层。
- 当显式工件契约和验证器存在时，`t2` 现在可以支撑更强的公开效率表述。
- `t3` 仍应表述为质量优先、时间优先，但 token 收益较小。
- `t0` 仍应表述为精确性优先，而不是 token 优先。

## 验证入口

- 公开 benchmark 工件统一放在 `benchmark/`。
- 预发布重型验证的权威报告仍在 `docs/release_validation_latest.md`。
- 刷新后的通用任务公开报告位于 `benchmark/hybrid_general_task_public_report_zh_latest.md`、`benchmark/hybrid_general_task_public_report_en_latest.md` 及对应的 PDF/JSON 工件中。
