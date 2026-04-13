from __future__ import annotations

from pathlib import Path

from _common import dump_payload, ensure_repo_src

ensure_repo_src()

from aclx.supervisor import ACLXSupervisor  # noqa: E402


def main() -> None:
    workspace = Path(__file__).resolve().parent / "data" / "t0"
    task = (
        "You are in an isolated workspace. Only read files under {workspace}.\n\n"
        "Read `docs/release_notes.txt`.\n"
        "Return exactly 3 non-empty lines:\n"
        "Tier: t0\n"
        "Decision: <one sentence>\n"
        "Evidence: docs/release_notes.txt; mention strategy lock and adaptive runtime.\n"
        "Do not edit files.\n"
    ).format(workspace=workspace)
    payload = ACLXSupervisor().build_payload(task, cwd=str(workspace), style="adaptive")
    dump_payload("t0_summary", payload, workspace=workspace)


if __name__ == "__main__":
    main()
