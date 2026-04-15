# 发布核对清单

英文版见 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。

## 发布前必须完成

- [x] `README.md` 已更新到最新验证范围与 benchmark 证据
- [x] `examples/` 中每个 tier 都有一个可运行最小示例
- [x] `CHANGELOG.md`
- [x] `LICENSE`
- [x] `CODE_OF_CONDUCT.md`
- [x] `SECURITY.md`
- [x] 宿主兼容性文档明确说明“默认启用安装”是 Codex 专用
- [x] `benchmark/` 下已有结构化 benchmark 工件
- [x] 最新的人类可读预发布重型报告以 `docs/` 为唯一权威入口
- [x] 关键发布文档已有中文镜像
- [x] `.github/` issue、PR 与 CI 模板已就绪

## 强烈建议完成

- [x] `STRATEGY.md`，涵盖 tier 触发条件、bundle 上限、bridge 模式与 override 规则
- [x] `CONTRIBUTING.md`
- [x] `benchmark/` 下已有机器可读公共 benchmark JSON
- [x] 已用 `python -m pip install -e .` 验证 editable install 工作流
- [x] 公开仓库已包含 `share_pack/` 资产

## 后续建议

- [x] `docs/routing_decision_tree.md`
- [x] `MANIFEST.in`，保证 source distribution 完整性
- [ ] 将 wheel 安装验证升级为一等正式支持工作流

## 说明

- 当前发布口径中的 headline benchmark 应来自通用任务运行 `20260415_110636_t2_refresh`。
- 最新有边界工程发布门禁应来自预发布运行 `20260413_152717`。
- 人类可读的预发布验证报告统一放在 `docs/`；`benchmark/` 仅保留机器可读汇总与 PDF 工件。
- `t0` 在极小固定格式任务上仍需谨慎：即使质量与时间可接受，token 与耗时结果也可能对噪声敏感。
- 发布文案必须区分“Codex 默认启用安装”和“其他 agent 宿主需要手动集成”。
