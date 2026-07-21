# ACL-X v0.3.4 正式更新说明

英文版见 [release_update_v0.3.4.md](release_update_v0.3.4.md)。

## 摘要

`v0.3.4` 是 ACL-X 当前的正式公开补丁更新版本。本次更新不改变公开 benchmark 的 headline 结果，主要目标是把已同步到 GitHub 的源码与 CI 行为进一步收稳，使当前发布线在 Windows 和 Linux 上都能稳定验证通过。

## 头部结果

- 通用任务重型运行 `20260415_110636_t2_refresh`：聚合 token 优化 `31.78%`，聚合时间优化 `54.12%`，质量差值 `+0.75`。
- 预发布重型运行 `20260413_152717`：聚合 token 优化 `66.35%`，聚合时间优化 `71.16%`，质量差值 `+5.00`。
- 当前公开发布立场仍然是质量优先、时间优先。token 收益是真实存在的，但仍然依赖 tier，而不是普遍保证。

## 主要变化

- 统一了 strategy lock 的文本哈希规则，消除了仅由换行符和 checkout 文本形态差异导致的跨平台 CI 漂移。
- 统一了 Windows 与 Linux 下的项目根相对路径处理，使 bundle 证据、prompt hints 和锁定测试的行为保持一致。
- 为提到绝对 `TASK.md` 路径的 prompt 增加了根目录合同源回退，保证 doc-loop exactness 规则在 CI 中仍能稳定加载。
- 将包元数据、changelog、README 入口、benchmark summary 链接和对外发布文案统一升级到新的补丁版本号。

## 对外表述建议

- `t1` 仍然是当前最清晰、最低风险的 token 与时间双重优化层。
- 当显式工件契约和验证器存在时，`t2` 依旧可以支撑更强的公开效率表述。
- `t3` 仍应表述为质量优先、时间优先，token 收益较小。
- `t0` 仍应表述为精确性优先，而不是 token 优先。
- `v0.3.4` 的定位是公开发布线稳定性补丁，而不是新的 benchmark 口径升级。

## 验证入口

- 公开 benchmark 工件继续统一放在 `benchmark/`。
- 预发布重型验证的权威报告仍在 `docs/release_validation_latest.md`。
- 刷新后的通用任务公开报告仍位于 `benchmark/hybrid_general_task_public_report_en_latest.md`、`benchmark/hybrid_general_task_public_report_zh_latest.md` 及对应的 PDF/JSON 工件中。
- 当前公开 CI 已可在 `ubuntu-latest` 与 `windows-latest` 上同时验证通过。
