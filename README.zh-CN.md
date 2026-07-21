# ACL-X

ACL-X 是一套面向 AI agent 的高密度通信语言与可见运行时边界。

英文版说明见 [README.md](README.md)。

## 已验证范围

> Hybrid 是一套面向有边界本地工作流的有限优化策略，并不是适用于任意通用任务的普遍优化方案。
>
> 这套策略仍然可以运行在通用任务上，但如果超出当前重型报告已经验证的任务族，就不能保证质量持平，也不能保证 token 或时间收益。

当前公开基准集中已验证的任务族：

- 带严格输出格式和显式字面量要求的本地文件读取或摘要任务
- 恰好一次真实 handoff 且必须写出明确工件的一次性审查任务
- 带命名文件、命名测试或命令、以及显式机器可读 handoff 工件的多步本地代码或配置修复任务
- 带 checkpoint 结构和客观内容要求的循环式文档或 playbook 改写任务

## 最新发布证据

当前公开发布结论：`GO`。

最新两次重型测试：

- 通用任务重型 `20260415_110636_t2_refresh`：聚合 token 优化 `31.78%`，聚合时间优化 `54.12%`，质量差值 `+0.75`
- 预发布重型 `20260413_152717`：聚合 token 优化 `66.35%`，聚合时间优化 `71.16%`，质量差值 `+5.00`

建议先读 [benchmark/summary.zh-CN.md](benchmark/summary.zh-CN.md)，再看最新中文公开报告 [benchmark/hybrid_general_task_public_report_zh_latest.md](benchmark/hybrid_general_task_public_report_zh_latest.md)。

## 更新说明

这是当前 ACL-X hybrid 策略的正式公开更新版本。

- 当前 release 口径仍然坚持质量优先：在已验证测试集上，输出质量不能下降。
- 现阶段的主要优化目标仍然是耗时。
- 后续版本会继续在当前版本基础上加强时间优化与 token 优化，尤其会继续提升 `t3` 的 token 表现并保持当前更强的 `t2` 收益。
- 欢迎大家提交使用反馈、失败样例和 benchmark 对比结果。

## 各层级适用场景

| 层级 | 何时选择 | Bridge 模式 | 典型任务 |
| --- | --- | --- | --- |
| `t0` | 无真实 handoff、无共享机器状态、无循环的单表面任务 | `none` | 读取一个文件并返回严格短摘要 |
| `t1` | 恰好一次真实 handoff 或一次子代理审查 | `bundle` | 检查目标并输出一份结构化审查结果 |
| `t2` | 带可复用机器状态、工件契约或 2+ handoff 的多步本地修复任务 | `session` | 修代码、重跑测试并写出共享状态工件 |
| `t3` | 带 checkpoint、resume、replay 或 repeated verification 的循环型任务 | `session` | 改写 playbook 或 skill，并保持循环不变量 |

更细的路由规则见 [STRATEGY.md](STRATEGY.md) 与 [docs/routing_decision_tree.md](docs/routing_decision_tree.md)。

## 快速开始

1. 克隆仓库。
2. 安装 editable checkout：

   ```powershell
   python -m pip install -e .
   ```

3. 如果你需要带 PDF 的正式报告，安装可选依赖：

   ```powershell
   python -m pip install -e ".[formal,reports]"
   ```

4. 运行一个最小示例：

   ```powershell
   python examples/t0_summary.py
   ```

5. 跑完整单测：

   ```powershell
   python -m unittest discover -s tests -q
   ```

当前正式支持的公开工作流：

- 源码 checkout 后执行 `python -m unittest ...`
- 通过 `python -m pip install -e .` 做 editable install

## Agent 兼容性

- 当前发布版里的默认启用安装是 Codex 专用。
- 其他 agent 宿主仍然可以手动复用 ACL-X 的协议、prompt 和 runtime 组件，但本仓库还没有为它们提供打包好的默认安装器。
- 如果要对外描述“默认启用”能力，请先阅读 [docs/agent_compatibility.zh-CN.md](docs/agent_compatibility.zh-CN.md)。

## 基准测试快照

| 套件 | Run ID | Tokens | Time | Quality | 建议这样理解 |
| --- | --- | ---: | ---: | ---: | --- |
| 预发布重型 | `20260413_152717` | `+66.35%` | `+71.16%` | `+5.00` | 带显式工件契约的有边界本地工程任务 |
| 通用任务重型 | `20260415_110636_t2_refresh` | `+31.78%` | `+54.12%` | `+0.75` | 带验证器和明确闭环条件的通用结构化任务 |

## 优化优先级

- 对外发布口径应将 hybrid 视为“质量优先”策略：只有在验证集上平均输出质量持平或更好时，release claim 才成立。
- 主要优化目标是耗时，而不是 token。
- token 表现按 tier 分化，应当引用下面两次重型测试的结果，而不是宣传成普遍性的 token 优化。

| 层级 | 路由类型 | 推荐表述 | 预发布重型 `20260413_152717` | 通用任务重型 `20260415_110636_t2_refresh` |
| --- | --- | --- | --- | --- |
| `t0` | 无真实 handoff、无共享机器状态、无循环的单表面任务 | 这是精确性优先层。聚合收益可能存在，但在极小固定格式任务上仍然对噪声敏感。 | token `-46.73%`，time `+31.89%`，quality `+5.00` | token `+7.21%`，time `+3.38%`，quality `+0.00` |
| `t1` | 恰好一次真实 handoff 或一次子代理审查 | 这是当前公开证据里最稳定的低风险 token 与时间双重优化层。 | token `+76.08%`，time `+79.52%`，quality `+0.00` | token `+40.79%`，time `+66.79%`，quality `+0.00` |
| `t2` | 带可复用机器状态、工件契约或 2+ handoff 的多步本地修复任务 | 当显式工件契约和验证器存在时，这一层已经可以支撑更强的公开效率表述。时间仍是主目标，但新的公开通用任务结果里 token 也有较强收益。 | token `+74.37%`，time `+70.96%`，quality `+15.00` | token `+48.26%`，time `+61.36%`，quality `+0.00` |
| `t3` | 带 checkpoint、resume、replay 或 repeated verification 的循环型任务 | 这是时间优先、质量优先于 token 的层级。聚合 token 收益仍小于 `t1` 和当前刷新后的 `t2`。 | token `+25.48%`，time `+58.51%`，quality `+0.00` | token `+7.84%`，time `+39.15%`，quality `+3.00` |

这些数字是两轮重型测试的 tier 聚合结果，不代表该 tier 下每个任务都会呈现同样的 token 方向。当前 `t1` 仍是最稳定的低风险双重优化层；刷新后的 `t2` 现在也可以支撑更强的公开效率表述；`t3` 更适合表述为“时间优先，token 收益较小”；`t0` 更适合表述为“精确性优先，而非 token 优先”。

## 已知限制

- 四层级分类器是一种由运行时结构驱动的启发式规则，不是对任务含义或业务价值的通用分类学。
- 同一个用户请求在获得显式文件、共享机器状态、loop checkpoint 或 resume 需求后，可能跨层级变化。
- 混合型任务在边界处不稳定，尤其是在执行过程中才出现验收条件时。
- 当前 benchmark 不能替代开放式网页研究、创意写作、产品策略、生产运维或高度依赖人类隐性上下文的工作流。
- 本仓库中的 ACL-X 约束的是可见运行时状态，而不是模型内部隐藏推理。
- `t2` 与 `t3` 需要命名工件和显式约束；缺少这些条件时，supervisor 会退回 `t0`。

## 仓库导读

- [benchmark/summary.zh-CN.md](benchmark/summary.zh-CN.md)：最新中文 benchmark 总览
- [benchmark/summary.md](benchmark/summary.md)：最新英文 benchmark 总览
- [benchmark/hybrid_general_task_public_report_zh_latest.md](benchmark/hybrid_general_task_public_report_zh_latest.md)：最新中文公开重型报告
- [benchmark/hybrid_general_task_public_report_en_latest.md](benchmark/hybrid_general_task_public_report_en_latest.md)：最新英文公开重型报告
- [docs/release_update_v0.3.4.zh-CN.md](docs/release_update_v0.3.4.zh-CN.md)：`v0.3.4` 正式更新说明
- [docs/release_update_v0.3.4.md](docs/release_update_v0.3.4.md)：`v0.3.4` release update notes
- [docs/release_validation_latest.zh-CN.md](docs/release_validation_latest.zh-CN.md)：最新中文预发布重型报告
- [docs/release_validation_latest.md](docs/release_validation_latest.md)：最新英文预发布重型报告
- [docs/agent_compatibility.zh-CN.md](docs/agent_compatibility.zh-CN.md)：Agent 兼容性与默认安装边界说明
- [docs/agent_compatibility.md](docs/agent_compatibility.md)：英文 Agent 兼容性说明
- [docs/launch_announcement.zh-CN.md](docs/launch_announcement.zh-CN.md)：中文更新公告文案包
- [docs/launch_announcement.md](docs/launch_announcement.md)：英文更新公告文案包
- [STRATEGY.zh-CN.md](STRATEGY.zh-CN.md)：中文 tier 策略说明
- [STRATEGY.md](STRATEGY.md)：英文 tier 策略说明
- [RUNTIME_GUIDE.zh-CN.md](RUNTIME_GUIDE.zh-CN.md)：中文运行时挂接与升级规则
- [RUNTIME_GUIDE.md](RUNTIME_GUIDE.md)：英文运行时挂接与升级规则
- [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)：中文本地 setup、测试与 benchmark 刷新命令
- [CONTRIBUTING.md](CONTRIBUTING.md)：英文贡献指南
- [RELEASE_CHECKLIST.zh-CN.md](RELEASE_CHECKLIST.zh-CN.md)：中文发布核对清单
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)：英文发布核对清单
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)：协作行为规范
- [SECURITY.md](SECURITY.md)：安全问题提交流程
