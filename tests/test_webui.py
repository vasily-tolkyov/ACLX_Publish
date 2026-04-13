from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aclx.runtime_bridge import ACLXRuntimeBridge
from aclx.supervisor import ACLXSupervisor
from aclx.webui import DEFAULT_VISIBLE_SESSION_IDS, SessionStore, UIStateStore, summarize_thread


def write_session(path: Path, *, cwd: str, user_text: str, timestamp: str, extra_rows: list[dict] | None = None) -> None:
    rows = [
        {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {"cwd": cwd, "source": "cli", "timestamp": timestamp},
        },
        {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}],
            },
        },
    ]
    if extra_rows:
        rows.extend(extra_rows)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


class WebUITests(unittest.TestCase):
    def test_summarize_thread_strips_paths_and_limits_length(self) -> None:
        text = r"Check D:\demo\project\main.py and explain the performance bottleneck."
        summary = summarize_thread(text)
        self.assertNotIn(r"D:\demo", summary)
        self.assertLessEqual(len(summary), 10)

    def test_workspace_tree_only_shows_whitelisted_sessions_and_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "04" / "05"
            sessions_dir.mkdir(parents=True)

            visible_id = DEFAULT_VISIBLE_SESSION_IDS[0]
            hidden_id = "11111111-1111-1111-1111-111111111111"

            (root / ".codex-global-state.json").write_text(
                json.dumps({"active-workspace-roots": [r"D:\demo", r"D:\other"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "session_index.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": visible_id,
                                "thread_name": "Visible thread",
                                "updated_at": "2026-04-05T10:00:00Z",
                            }
                        ),
                        json.dumps(
                            {
                                "id": hidden_id,
                                "thread_name": "Hidden thread",
                                "updated_at": "2026-04-05T09:00:00Z",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            write_session(
                sessions_dir / f"rollout-2026-04-05T10-00-00-{visible_id}.jsonl",
                cwd=r"D:\demo",
                user_text="Show only this thread",
                timestamp="2026-04-05T10:00:00Z",
            )
            write_session(
                sessions_dir / f"rollout-2026-04-05T09-00-00-{hidden_id}.jsonl",
                cwd=r"D:\other",
                user_text="This thread should stay hidden",
                timestamp="2026-04-05T09:00:00Z",
            )

            ui_state = UIStateStore(root)
            draft = ui_state.create_draft(r"D:\demo")
            store = SessionStore(root, ui_state=ui_state)
            tree = store.list_workspaces()

            self.assertEqual(tree["candidate_workspaces"][0], r"D:\demo")
            self.assertIn(r"D:\other", tree["candidate_workspaces"])
            self.assertEqual(len(tree["workspaces"]), 1)
            self.assertEqual(tree["workspaces"][0]["path"], r"D:\demo")

            thread_ids = [thread["id"] for thread in tree["workspaces"][0]["threads"]]
            self.assertIn(draft["id"], thread_ids)
            self.assertIn(f"session:{visible_id}", thread_ids)
            self.assertNotIn(f"session:{hidden_id}", thread_ids)

    def test_legacy_draft_is_hidden_until_created_via_current_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aclx_ui_state.json").write_text(
                json.dumps(
                    {
                        "drafts": [
                            {
                                "id": "draft:legacy",
                                "kind": "draft",
                                "cwd": r"D:\demo",
                                "title": "Legacy draft",
                                "created_at": "2026-04-05T10:00:00Z",
                                "updated_at": "2026-04-05T10:00:00Z",
                                "entries": [],
                            }
                        ],
                        "session_overrides": {},
                        "visible_session_ids": list(DEFAULT_VISIBLE_SESSION_IDS),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            ui_state = UIStateStore(root)
            self.assertEqual(ui_state.list_drafts(), [])

    def test_orphan_whitelisted_session_file_without_index_row_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "04" / "05"
            sessions_dir.mkdir(parents=True)

            visible_id = DEFAULT_VISIBLE_SESSION_IDS[0]
            (root / "session_index.jsonl").write_text("", encoding="utf-8")
            write_session(
                sessions_dir / f"rollout-2026-04-05T10-00-00-{visible_id}.jsonl",
                cwd=r"D:\demo",
                user_text="Visible even without index row",
                timestamp="2026-04-05T10:00:00Z",
            )

            store = SessionStore(root, ui_state=UIStateStore(root))
            tree = store.list_workspaces()

            self.assertEqual(len(tree["workspaces"]), 1)
            self.assertEqual(tree["workspaces"][0]["threads"][0]["id"], f"session:{visible_id}")

    def test_promoted_draft_becomes_visible_real_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "04" / "05"
            sessions_dir.mkdir(parents=True)

            new_session_id = "22222222-2222-2222-2222-222222222222"
            (root / "session_index.jsonl").write_text(
                json.dumps(
                    {
                        "id": new_session_id,
                        "thread_name": "Freshly promoted",
                        "updated_at": "2026-04-05T11:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            write_session(
                sessions_dir / f"rollout-2026-04-05T11-00-00-{new_session_id}.jsonl",
                cwd=r"D:\fresh",
                user_text="My first real message",
                timestamp="2026-04-05T11:00:00Z",
            )

            ui_state = UIStateStore(root)
            draft = ui_state.create_draft(r"D:\fresh")
            ui_state.promote_draft(draft["id"], new_session_id, "My first real message")

            state_payload = json.loads((root / "aclx_ui_state.json").read_text(encoding="utf-8"))
            self.assertIn(new_session_id, state_payload["visible_session_ids"])

            store = SessionStore(root, ui_state=ui_state)
            tree = store.list_workspaces()

            self.assertEqual(len(tree["workspaces"]), 1)
            thread_ids = [thread["id"] for thread in tree["workspaces"][0]["threads"]]
            self.assertIn(f"session:{new_session_id}", thread_ids)
            self.assertNotIn(draft["id"], thread_ids)

    def test_archive_and_restore_session_moves_file_and_updates_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "04" / "05"
            sessions_dir.mkdir(parents=True)
            (root / "archived_sessions").mkdir(parents=True)

            session_id = DEFAULT_VISIBLE_SESSION_IDS[0]
            session_path = sessions_dir / f"rollout-2026-04-05T10-00-00-{session_id}.jsonl"
            (root / "session_index.jsonl").write_text(
                json.dumps({"id": session_id, "thread_name": "Archivable thread", "updated_at": "2026-04-05T10:00:00Z"})
                + "\n",
                encoding="utf-8",
            )
            write_session(
                session_path,
                cwd=r"D:\demo",
                user_text="Archive me",
                timestamp="2026-04-05T10:00:00Z",
            )

            ui_state = UIStateStore(root)
            store = SessionStore(root, ui_state=ui_state)

            archived = store.archive_thread(f"session:{session_id}")
            archived_path = root / archived["archived_relpath"]
            self.assertFalse(session_path.exists())
            self.assertTrue(archived_path.exists())
            self.assertEqual(store.list_workspaces()["workspaces"], [])
            self.assertEqual(store.list_recent_archived_threads()[0]["thread_id"], f"session:{session_id}")

            restored = store.restore_archived_thread(str(archived["id"]))
            self.assertEqual(restored["thread_id"], f"session:{session_id}")
            self.assertTrue(session_path.exists())
            self.assertEqual(store.list_recent_archived_threads(), [])
            self.assertEqual(store.list_workspaces()["workspaces"][0]["threads"][0]["id"], f"session:{session_id}")

    def test_archive_and_restore_draft_updates_ui_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ui_state = UIStateStore(root)
            draft = ui_state.create_draft(r"D:\demo")
            store = SessionStore(root, ui_state=ui_state)

            archived = store.archive_thread(draft["id"])
            self.assertEqual(archived["thread_id"], draft["id"])
            self.assertEqual(store.list_workspaces()["workspaces"], [])
            archived_rows = store.list_recent_archived_threads()
            self.assertEqual(len(archived_rows), 1)
            self.assertEqual(archived_rows[0]["kind"], "draft")

            restored = store.restore_archived_thread(str(archived["id"]))
            self.assertEqual(restored["thread_id"], draft["id"])
            threads = store.list_workspaces()["workspaces"][0]["threads"]
            self.assertEqual(threads[0]["id"], draft["id"])

    def test_get_thread_returns_draft_and_session_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "04" / "05"
            sessions_dir.mkdir(parents=True)

            session_id = "abc123"
            (root / "session_index.jsonl").write_text(
                json.dumps({"id": session_id, "thread_name": "Resume task", "updated_at": "2026-04-05T10:00:00Z"})
                + "\n",
                encoding="utf-8",
            )

            write_session(
                sessions_dir / "rollout-2026-04-05T10-00-00-abc123.jsonl",
                cwd=r"D:\demo",
                user_text="# AGENTS.md instructions for D:\\demo",
                timestamp="2026-04-05T10:00:00Z",
                extra_rows=[
                    {
                        "timestamp": "2026-04-05T10:00:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "developer",
                            "content": [{"type": "input_text", "text": "hidden"}],
                        },
                    },
                    {
                        "timestamp": "2026-04-05T10:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Resume task"}],
                        },
                    },
                    {
                        "timestamp": "2026-04-05T10:00:02Z",
                        "type": "event_msg",
                        "payload": {"type": "agent_message", "message": "Working"},
                    },
                ],
            )

            ui_state = UIStateStore(root)
            draft = ui_state.create_draft(r"D:\demo")
            store = SessionStore(root, ui_state=ui_state)

            draft_detail = store.get_thread(draft["id"])
            assert draft_detail is not None
            self.assertEqual(draft_detail["kind"], "draft")
            self.assertEqual(draft_detail["cwd"], r"D:\demo")

            session_detail = store.get_thread(f"session:{session_id}")
            assert session_detail is not None
            self.assertEqual(session_detail["kind"], "session")
            self.assertEqual(session_detail["cwd"], r"D:\demo")
            self.assertEqual(len(session_detail["entries"]), 1)
            self.assertEqual(session_detail["entries"][0]["role"], "user")

    def test_runtime_bridge_round_trips_user_text_for_display(self) -> None:
        bridge = ACLXRuntimeBridge()
        aclx = bridge.encode_user_text("请直接修复这个问题", cwd=r"D:\demo")
        self.assertTrue(bridge.is_aclx(aclx))
        self.assertEqual(bridge.display_text(aclx, role="user"), "请直接修复这个问题")

    def test_get_thread_decodes_aclx_user_and_assistant_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "04" / "05"
            sessions_dir.mkdir(parents=True)

            session_id = DEFAULT_VISIBLE_SESSION_IDS[0]
            bridge = ACLXRuntimeBridge()
            user_aclx = bridge.encode_user_text("请修复这个线程", cwd=r"D:\demo")
            assistant_aclx = bridge.encode_supervisor_task("修复完成并汇报", cwd=r"D:\demo")

            (root / "session_index.jsonl").write_text(
                json.dumps({"id": session_id, "thread_name": "ACLX thread", "updated_at": "2026-04-05T10:00:00Z"})
                + "\n",
                encoding="utf-8",
            )
            write_session(
                sessions_dir / f"rollout-2026-04-05T10-00-00-{session_id}.jsonl",
                cwd=r"D:\demo",
                user_text=user_aclx,
                timestamp="2026-04-05T10:00:00Z",
                extra_rows=[
                    {
                        "timestamp": "2026-04-05T10:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": assistant_aclx}],
                        },
                    }
                ],
            )

            store = SessionStore(root, ui_state=UIStateStore(root))
            thread = store.get_thread(f"session:{session_id}")
            assert thread is not None
            self.assertEqual(thread["entries"][0]["text"], "请修复这个线程")
            self.assertIn("当前状态：", thread["entries"][1]["text"])

    def test_supervisor_build_payload_keeps_t0_default_and_full_mode_wraps_runtime_prompt(self) -> None:
        default_payload = ACLXSupervisor().build_payload("请分析目录并修复", cwd="D:/")
        self.assertEqual(default_payload.tier, "t0")
        self.assertEqual(default_payload.codex_prompt, "请分析目录并修复")
        self.assertEqual(default_payload.aclx_bundle, "")

        full_payload = ACLXSupervisor().build_payload("请分析目录并修复", cwd="D:/", style="full")
        self.assertIn("$aclx-runtime", full_payload.codex_prompt)
        self.assertIn("$acl-x-protocol", full_payload.codex_prompt)
        self.assertIn(full_payload.aclx_bundle, full_payload.codex_prompt)


if __name__ == "__main__":
    unittest.main()

