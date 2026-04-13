from __future__ import annotations

import json
from pathlib import Path

from _common import ensure_repo_src, repo_root

ensure_repo_src()

from aclx.hybrid import ACLXHybridPromptBuilder  # noqa: E402
from aclx.supervisor import ACLXSupervisor  # noqa: E402


def load_fixture() -> tuple[dict[str, object], Path]:
    root = repo_root()
    fixture_dir = root / "tests" / "fixtures" / "t3_loop_skill_task"
    fixture = json.loads((fixture_dir / "fixture.json").read_text(encoding="utf-8"))
    return fixture, fixture_dir


def main() -> None:
    fixture, workspace = load_fixture()
    task = str(fixture["task"]).format(workspace=str(workspace))
    supervisor_payload = ACLXSupervisor().build_payload(
        task,
        cwd=str(workspace),
        style="adaptive",
        profile=str(fixture["profile"]),
        task_shape="loop",
        expected_handoffs=5,
        expected_rounds=5,
        child_agents=2,
        shared_state=True,
        outputs=[str(value) for value in fixture.get("outputs", [])],
        constraints=[str(value) for value in fixture.get("constraints", [])],
        stop_conditions=[str(value) for value in fixture.get("stop_conditions", [])],
        next_actions=[str(value) for value in fixture.get("next_actions", [])],
    )
    resume_payload = ACLXHybridPromptBuilder().build_resume_prompt(
        task_code="T3",
        profile=str(fixture["profile"]),
        lane="loop-sample",
        round_label="r2",
        snapshot_code="S1",
        issue_codes=["F1"],
        next_actions=[str(value) for value in fixture.get("next_actions", [])],
        delta_items=["D1"],
        required_artifacts=[str(value) for value in fixture.get("outputs", [])],
        acceptance_contract=[str(value) for value in fixture.get("constraints", [])],
        stop_conditions=[str(value) for value in fixture.get("stop_conditions", [])],
    )
    print(
        json.dumps(
            {
                "example": "t3_loop_resume",
                "workspace": str(workspace),
                "initial_tier": supervisor_payload.tier,
                "initial_bridge_mode": supervisor_payload.bridge_mode,
                "initial_prompt": supervisor_payload.codex_prompt,
                "initial_aclx_bundle": supervisor_payload.aclx_bundle,
                "resume_tier": resume_payload.tier,
                "resume_bridge_mode": resume_payload.bridge_mode,
                "resume_prompt": resume_payload.prompt,
                "resume_aclx_bundle": resume_payload.aclx_bundle,
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
