# Release Checklist

Chinese version: [RELEASE_CHECKLIST.zh-CN.md](RELEASE_CHECKLIST.zh-CN.md).

## Must Finish Before Release

- [x] `README.md` updated to the latest validated scope and benchmark evidence
- [x] `examples/` with one runnable minimal example per tier
- [x] `CHANGELOG.md`
- [x] `LICENSE`
- [x] `CODE_OF_CONDUCT.md`
- [x] `SECURITY.md`
- [x] host-compatibility documentation states that default-on installation is Codex-specific
- [x] structured benchmark artifacts under `benchmark/`
- [x] latest human-readable pre-release heavy report staged canonically under `docs/`
- [x] Chinese mirrors exist for the key release-facing docs
- [x] `.github/` issue, PR, and CI templates

## Strongly Recommended

- [x] `STRATEGY.md` with tier triggers, bundle caps, bridge modes, and override rules
- [x] `CONTRIBUTING.md`
- [x] machine-readable public benchmark JSON under `benchmark/`
- [x] editable-install workflow validated with `python -m pip install -e .`
- [x] `share_pack/` assets included for the public repo

## Good Follow-Up Work

- [x] routing decision tree under `docs/routing_decision_tree.md`
- [x] `MANIFEST.in` for source distribution completeness
- [ ] publish wheel-install validation as a first-class supported workflow

## Notes

- The current headline benchmark for release messaging should come from general-task run `20260413_160451`.
- The latest bounded engineering release gate should come from pre-release run `20260413_152717`.
- Human-readable pre-release validation lives under `docs/`; `benchmark/` keeps machine-readable summaries and PDF artifacts.
- `t0` still needs caution on tiny fixed-format tasks where token savings can be negative even when quality and time stay acceptable.
- Release wording should distinguish "Codex default-on installation" from "manual integration for other agent hosts".
