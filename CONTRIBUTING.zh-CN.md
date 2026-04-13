# 贡献指南

英文版见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 提 Issue 之前

请提供足够的信息，让人能够在本地复现路由或运行时行为：

- 完整任务文本，或最小化脱敏后的等价文本
- 预期 tier 与实际被路由到的 tier
- 你提供过的 `outputs`、`constraints`、`stop_conditions`、`expected_handoffs`、`expected_rounds`、`child_agents`
- 你执行的命令
- 相关工件路径、prompt 片段，或 benchmark/report 路径

高质量 issue 通常至少包含下面之一：

- `tests/fixtures/` 下的一个最小 fixture
- 一个失败的单元测试
- 生成 prompt 与文档契约之间的一个明确不匹配

## Pull Request

- 尽量让每个 PR 只覆盖一个行为变化。
- 每次改动 routing、prompt 形状或 artifact contract 时，都补充或更新测试。
- 如果修改了发布面对外文档，请保持对应 `zh-CN` 镜像同步。
- 如果触及 `configs/hybrid_router_map.yaml`、`src/aclx/hybrid.py` 或 `src/aclx/supervisor.py`，请重新运行 routing 与 supervisor 测试。
- 如果有意修改了被 strategy lock 覆盖的策略文件，请更新 `configs/strategy_lock.json`，并在 PR 描述里说明原因。
- 不要提交 `artifacts/`、`tmp/`、`output/` 或 `tests/formal/runs/` 下的大型临时目录。只提交已经整理好的 `benchmark/` 与 `docs/` 文件。

## 本地安装

Editable install：

```powershell
python -m pip install -e .
```

如果需要带 PDF 的正式报告，安装可选依赖：

```powershell
python -m pip install -e ".[formal,reports]"
```

## 测试命令

完整单元测试门禁：

```powershell
python -m unittest discover -s tests -q
```

定向 routing 门禁：

```powershell
python -m unittest tests.test_hybrid tests.test_supervisor tests.test_strategy_lock tests.test_t23_real_ab_runner -q
```

轻量发布验证：

```powershell
python scripts/release_validation_ab.py
```

重型预发布运行：

```powershell
python tests/formal/run_hybrid_pre_release_heavy.py
```

重型通用任务运行：

```powershell
python tests/formal/run_hybrid_general_task_heavy.py
```

从通用任务汇总渲染中英双语公开报告：

```powershell
python tests/formal/render_hybrid_general_task_public_reports.py benchmark/hybrid_general_task_heavy_latest.json
```

## Benchmark 变更

如果你的 PR 修改了路由语义或 prompt 打包，请说明：

- 改了什么
- 预计哪些 tier 会变化
- headline benchmark 数字是否应变化
- 你重新运行了哪份报告

整理后的公开 benchmark 工件索引以 [benchmark/summary.zh-CN.md](benchmark/summary.zh-CN.md) 为准。

## 打包说明

- `python -m pip install -e .` 是正式支持的公开工作流。
- 如果改动了打包逻辑，请确认 editable install 仍然可用，并重新运行完整单测门禁。
- wheel 可移植性还不是当前的首要验证发布路径；源码 checkout 与 editable install 仍是参考工作流。
- 当前“默认启用”的打包安装路径仅针对 Codex。如果你改动了 share-pack 安装行为或宿主默认策略，请同步更新 `docs/agent_compatibility.md` 与 `docs/agent_compatibility.zh-CN.md`。
