# Hybrid 预发布重型测试报告（中文版）

- Run ID：`20260413_152717`
- 生成时间：`2026-04-13 16:04:35`
- 正式运行根目录：`D:\ACLX_Publish\tests\formal\runs\hybrid_pre_release_heavy_20260413_152717`
- Gate 测试通过：`True`
- 策略锁一致：`True`
- 发布建议：`GO`

英文原版见 [release_validation_latest.md](release_validation_latest.md)。

## 执行范围与注意事项

Hybrid 是一套面向有边界本地工作流的有限优化策略，并不是适用于任意通用任务的普遍优化方案。

这套策略仍然可以运行在通用任务上，但如果超出本报告已验证的任务族，就不能保证质量持平，也不能保证 token 或时间收益。

因此，这份报告应被理解为狭窄操作区间内的发布级证据，而不是对任意任务类型、任意复杂度的平均承诺。

## 方法

- 本次运行对比的是自然语言基线与当前 adaptive hybrid 策略。
- 测试套件包含 12 个本地重型任务，覆盖四个层级，每层 3 个任务。
- token 优先使用 Codex 报告的总 token；若缺失，则回退到提示词加可见输出的估算值。
- 质量使用任务级验证器并归一化到 0-100 分。
- 汇总还跟踪 contract family、adapter family、validator type、可恢复性覆盖和 exactness 覆盖，避免只按 tier 标签得出结论。

## 分类限制

- 四层级 hybrid 分类是一种由运行时结构驱动的启发式规则，不是对任务含义或业务价值的通用分类学。
- 同一个用户请求在获得显式文件、可复用 handoff 状态、loop checkpoint 或 resume 需求后，可能跨层级变化。
- 混合型任务在边界处尤其不稳定。一个初始很短的只读任务，一旦在执行中引入新的验收条件，就可能变成多步修复或 loop-heavy 工作流。
- 当真实成功条件存在于 prompt 之外、工作区之外或验证器无法检查的工件之外时，分类可靠性会下降。

## 推荐任务族

- 带严格输出格式和显式字面量要求的本地文件读取或摘要任务
- 恰好一次真实 handoff 且必须写出明确工件的一次性审查任务
- 带命名文件、命名测试或命令、以及显式机器可读 handoff 工件的多步本地代码或配置修复任务
- 带 checkpoint 结构和客观内容要求的循环式文档或 playbook 改写任务

## 不应把本报告当作代理证据的任务族

- 范围会在执行中变化的开放式网页研究、产品策略或探索性规划
- 创意生成、风格驱动写作，或质量主要依赖主观判断而非验证器的任务
- 生产运维、远程系统工作，或由网络延迟、审批、外部服务主导的工作流
- 人类强参与、隐性上下文比 prompt 契约和本地工件纪律更重要的任务

## 发布口径指引

- hybrid 的对外表述应以“质量不降”为先，只有验证集上的平均输出质量持平或更好时，release claim 才成立。
- 主要优化目标是耗时，而不是 token。
- token 表现按 tier 分化，应引用两次重型测试的分层结果，而不是宣传成普遍性的 token 优化。

| 层级 | 路由类型 | 推荐表述 | 预发布重型 `20260413_152717` | 通用任务重型 `20260413_160451` |
| --- | --- | --- | --- | --- |
| `t0` | 无真实 handoff、无共享机器状态、无循环的单表面任务 | 精确性优先层。耗时可以改善，但在微小固定格式任务上，token 更倾向于退化。 | token `-46.73%`，time `+31.89%`，quality `+5.00` | token `-12.11%`，time `+29.62%`，quality `+0.00` |
| `t1` | 恰好一次真实 handoff 或一次子代理审查 | 当前证据里最明确的 token 和时间双重优化层。 | token `+76.08%`，time `+79.52%`，quality `+0.00` | token `+68.59%`，time `+72.69%`，quality `+0.00` |
| `t2` | 带可复用机器状态、工件契约或 2+ handoff 的多步本地修复任务 | 时间优先、质量优先于 token。token 收益依赖任务形态，不保证每个任务都优化。 | token `+74.37%`，time `+70.96%`，quality `+15.00` | token `+3.43%`，time `+47.28%`，quality `+0.00` |
| `t3` | 带 checkpoint、resume、replay 或 repeated verification 的循环型任务 | 时间优先、质量优先于 token。聚合 token 往往小于 `t1`，单任务也可能回退。 | token `+25.48%`，time `+58.51%`，quality `+0.00` | token `+10.84%`，time `+59.11%`，quality `+3.00` |

这些数字是两轮重型测试的 tier 聚合结果，不代表同一 tier 下每个任务都会在 token 上朝同一方向变化。

## 为什么 `t0` 可能出现负优化

在这轮正式运行里，`t0` 层聚合结果是 token `-46.73%`、time `+31.89%`，平均质量从 `95.00` 提升到 `100.00`。

负向 token 异常点主要来自：

- Three-line release notes summary：`-80.30%`
- Routing threshold brief：`-69.70%`

主要原因是 hybrid 固定控制开销。在极小的只读任务上，路由包装、输出保持约束和更严格的 prompt 契约，可能比任务本体还更耗 token。

这不代表质量失败。本轮中 `t0` 的 hybrid 输出质量持平或更好，只是由于任务体量太小，额外控制成本没有被摊薄。

## 任务选择

| 层级 | 组别 | 任务 | 代表性说明 |
| --- | ---: | --- | --- |
| t0 | 1 | Three-line release notes summary | 从简短 release notes 中抽取严格三行输出，带路径引用和两个命名事实。 |
| t0 | 2 | Routing threshold brief | 从小型阈值配置中输出固定格式 brief，强调格式与字面量保真。 |
| t0 | 3 | Operator note brief | 从简短 operator note 中抽取三行摘要，强调显式证据。 |
| t1 | 1 | Empty-input bug review | 一次真实 reviewer handoff 的轻量缺陷审查任务。 |
| t1 | 2 | Zero-sample bug review | 单次协调步骤、无复用状态的缺陷审查任务。 |
| t1 | 3 | Missing-route bug review | 单次 handoff 的结构化审查任务。 |
| t2 | 1 | Shared pipeline repair | 带代码修复、测试重跑和共享状态工件写出的多步工程修复任务。 |
| t2 | 2 | Reviewer queue repair | 带共享 handoff 工件的多步本地修复任务。 |
| t2 | 3 | Stage plan repair | 多个工件必须保持对齐的多步修复任务。 |
| t3 | 1 | Review loop playbook rewrite | 保持证据优先和 checkpoint 可恢复性的循环式文档改写任务。 |
| t3 | 2 | Release signoff handbook rewrite | 保持 blocker-first checkpoint 结构的循环式文档任务。 |
| t3 | 3 | Resume handoff guide rewrite | 保持恢复语义与未解决事项优先级的循环式连续性任务。 |

## 每任务指标

| Tier | Group | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Quality | Hybrid Quality | Quality Delta | Route OK |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| t0 | 1 | 3320 | 5986 | -80.30% | 19.15 | 23.73 | -23.93% | 85 | 100 | 15 | yes |
| t0 | 2 | 3541 | 6009 | -69.70% | 35.61 | 11.51 | 67.67% | 100 | 100 | 0 | yes |
| t0 | 3 | 3365 | 3010 | 10.55% | 18.49 | 14.65 | 20.79% | 100 | 100 | 0 | yes |
| t1 | 1 | 145690 | 13238 | 90.91% | 367.44 | 42.46 | 88.45% | 100 | 100 | 0 | yes |
| t1 | 2 | 5866 | 16279 | -177.51% | 336.45 | 95.65 | 71.57% | 100 | 100 | 0 | yes |
| t1 | 3 | 20236 | 11584 | 42.76% | 139.29 | 34.55 | 75.20% | 100 | 100 | 0 | yes |
| t2 | 1 | 33823 | 7342 | 78.29% | 208.84 | 61.57 | 70.52% | 85 | 100 | 15 | yes |
| t2 | 2 | 24039 | 11570 | 51.87% | 139.66 | 43.35 | 68.96% | 85 | 100 | 15 | yes |
| t2 | 3 | 48130 | 8251 | 82.86% | 147.95 | 39.24 | 73.48% | 85 | 100 | 15 | yes |
| t3 | 1 | 7308 | 8145 | -11.45% | 79.26 | 47.44 | 40.15% | 100 | 100 | 0 | yes |
| t3 | 2 | 17817 | 8487 | 52.37% | 118.22 | 45.19 | 61.78% | 100 | 100 | 0 | yes |
| t3 | 3 | 8283 | 8264 | 0.23% | 124.65 | 41.03 | 67.08% | 100 | 100 | 0 | yes |

## 分层聚合

| Tier | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Time (s) | Hybrid Time (s) | Time Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t0 | 3 | 10226 | 15005 | -46.73% | 73.24 | 49.89 | 31.89% | 95.00 | 100.00 | 5.00 |
| t1 | 3 | 171792 | 41101 | 76.08% | 843.19 | 172.66 | 79.52% | 100.00 | 100.00 | 0.00 |
| t2 | 3 | 105992 | 27163 | 74.37% | 496.45 | 144.16 | 70.96% | 85.00 | 100.00 | 15.00 |
| t3 | 3 | 33408 | 24896 | 25.48% | 322.13 | 133.66 | 58.51% | 100.00 | 100.00 | 0.00 |

## Contract Family 聚合

| Contract Family | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| generic_config_extract | 1 | 3541 | 6009 | -69.70% | 100.00 | 100.00 | 0.00 |
| loop_document_rewrite | 3 | 33408 | 24896 | 25.48% | 100.00 | 100.00 | 0.00 |
| read_extract | 2 | 6685 | 8996 | -34.57% | 92.50 | 100.00 | 7.50 |
| shared_state_repair | 3 | 105992 | 27163 | 74.37% | 85.00 | 100.00 | 15.00 |
| single_handoff_review | 3 | 171792 | 41101 | 76.08% | 100.00 | 100.00 | 0.00 |

## Adapter Family 聚合

| Adapter Family | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| docs | 5 | 40093 | 33892 | 15.47% | 97.00 | 100.00 | 3.00 |
| generic-fs | 1 | 3541 | 6009 | -69.70% | 100.00 | 100.00 | 0.00 |
| python | 6 | 277784 | 68264 | 75.43% | 92.50 | 100.00 | 7.50 |

## Validator Type 聚合

| Validator Type | Task Count | Baseline Tokens | Hybrid Tokens | Token Opt % | Baseline Avg Quality | Hybrid Avg Quality | Quality Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| document_exactness_and_checkpoint | 3 | 33408 | 24896 | 25.48% | 100.00 | 100.00 | 0.00 |
| exact_output | 3 | 10226 | 15005 | -46.73% | 95.00 | 100.00 | 5.00 |
| structured_review | 3 | 171792 | 41101 | 76.08% | 100.00 | 100.00 | 0.00 |
| unit_tests_and_artifacts | 3 | 105992 | 27163 | 74.37% | 85.00 | 100.00 | 15.00 |

## 覆盖率

- 可恢复性覆盖：`3/3` 任务，`100.00%`
- Exactness 保持覆盖：`9/12` 任务，`75.00%`

## 总体聚合

- Baseline 总 tokens：`321418`
- Hybrid 总 tokens：`108165`
- Token 优化：`66.35%`
- Baseline 总耗时：`1735.01`
- Hybrid 总耗时：`500.36`
- 时间优化：`71.16%`
- Baseline 平均质量：`95.00`
- Hybrid 平均质量：`100.00`
- 质量差值：`5.00`

## 结论

在本次预发布重型矩阵覆盖的有边界本地工程任务范围内，当前锁定版 hybrid 已达到公开发布条件。对外应将其描述为“质量优先、时间优先”的策略：平均输出质量不下降，耗时显著改善，而 token 表现仍按 tier 分化，不能泛化为每个任务都会优化。
