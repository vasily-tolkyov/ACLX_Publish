# ACL-X v0.3.3 Release Update Notes

Chinese version: [release_update_v0.3.3.zh-CN.md](release_update_v0.3.3.zh-CN.md).

## Summary

`v0.3.3` is the current public release update for ACL-X. This update refreshes the public general-task benchmark package, synchronizes the published source tree to the current locked hybrid strategy, and adds clearer release-facing messaging around what the benchmark now supports.

## Headline Outcome

- General-task heavy run `20260415_110636_t2_refresh`: `31.78%` aggregate token improvement, `54.12%` aggregate time improvement, `+0.75` quality delta.
- Pre-release heavy run `20260413_152717`: `66.35%` aggregate token improvement, `71.16%` aggregate time improvement, `+5.00` quality delta.
- Public release stance remains quality-first and time-first. Token gains are real, but they remain tier-dependent rather than universal.

## What Changed

- Replaced the previously weaker public `t2` benchmark slice with repaired results from the refreshed general-task run.
- Published the current locked source tree, tier configs, runtime/session surfaces, and behavior-locking tests alongside the benchmark update.
- Aligned README, benchmark summary, launch-copy pack, checklist, and bilingual public reports to the same release line.

## Release Messaging Guidance

- `t1` remains the clearest low-risk repeat win for both tokens and time.
- `t2` now supports a stronger public efficiency claim when explicit artifact contracts and validators are present.
- `t3` should still be described as quality-first and time-first, with smaller token upside.
- `t0` should still be described as exactness-first rather than token-first.

## Validation

- Public benchmark artifacts are staged under `benchmark/`.
- The canonical pre-release heavy validation report remains under `docs/release_validation_latest.md`.
- The refreshed general-task public report is available under `benchmark/hybrid_general_task_public_report_en_latest.md` and the corresponding PDF/JSON artifacts.
