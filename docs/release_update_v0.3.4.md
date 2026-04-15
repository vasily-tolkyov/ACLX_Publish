# ACL-X v0.3.4 Release Update Notes

Chinese version: [release_update_v0.3.4.zh-CN.md](release_update_v0.3.4.zh-CN.md).

## Summary

`v0.3.4` is the current public patch release update for ACL-X. This update keeps the published benchmark headline unchanged, but hardens the public source tree and CI behavior so the synchronized release line now verifies consistently across both Windows and Linux.

## Headline Outcome

- General-task heavy run `20260415_110636_t2_refresh`: `31.78%` aggregate token improvement, `54.12%` aggregate time improvement, `+0.75` quality delta.
- Pre-release heavy run `20260413_152717`: `66.35%` aggregate token improvement, `71.16%` aggregate time improvement, `+5.00` quality delta.
- Public release stance remains quality-first and time-first. Token gains are real, but they remain tier-dependent rather than universal.

## What Changed

- Normalized strategy-lock hashing across line endings and checkout text normalization so public CI no longer fails on platform-only byte drift.
- Normalized project-root-relative path handling across Windows and Linux so bundle evidence, prompt hints, and locked assertions stay stable in both environments.
- Added a root-level `TASK.md` contract-source fallback for prompts that mention an absolute task path, preserving doc-loop exactness loading in CI.
- Aligned package metadata, changelog, README pointers, benchmark summary links, and release-copy pack to the new patch version.

## Release Messaging Guidance

- `t1` remains the clearest low-risk repeat win for both tokens and time.
- `t2` still supports the stronger public efficiency claim when explicit artifact contracts and validators are present.
- `t3` should still be described as quality-first and time-first, with smaller token upside.
- `t0` should still be described as exactness-first rather than token-first.
- `v0.3.4` is a stability patch for the public release line, not a new benchmark claim.

## Validation

- Public benchmark artifacts remain staged under `benchmark/`.
- The canonical pre-release heavy validation report remains under `docs/release_validation_latest.md`.
- The refreshed general-task public report is available under `benchmark/hybrid_general_task_public_report_en_latest.md` and the corresponding PDF/JSON artifacts.
- Public CI now verifies the synchronized source line on both `ubuntu-latest` and `windows-latest`.
