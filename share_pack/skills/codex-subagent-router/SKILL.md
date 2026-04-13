---
name: codex-subagent-router
description: Use when a task involves choosing, routing, or delegating work to installed Codex custom agents. Prefer the user's curated local agent subset for Python, PowerShell, Windows automation, frontend frameworks, backend/fullstack work, review, debugging, DevOps, data or AI, and research tasks. Allow adaptive multi-agent delegation with no fixed upper limit, and avoid deleted or niche agents unless the user explicitly asks for them.
---

# Codex Subagent Router

Use this skill as the default routing and delegation policy whenever the main Codex agent is about to choose custom subagents.

## Mission

This skill exists to make subagent selection predictable.

It should help the main agent:

- prefer the user's curated local agents over broad or niche alternatives
- choose one or many subagents based on the real task structure
- avoid arbitrary caps on agent count
- split work by stack, phase, module, or risk boundary when that improves clarity
- keep each spawned subagent narrowly scoped
- avoid deleted agents and avoid niche retained agents unless the task clearly calls for them

## Core policy

This skill does not limit the main program to one child agent.

Default rule:

- use 1 agent for small, single-surface work
- use 2 agents when there is one natural split
- use 3-5 agents when there are several clearly independent lanes
- use 6 or more agents only when the task behaves like a real multi-module or multi-phase project
- do not impose a fixed upper limit on subagent count

When in doubt, choose the smallest agent set that preserves clarity and forward progress.

## Routing workflow

1. Classify the task:
   - feature delivery
   - bug fix
   - code review
   - debugging
   - test work
   - refactor or modernization
   - tooling or automation
   - infrastructure or deployment
   - data or AI
   - research or documentation
   - multi-stage project orchestration
2. Detect the strongest stack signal from file types, framework markers, repository structure, and user wording.
3. Decide whether the work is:
   - single-surface
   - cross-stack
   - multi-phase
   - risk-separated
   - parallelizable
4. Choose one or more primary agents using [references/routing-matrix.md](references/routing-matrix.md).
5. Add support agents only when they own a clear non-overlapping lane.
6. Keep the final set small enough to coordinate, but large enough to match the actual task structure.

## Runtime tier gate

Before spawning subagents, apply the default hard runtime classifier:

- `t0`: single-surface work, no real handoff, no shared machine state, no loop
- `t1`: exactly one real handoff or one shared package
- `t2`: 2+ handoffs, 2+ child agents, or reusable machine state across steps
- `t3`: loop, repeated resume, checkpoint/replay flow, or repeated rounds

Rules:

- start at `t0`
- promote only from actual runtime structure, not from ACL-X vocabulary alone
- if the task only writes, ports, audits, or configures a skill/router/protocol, keep `t0`
- do not spawn subagents just because the task discusses subagents as content

## Required subagent specification

When this skill leads to spawning or proposing subagents, do not return only a loose list of agent names.

For each subagent, define all of the following:

- `agent_type`: the concrete installed agent name
- `lane`: one short responsibility label
- `goal`: the exact outcome this agent owns
- `scope_in`: what it may change or investigate
- `scope_out`: what it must not own
- `inputs`: files, modules, facts, or dependencies it should start from
- `outputs`: what it must return
- `handoff_to`: which later lane or reviewer consumes the result
- `stop_conditions`: when it should stop and escalate instead of guessing

If any of these fields is missing, the subagent template is incomplete.

## Subagent output template

When generating a plan for multiple subagents, prefer this exact structure:

```text
Task type: <type>
Agent count: <n>

Agent 1
- agent_type: <installed-agent-name>
- lane: <short-lane-name>
- goal: <owned outcome>
- scope_in: <allowed scope>
- scope_out: <excluded scope>
- inputs: <starting context>
- outputs: <expected result>
- handoff_to: <next lane or none>
- stop_conditions: <when to stop>

Agent 2
- agent_type: <installed-agent-name>
- lane: <short-lane-name>
- goal: <owned outcome>
- scope_in: <allowed scope>
- scope_out: <excluded scope>
- inputs: <starting context>
- outputs: <expected result>
- handoff_to: <next lane or none>
- stop_conditions: <when to stop>
```

Do not use placeholder role labels in `agent_type`.

## Task decomposition decision tree

Use this before spawning subagents.

### Step 1. Can one agent handle it cleanly?

Stay with 1 agent if all of these are true:

- one clear stack or framework
- one main deliverable
- one tight file cluster or one tightly coupled module group
- no meaningful parallelism
- low review, migration, or rollout risk

Typical outcomes:

- `react-specialist`
- `backend-developer`
- `python-pro`
- `reviewer`

### Step 2. Is there one natural split?

Use 2 agents if any of these are true:

- execution and review should be separated
- frontend and backend are both involved
- implementation and testing are distinct
- debugging and fixing are better owned by different agents

Typical outcomes:

- executor plus `reviewer`
- `react-specialist` plus `backend-developer`
- `python-pro` plus `test-automator`
- `debugger` plus the concrete stack agent chosen for the codebase

### Step 3. Are there several independent lanes?

Use 3-5 agents if two or more of these are true:

- multiple stacks are involved
- there is a dedicated testing lane
- there is a dedicated review, security, or performance lane
- deployment or migration is part of the same task
- repo discovery or research is needed before implementation
- at least two workstreams can proceed in parallel

Typical outcomes:

- frontend plus backend plus `reviewer`
- `code-mapper` plus executor plus `reviewer`
- executor plus `test-automator` plus `reviewer`
- `devops-engineer` plus `deployment-engineer` plus `sre-engineer`
- `llm-architect` plus `prompt-engineer` plus `ai-engineer`

### Step 4. Is this a real project rather than a task?

Use 6 or more agents only when the work behaves like a project, for example:

- several modules, services, or apps need independent ownership
- one large repo contains multiple distinct domains
- implementation, testing, review, deployment, documentation, and research all need separate lanes
- some lanes can start immediately while others depend on earlier outputs
- coordination itself becomes a real responsibility

When you go to 6 or more agents:

- add `multi-agent-coordinator`, `workflow-orchestrator`, or `task-distributor` only if coordination is genuinely needed
- assign each agent to one module, one phase, or one risk boundary
- avoid spawning several generic agents for the same stack without distinct ownership
- prefer explicit lanes such as frontend, backend, tests, review, deploy, docs, research, or migration

### Stop conditions

Do not add another agent if:

- the new agent would touch the same scope without a clear separation of responsibility
- coordination cost is higher than the likely speedup
- the task is blocked on one critical path and parallelism would be fake
- the extra agent exists only because many agents feel impressive

### Final check before spawning

Before finalizing the agent set, confirm:

- each agent has one clear lane
- the set covers the task without major overlap
- at least one agent owns verification when risk is non-trivial
- the number of agents matches the actual structure of the work

## Category-adaptive routing

### Frontend

When the framework is clear, prefer:

- `nextjs-developer` for Next.js
- `react-specialist` for React
- `vue-expert` for Vue
- `angular-architect` for Angular
- `frontend-developer` only when the work is frontend but no framework specialist is clearly indicated

Typical patterns:

- the chosen frontend framework agent plus `reviewer`
- the chosen frontend framework agent plus `browser-debugger`
- the chosen frontend framework agent plus `ui-fixer`
- the chosen frontend framework agent plus `backend-developer` for integrated features

### Python, PowerShell, Windows automation, and tooling

Prefer:

- `python-pro`
- `powershell-5.1-expert`
- `powershell-7-expert`
- `powershell-module-architect`
- `powershell-ui-architect`
- `cli-developer`
- `tooling-engineer`
- `mcp-developer`
- `windows-infra-admin`
- `azure-infra-engineer`

Typical patterns:

- `python-pro` plus `tooling-engineer`
- `powershell-7-expert` plus `powershell-module-architect`
- `powershell-5.1-expert` plus `windows-infra-admin`
- `mcp-developer` plus `python-pro` plus `reviewer`

### Backend and fullstack

When no narrower specialist is clearly better, prefer:

- `backend-developer`
- `fullstack-developer`
- `api-designer`
- `code-mapper`
- `refactoring-specialist`
- `legacy-modernizer`

Typical patterns:

- `api-designer` plus `backend-developer`
- `fullstack-developer` plus `reviewer`
- `code-mapper` plus the concrete stack agent chosen for the repo plus `reviewer`
- `refactoring-specialist` plus `test-automator`

### Quality, debugging, and testing

Use these as support lanes or, when the task is explicitly quality-led, as primary lanes:

- `reviewer`
- `code-reviewer`
- `debugger`
- `error-detective`
- `qa-expert`
- `test-automator`
- `performance-engineer`
- `security-auditor`
- `browser-debugger`
- `accessibility-tester`

Typical patterns:

- executor plus `reviewer`
- executor plus `debugger` plus `test-automator`
- frontend specialist plus `browser-debugger` plus `accessibility-tester`
- backend specialist plus `security-auditor` plus `performance-engineer`

### Infra, deployment, and operations

Prefer:

- `devops-engineer`
- `deployment-engineer`
- `docker-expert`
- `cloud-architect`
- `sre-engineer`
- `incident-responder`
- `security-engineer`
- `windows-infra-admin`
- `azure-infra-engineer`

Do not default to deleted deep-specialist agents such as Kubernetes or Terraform specialists.

Typical patterns:

- `devops-engineer` plus `deployment-engineer`
- `docker-expert` plus `devops-engineer`
- `cloud-architect` plus `security-engineer` plus `sre-engineer`
- `azure-infra-engineer` plus `windows-infra-admin`

### Data, AI, and research

Prefer:

- `ai-engineer`
- `llm-architect`
- `prompt-engineer`
- `data-engineer`
- `data-analyst`
- `database-administrator`
- `database-optimizer`
- `sql-pro`
- `postgres-pro`
- `docs-researcher`
- `search-specialist`
- `research-analyst`
- `knowledge-synthesizer`

Typical patterns:

- `llm-architect` plus `prompt-engineer`
- `data-engineer` plus `sql-pro` plus `database-optimizer`
- `docs-researcher` plus `search-specialist` plus `knowledge-synthesizer`
- `ai-engineer` plus `reviewer`

### Orchestration

Use orchestration-oriented agents only when the task is genuinely multi-agent or coordination-heavy:

- `multi-agent-coordinator`
- `workflow-orchestrator`
- `task-distributor`
- `context-manager`
- `error-coordinator`
- `performance-monitor`
- `agent-organizer`
- `agent-installer`

These agents do not replace execution specialists. They structure larger runs.

## 中文速查表

管理 agent 在分派时，优先按下面这张表判断。

| 任务类型 | 优先 agent | 常见补充 agent |
|---|---|---|
| Next.js 页面或全栈功能 | `nextjs-developer` | `reviewer`, `backend-developer` |
| React 页面或组件 | `react-specialist` | `browser-debugger`, `reviewer` |
| Vue 页面或组件 | `vue-expert` | `reviewer` |
| Angular 前端工程 | `angular-architect` | `reviewer` |
| 通用前端需求 | `frontend-developer` | `ui-fixer`, `browser-debugger` |
| 后端接口或服务 | `backend-developer` | `api-designer`, `reviewer` |
| 小型前后端联动需求 | `fullstack-developer` | `reviewer` |
| API 契约设计 | `api-designer` | `backend-developer` |
| Python 自动化或本地工具 | `python-pro` | `tooling-engineer`, `test-automator` |
| PowerShell 7 自动化 | `powershell-7-expert` | `powershell-module-architect` |
| PowerShell 5.1 兼容脚本 | `powershell-5.1-expert` | `windows-infra-admin` |
| PowerShell 模块化改造 | `powershell-module-architect` | `powershell-7-expert` |
| MCP 或代理集成 | `mcp-developer` | `python-pro`, `reviewer` |
| CLI 工具开发 | `cli-developer` | `tooling-engineer` |
| 工程化或开发工具链 | `tooling-engineer` | `build-engineer`, `reviewer` |
| 仓库结构梳理 | `code-mapper` | 对应栈 agent |
| 重构或整理旧代码 | `refactoring-specialist` | `legacy-modernizer`, `test-automator` |
| 代码评审 | `reviewer` | `code-reviewer` |
| 实现质量审查 | `code-reviewer` | `reviewer` |
| 疑难 bug 排查 | `debugger` | 对应栈 agent |
| 错误定位与原因分析 | `error-detective` | 对应栈 agent |
| 自动化测试补齐 | `test-automator` | `qa-expert`, 对应栈 agent |
| 测试方案设计 | `qa-expert` | 对应栈 agent |
| 浏览器端问题排查 | `browser-debugger` | 前端框架 agent |
| 无障碍检查 | `accessibility-tester` | 前端框架 agent |
| 性能优化 | `performance-engineer` | 对应栈 agent |
| 安全审查 | `security-auditor` | `reviewer` |
| 部署或 CD 流程 | `deployment-engineer` | `devops-engineer` |
| CI/CD 与自动化运维 | `devops-engineer` | `build-engineer`, `docker-expert` |
| Docker 容器相关 | `docker-expert` | `devops-engineer` |
| 云架构或稳定性 | `cloud-architect` | `sre-engineer`, `security-engineer` |
| Windows 或 Azure 运维 | `azure-infra-engineer` | `windows-infra-admin` |
| AI 应用开发 | `ai-engineer` | `llm-architect`, `prompt-engineer` |
| LLM 架构设计 | `llm-architect` | `prompt-engineer` |
| Prompt 优化 | `prompt-engineer` | `llm-architect` |
| 数据管道或处理 | `data-engineer` | `database-administrator` |
| SQL 或查询优化 | `sql-pro` | `database-optimizer` |
| PostgreSQL 相关 | `postgres-pro` | `sql-pro` |
| 文档检索 | `docs-researcher` | `search-specialist` |
| 网络搜索与资料搜集 | `search-specialist` | `research-analyst` |
| 多来源结论整合 | `knowledge-synthesizer` | `research-analyst` |
| 多 agent 项目编排 | `multi-agent-coordinator` | `workflow-orchestrator`, `task-distributor` |
| 长任务上下文整理 | `context-manager` | `multi-agent-coordinator` |

## Agents to avoid by default

These agents are not first-choice defaults unless the task explicitly calls for them:

- `blockchain-developer`
- `embedded-systems`
- `fintech-engineer`
- `game-developer`
- `iot-engineer`
- `m365-admin`
- `payment-integration`
- `quant-analyst`
- `risk-manager`
- `seo-specialist`
- `slack-expert`
- `api-documenter`
- `ad-security-reviewer`
- `chaos-engineer`
- `compliance-auditor`
- `penetration-tester`
- `powershell-security-hardening`
- `devops-incident-responder`
- `it-ops-orchestrator`
- `microservices-architect`
- `graphql-architect`
- `ui-designer`
- `websocket-engineer`

## Selection rules

- Prefer the most specific retained agent that matches the actual task.
- If both language and framework are known, framework wins for UI work and language wins for tooling work.
- If the task is mostly repository understanding, start with `code-mapper`.
- If the task is mostly implementation, start with execution specialists, not coordinators.
- If the task is mostly verification, start with `reviewer`, `debugger`, `qa-expert`, or `code-reviewer`.
- If the task is mostly docs lookup or synthesis, start with `docs-researcher`, `search-specialist`, or `knowledge-synthesizer`.
- If no routing choice is obvious, prefer `fullstack-developer`, `backend-developer`, `frontend-developer`, `python-pro`, or `tooling-engineer` based on the nearest signal.
- For large tasks, decompose by module, stack, or phase, and allow as many subagents as needed.
- Each spawned subagent should own one clear lane.

## Output expectations

When using this skill, state briefly:

- the detected task type
- whether the task needs one agent or many
- the chosen primary agent set
- any support agents and why
- any obvious agents intentionally not chosen
- the concrete per-agent template if subagents are being proposed or spawned

Keep the explanation short and move on to execution.
