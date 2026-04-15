# Changelog

## v0.3.3 - 2026-04-15

- Refreshed the public GitHub benchmark package with the merged general-task heavy run `20260415_110636_t2_refresh`.
- Replaced the previously weak public `t2` slice with the repaired `t2` benchmark results, lifting the published `t2` aggregate to `48.26%` token optimization and `61.36%` time optimization with no quality regression.
- Synchronized the public source tree, tier configs, adapter/runtime files, and behavior-locking tests to the current locked hybrid strategy state.
- Updated the release-facing README, benchmark summary, and latest English and Chinese public reports to the new headline numbers.

## v0.3.2 - 2026-04-14

- Aligned the formal release line with the current `main` branch state.
- Carried forward the post-release Chinese launch-copy wording sync into the formal public release version.
- Promoted the aligned public release as `v0.3.2`.

## v0.3.1 - 2026-04-13

- Fixed the public release line after the initial `v0.3.0` tag exposed cross-platform GitHub Actions failures.
- Normalized strategy-lock and contract-source handling so line-ending differences and Windows short paths no longer cause false drift or missing `TASK.md` contract loads.
- Fixed share-pack verification across Windows and Unix launcher layouts.
- Added regression coverage for cross-platform contract parsing and share-pack validation behavior.
- Promoted the repaired formal public release as `v0.3.1`.

## v0.3.0 - 2026-04-13

- Formal first public GitHub release for the current ACL-X hybrid strategy.
- Refreshed the public release tree for GitHub publication under `D:\ACLX_Publish`, including portable scripts, tests, `share_pack/` assets, and standard repository metadata.
- Made the public editable-install workflow work with `python -m pip install -e .`.
- Added `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue templates, a PR template, `.gitignore`, and `MANIFEST.in`.
- Published new heavy benchmark artifacts from pre-release run `20260413_152717` and general-task run `20260413_160451`.
- Updated public benchmark summaries, README release messaging, and checklist references to the latest results.
- Added explicit host-compatibility documentation clarifying that default-on installation is currently Codex-specific while other agent hosts require manual integration.
- Added launch messaging that states the near-term roadmap clearly: keep quality flat or better, continue strengthening time optimization, continue improving token optimization, and welcome user feedback.

## v0.2.0 - 2026-04-08

- Initial public release candidate for ACL-X as a compact communication language and visible runtime for AI agents.
- Benchmarks staged from formal run `20260408_184824`.
- Added release-facing README, strategy documentation, contribution guide, minimal examples, benchmark summaries, and CI template.
