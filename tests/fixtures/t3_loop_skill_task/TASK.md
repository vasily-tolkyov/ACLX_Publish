Rewrite `target_skill/SKILL.md` so it becomes a valid skill and preserves these exact behavioral constraints:

- mention `generator`, `critic`, and `refiner` roles
- say `intake-only` or `intake only`
- say the critic gives the `final outward verdict`
- mention `strict mode` or `strict-mode-only`
- say `do not use for new tasks`
- say `must not count passes or failures`
- say `must not rewrite` user requests
- keep YAML frontmatter valid for the local quick validator
- write `runtime/checkpoints/checkpoint_01.aclx` as an ACL-X C-layer checkpoint artifact

Keep the final reply concise and list changed file paths.
