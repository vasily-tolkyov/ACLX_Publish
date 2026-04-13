# Routing Matrix

Use this matrix to choose one or more retained custom agents.

Interpretation:

- `Primary agent set` is the best starting execution group
- `Support agents` are optional additions for review, testing, debugging, or coordination
- `Typical split` describes how to separate responsibilities when the task is large enough to justify multiple subagents

## Feature delivery

| Signal | Primary agent set | Support agents | Typical split |
|---|---|---|---|
| Next.js feature | `nextjs-developer` | `reviewer`, `backend-developer` | page or app work, API work, review |
| React feature | `react-specialist` | `browser-debugger`, `reviewer` | UI implementation, browser validation, review |
| Vue feature | `vue-expert` | `reviewer` | component work, review |
| Angular feature | `angular-architect` | `reviewer` | architecture or feature work, review |
| Generic frontend feature | `frontend-developer` | `ui-fixer`, `browser-debugger`, `reviewer` | implementation, browser debugging, review |
| Backend API feature | `backend-developer` | `api-designer`, `reviewer` | contract design, service implementation, review |
| Full feature touching UI and API | `fullstack-developer` | `reviewer`, `test-automator` | frontend lane, backend lane, verification lane |
| Contract-first API design | `api-designer` | `backend-developer`, `reviewer` | contract, implementation, review |
| Python automation or tool | `python-pro` | `tooling-engineer`, `test-automator` | core logic, tooling polish, tests |
| PowerShell automation or tool | `powershell-7-expert` or `powershell-5.1-expert` | `powershell-module-architect` | script logic, module structure |
| Windows admin automation | `windows-infra-admin` | `powershell-5.1-expert`, `azure-infra-engineer` | admin workflow, script compatibility, platform specifics |
| MCP integration | `mcp-developer` | `python-pro`, `reviewer` | protocol integration, local implementation, review |
| CLI productization | `cli-developer` | `tooling-engineer`, `reviewer` | command UX, packaging or tooling, review |

## Bug fixing and debugging

| Signal | Primary agent set | Support agents | Typical split |
|---|---|---|---|
| Browser-only frontend bug | `browser-debugger` | the chosen frontend framework agent, `reviewer` | repro or debug, code fix, review |
| UI bug with clear fix surface | `ui-fixer` | the chosen frontend framework agent | minimal patch, framework consistency |
| Hard runtime bug | `debugger` | the concrete stack agent for the affected code, `error-detective` | reproduction, root cause isolation, implementation |
| Error-pattern investigation | `error-detective` | the concrete stack agent for the affected code | log or error analysis, targeted fix |
| General backend defect | `backend-developer` | `reviewer`, `test-automator` | implementation, regression tests, review |
| Python automation defect | `python-pro` | `debugger`, `test-automator` | fix, debugging support, tests |
| PowerShell defect | `powershell-7-expert` or `powershell-5.1-expert` | `debugger`, `windows-infra-admin` | script fix, repro or debug, environment handling |

## Review and quality

| Signal | Primary agent set | Support agents | Typical split |
|---|---|---|---|
| PR-style review | `reviewer` | `code-reviewer` | correctness review, implementation review |
| Code-quality review | `code-reviewer` | `reviewer` | code-level findings, risk validation |
| Test planning | `qa-expert` | the concrete stack agent for the affected code | strategy, implementation guidance |
| Test implementation | `test-automator` | the concrete stack agent for the affected code, `qa-expert` | test code, stack-specific adjustments, coverage review |
| Performance issue | `performance-engineer` | the concrete stack agent for the affected code | measurement, optimization |
| Security review | `security-auditor` | `reviewer`, `security-engineer` | app review, risk review, infra implications |
| Accessibility review | `accessibility-tester` | frontend specialist, `browser-debugger` | audit, implementation fixes, browser validation |

## Refactor and modernization

| Signal | Primary agent set | Support agents | Typical split |
|---|---|---|---|
| Repository understanding first | `code-mapper` | the concrete stack agent for the affected code | structure map, implementation |
| Structural refactor | `refactoring-specialist` | `reviewer`, `test-automator` | refactor, review, regression tests |
| Legacy cleanup or upgrade | `legacy-modernizer` | the concrete stack agent for the affected code, `reviewer` | modernization plan, targeted implementation, review |
| Dependency or tooling cleanup | `tooling-engineer` | `dependency-manager`, `build-engineer` | tooling changes, dependency work, build verification |

## Infra and operations

| Signal | Primary agent set | Support agents | Typical split |
|---|---|---|---|
| CI/CD or automation | `devops-engineer` | `build-engineer`, `reviewer` | pipeline changes, build validation, review |
| Deployment path | `deployment-engineer` | `devops-engineer`, `sre-engineer` | deployment changes, pipeline work, rollout safety |
| Docker or container work | `docker-expert` | `devops-engineer`, `reviewer` | container changes, CI or deploy alignment, review |
| Cloud architecture | `cloud-architect` | `security-engineer`, `sre-engineer` | architecture, security posture, reliability |
| Reliability or ops | `sre-engineer` | `incident-responder`, `performance-monitor` | reliability plan, incident handling, monitoring |
| Windows or Azure operations | `azure-infra-engineer` | `windows-infra-admin`, `powershell-5.1-expert` | Azure lane, Windows lane, scripting |

## Data, AI, and research

| Signal | Primary agent set | Support agents | Typical split |
|---|---|---|---|
| LLM app design | `llm-architect` | `ai-engineer`, `prompt-engineer` | architecture, app implementation, prompt tuning |
| General AI feature | `ai-engineer` | `prompt-engineer`, `reviewer` | feature implementation, prompt work, review |
| Prompt tuning | `prompt-engineer` | `llm-architect` | prompt optimization, architecture sanity check |
| Data pipeline | `data-engineer` | `database-administrator`, `sql-pro` | pipeline work, DB ops, query work |
| Query tuning | `sql-pro` | `database-optimizer`, `postgres-pro` | query rewrite, optimization, database-specific tuning |
| PostgreSQL work | `postgres-pro` | `sql-pro`, `database-optimizer` | database-specific changes, SQL work, tuning |
| Docs lookup | `docs-researcher` | `search-specialist`, `knowledge-synthesizer` | source reading, broader search, synthesis |
| Broad web research | `search-specialist` | `research-analyst`, `knowledge-synthesizer` | source collection, analysis, synthesis |
| Multi-source synthesis | `knowledge-synthesizer` | `research-analyst`, `docs-researcher` | synthesis, analysis, source grounding |

## Coordination

| Signal | Primary agent set | Support agents | Typical split |
|---|---|---|---|
| Long multi-agent effort | `multi-agent-coordinator` | `workflow-orchestrator`, `context-manager` | coordination, workflow sequencing, context continuity |
| Work package splitting | `task-distributor` | `multi-agent-coordinator` | decomposition, supervision |
| Context cleanup and continuity | `context-manager` | `knowledge-synthesizer` | context maintenance, recap synthesis |
| Agent-set maintenance | `agent-organizer` | `agent-installer` | agent inventory, installation or cleanup |
