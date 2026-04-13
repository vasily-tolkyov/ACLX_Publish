from __future__ import annotations

from pathlib import Path

from _common import dump_payload, ensure_repo_src

ensure_repo_src()

from aclx.supervisor import ACLXSupervisor  # noqa: E402


def main() -> None:
    workspace = Path(__file__).resolve().parent / "data" / "t1"
    task = (
        "You are in an isolated workspace. Only edit files under {workspace}.\n\n"
        "Inspect `src/review_target.py`.\n"
        "Delegate exactly once to one reviewer pass, merge the conclusion yourself, and write `reports/review.md`.\n"
        "`reports/review.md` must contain headings `Decision` and `Evidence`.\n"
        "Identify the highest-risk bug with a concrete file path and explain why empty input breaks the function.\n"
        "Keep the final reply to one sentence and list changed file paths.\n"
    ).format(workspace=workspace)
    payload = ACLXSupervisor().build_payload(
        task,
        cwd=str(workspace),
        style="adaptive",
        profile="review",
        task_shape="delegated_once",
        expected_handoffs=1,
        expected_rounds=1,
        child_agents=1,
        shared_state=True,
        outputs=["reports/review.md"],
        constraints=[
            "reports/review.md keeps Decision and Evidence headings",
            "reports/review.md names src/review_target.py",
            "reports/review.md explains why empty input breaks cleaned[0]",
        ],
        stop_conditions=["missing review report"],
        next_actions=["delegate once", "write review report"],
    )
    dump_payload("t1_single_review", payload, workspace=workspace)


if __name__ == "__main__":
    main()
