from __future__ import annotations

import json
from pathlib import Path

from _common import dump_payload, ensure_repo_src, repo_root

ensure_repo_src()

from aclx.supervisor import ACLXSupervisor  # noqa: E402


def load_fixture() -> tuple[dict[str, object], Path]:
    root = repo_root()
    fixture_dir = root / "tests" / "fixtures" / "t2_shared_state_task"
    fixture = json.loads((fixture_dir / "fixture.json").read_text(encoding="utf-8"))
    return fixture, fixture_dir


def main() -> None:
    fixture, workspace = load_fixture()
    task = str(fixture["task"]).format(workspace=str(workspace))
    payload = ACLXSupervisor().build_payload(
        task,
        cwd=str(workspace),
        style="adaptive",
        profile=str(fixture["profile"]),
        task_shape="shared_state",
        expected_handoffs=2,
        expected_rounds=2,
        child_agents=2,
        shared_state=True,
        outputs=[str(value) for value in fixture.get("outputs", [])],
        constraints=[str(value) for value in fixture.get("constraints", [])],
        stop_conditions=[str(value) for value in fixture.get("stop_conditions", [])],
        next_actions=[str(value) for value in fixture.get("next_actions", [])],
    )
    dump_payload(
        "t2_pipeline_fix",
        payload,
        workspace=workspace,
        extra={"fixture": str(workspace / "fixture.json")},
    )


if __name__ == "__main__":
    main()
