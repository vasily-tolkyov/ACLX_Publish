from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .ctxbridge import load_ctx_module
from .runtime_bridge import ACLXRuntimeBridge
from .supervisor import ACLXSupervisor, DEFAULT_CODEX_CWD, DEFAULT_SUPERVISOR_TASK

DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8765
ASSET_DIR = Path(__file__).with_name("webui_assets")
PATH_NOISE_RE = re.compile(r"([A-Za-z]:\\[^\s,，。！？；：、()（）【】<>\"']+|(?:/[^\s,，。！？；：、()（）【】<>\"']+)+)")
SPACE_RE = re.compile(r"\s+")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
DEFAULT_VISIBLE_SESSION_IDS = (
    "019d58b2-5ced-7ea1-9f55-cd9dfdcae0c9",
    "019d56a4-b2e2-7ed0-9605-84ff065b93de",
)


def default_codex_home() -> Path:
    env_value = os.environ.get("CODEX_HOME")
    if env_value:
        return Path(env_value)
    return Path.home() / ".codex"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_ui_state() -> dict[str, Any]:
    return {
        "drafts": [],
        "visible_draft_ids": [],
        "archived_threads": [],
        "session_overrides": {},
        "visible_session_ids": list(DEFAULT_VISIBLE_SESSION_IDS),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _safe_datetime(value: str) -> str:
    return value or ""


def _clean_summary_source(text: str) -> str:
    text = PATH_NOISE_RE.sub(" ", text or "")
    text = text.replace("\r", " ").replace("\n", " ")
    text = SPACE_RE.sub(" ", text)
    text = text.replace(" ", "")
    text = text.strip(" \t-–—_.,，。！？；：:()（）[]【】<>《》\"'`")
    return text or "新线程"


def summarize_thread(text: str, *, fallback: str = "新线程", limit: int = 10) -> str:
    cleaned = _clean_summary_source(text) if text else fallback
    if not cleaned:
        cleaned = fallback
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 1:
        return cleaned[:limit]
    return cleaned[: limit - 1] + "…"


def workspace_label(cwd: str) -> str:
    path = Path(cwd)
    if path.name:
        return path.name
    anchor = path.anchor.rstrip("\\/")
    return anchor or cwd


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("content")
        if text:
            parts.append(str(text).strip())
    return "\n\n".join(part for part in parts if part)


def _extract_session_id_from_name(value: str) -> str:
    match = UUID_RE.search(value or "")
    if match:
        return match.group(0)
    stem = value.rsplit("-", 1)[-1] if "-" in value else value
    return stem.strip()


class UIStateStore:
    def __init__(self, codex_home: Path) -> None:
        self.path = codex_home / "aclx_ui_state.json"
        self.lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_ui_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_ui_state()
        if not isinstance(data, dict):
            return _default_ui_state()
        data.setdefault("drafts", [])
        data.setdefault("visible_draft_ids", [])
        data.setdefault("archived_threads", [])
        data.setdefault("session_overrides", {})
        visible_session_ids = data.get("visible_session_ids")
        if not isinstance(visible_session_ids, list):
            data["visible_session_ids"] = list(DEFAULT_VISIBLE_SESSION_IDS)
        else:
            cleaned_visible_ids: list[str] = []
            seen: set[str] = set()
            for value in visible_session_ids:
                session_id = str(value or "").strip()
                if session_id and session_id not in seen:
                    cleaned_visible_ids.append(session_id)
                    seen.add(session_id)
            data["visible_session_ids"] = cleaned_visible_ids
        visible_draft_ids = data.get("visible_draft_ids")
        if not isinstance(visible_draft_ids, list):
            data["visible_draft_ids"] = []
        else:
            cleaned_visible_draft_ids: list[str] = []
            seen_draft_ids: set[str] = set()
            for value in visible_draft_ids:
                draft_id = str(value or "").strip()
                if draft_id and draft_id not in seen_draft_ids:
                    cleaned_visible_draft_ids.append(draft_id)
                    seen_draft_ids.add(draft_id)
            data["visible_draft_ids"] = cleaned_visible_draft_ids
        archived_threads = data.get("archived_threads")
        if not isinstance(archived_threads, list):
            data["archived_threads"] = []
        else:
            cleaned_archived_threads: list[dict[str, Any]] = []
            seen_archive_ids: set[str] = set()
            for value in archived_threads:
                if not isinstance(value, dict):
                    continue
                archive_id = str(value.get("id") or "").strip()
                if not archive_id or archive_id in seen_archive_ids:
                    continue
                cleaned_archived_threads.append(value)
                seen_archive_ids.add(archive_id)
            cleaned_archived_threads.sort(key=lambda item: str(item.get("archived_at") or ""), reverse=True)
            data["archived_threads"] = cleaned_archived_threads[:10]
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_drafts(self) -> list[dict[str, Any]]:
        with self.lock:
            data = self._read()
            drafts = data.get("drafts", [])
            visible_draft_ids = {
                str(value).strip()
                for value in data.get("visible_draft_ids", [])
                if str(value or "").strip()
            }
            return [
                draft
                for draft in drafts
                if isinstance(draft, dict) and str(draft.get("id") or "").strip() in visible_draft_ids
            ]

    def get_draft(self, thread_id: str) -> dict[str, Any] | None:
        with self.lock:
            for draft in self._read().get("drafts", []):
                if isinstance(draft, dict) and draft.get("id") == thread_id:
                    return draft
        return None

    def create_draft(self, cwd: str) -> dict[str, Any]:
        now = _utc_now_iso()
        with self.lock:
            data = self._read()
            drafts = [draft for draft in data.get("drafts", []) if isinstance(draft, dict)]
            siblings = [draft.get("title") for draft in drafts if draft.get("cwd") == cwd]
            title = "新线程"
            if title in siblings:
                suffix = 2
                while f"新线程 {suffix}" in siblings:
                    suffix += 1
                title = f"新线程 {suffix}"
            draft = {
                "id": f"draft:{uuid.uuid4().hex[:12]}",
                "kind": "draft",
                "cwd": cwd,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "entries": [],
            }
            drafts.append(draft)
            data["drafts"] = drafts
            visible_draft_ids = [
                str(value).strip()
                for value in data.get("visible_draft_ids", [])
                if str(value or "").strip()
            ]
            visible_draft_ids.append(str(draft["id"]))
            data["visible_draft_ids"] = visible_draft_ids
            self._write(data)
            return draft

    def promote_draft(self, draft_id: str, session_id: str, first_user_message: str) -> None:
        with self.lock:
            data = self._read()
            drafts = [draft for draft in data.get("drafts", []) if isinstance(draft, dict) and draft.get("id") != draft_id]
            overrides = data.get("session_overrides", {})
            visible_session_ids = [
                str(value).strip()
                for value in data.get("visible_session_ids", [])
                if str(value or "").strip()
            ]
            visible_draft_ids = [
                str(value).strip()
                for value in data.get("visible_draft_ids", [])
                if str(value or "").strip()
            ]
            overrides[session_id] = {
                "display_first_user_message": first_user_message,
                "created_at": _utc_now_iso(),
            }
            if session_id not in visible_session_ids:
                visible_session_ids.append(session_id)
            visible_draft_ids = [value for value in visible_draft_ids if value != draft_id]
            data["drafts"] = drafts
            data["visible_draft_ids"] = visible_draft_ids
            data["session_overrides"] = overrides
            data["visible_session_ids"] = visible_session_ids
            self._write(data)

    def get_session_override(self, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            overrides = self._read().get("session_overrides", {})
            value = overrides.get(session_id)
            return value if isinstance(value, dict) else None

    def visible_session_ids(self) -> set[str]:
        with self.lock:
            visible_session_ids = self._read().get("visible_session_ids", [])
            return {
                str(value).strip()
                for value in visible_session_ids
                if str(value or "").strip()
            }

    def list_archived_threads(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self.lock:
            archived_threads = self._read().get("archived_threads", [])
            return [
                item
                for item in archived_threads[:limit]
                if isinstance(item, dict)
            ]

    def get_archived_thread(self, archive_id: str) -> dict[str, Any] | None:
        with self.lock:
            for item in self._read().get("archived_threads", []):
                if isinstance(item, dict) and str(item.get("id") or "") == archive_id:
                    return item
        return None

    def archive_session(
        self,
        *,
        session_id: str,
        title: str,
        cwd: str,
        original_relpath: str,
        archived_relpath: str,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        with self.lock:
            data = self._read()
            visible_session_ids = [
                str(value).strip()
                for value in data.get("visible_session_ids", [])
                if str(value or "").strip()
            ]
            data["visible_session_ids"] = [value for value in visible_session_ids if value != session_id]
            archived_threads = [
                item
                for item in data.get("archived_threads", [])
                if isinstance(item, dict) and str(item.get("thread_id") or "") != f"session:{session_id}"
            ]
            entry = {
                "id": f"archive:{uuid.uuid4().hex[:12]}",
                "thread_id": f"session:{session_id}",
                "kind": "session",
                "session_id": session_id,
                "title": title,
                "cwd": cwd,
                "archived_at": now,
                "original_relpath": original_relpath,
                "archived_relpath": archived_relpath,
            }
            data["archived_threads"] = [entry, *archived_threads][:10]
            self._write(data)
            return entry

    def archive_draft(self, draft_id: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self.lock:
            data = self._read()
            drafts = [draft for draft in data.get("drafts", []) if isinstance(draft, dict)]
            draft = next((item for item in drafts if str(item.get("id") or "") == draft_id), None)
            if not draft:
                return None
            visible_draft_ids = [
                str(value).strip()
                for value in data.get("visible_draft_ids", [])
                if str(value or "").strip()
            ]
            data["visible_draft_ids"] = [value for value in visible_draft_ids if value != draft_id]
            archived_threads = [
                item
                for item in data.get("archived_threads", [])
                if isinstance(item, dict) and str(item.get("thread_id") or "") != draft_id
            ]
            entry = {
                "id": f"archive:{uuid.uuid4().hex[:12]}",
                "thread_id": draft_id,
                "kind": "draft",
                "draft_id": draft_id,
                "title": str(draft.get("title") or "新线程"),
                "cwd": str(draft.get("cwd") or ""),
                "archived_at": now,
            }
            data["archived_threads"] = [entry, *archived_threads][:10]
            self._write(data)
            return entry

    def restore_archived_thread(self, archive_id: str) -> dict[str, Any] | None:
        with self.lock:
            data = self._read()
            archived_threads = [item for item in data.get("archived_threads", []) if isinstance(item, dict)]
            entry = next((item for item in archived_threads if str(item.get("id") or "") == archive_id), None)
            if not entry:
                return None
            data["archived_threads"] = [item for item in archived_threads if str(item.get("id") or "") != archive_id]
            if entry.get("kind") == "session":
                session_id = str(entry.get("session_id") or "").strip()
                visible_session_ids = [
                    str(value).strip()
                    for value in data.get("visible_session_ids", [])
                    if str(value or "").strip()
                ]
                if session_id and session_id not in visible_session_ids:
                    visible_session_ids.append(session_id)
                data["visible_session_ids"] = visible_session_ids
            elif entry.get("kind") == "draft":
                draft_id = str(entry.get("draft_id") or entry.get("thread_id") or "").strip()
                visible_draft_ids = [
                    str(value).strip()
                    for value in data.get("visible_draft_ids", [])
                    if str(value or "").strip()
                ]
                if draft_id and draft_id not in visible_draft_ids:
                    visible_draft_ids.append(draft_id)
                data["visible_draft_ids"] = visible_draft_ids
            self._write(data)
            return entry


class SessionStore:
    def __init__(self, codex_home: Path | None = None, ui_state: UIStateStore | None = None) -> None:
        self.codex_home = codex_home or default_codex_home()
        self.index_file = self.codex_home / "session_index.jsonl"
        self.sessions_dir = self.codex_home / "sessions"
        self.archived_sessions_dir = self.codex_home / "archived_sessions"
        self.global_state_file = self.codex_home / ".codex-global-state.json"
        self.ui_state = ui_state or UIStateStore(self.codex_home)
        self.runtime_bridge = ACLXRuntimeBridge()

    def list_workspaces(self) -> dict[str, Any]:
        path_map = self._active_session_paths()
        active_sessions = self._collect_active_sessions(path_map)
        visible_session_ids = self.ui_state.visible_session_ids()
        groups: dict[str, dict[str, Any]] = {}

        for session in active_sessions:
            session_id = str(session.get("id") or "").strip()
            if session_id not in visible_session_ids:
                continue
            path = session.get("path")
            meta = session.get("meta") or {}
            cwd = str(session.get("cwd") or meta.get("cwd") or str(DEFAULT_CODEX_CWD))
            title_source = str(session.get("thread_name") or "") or str(meta.get("first_user_text") or "") or session_id
            thread = {
                "id": f"session:{session_id}",
                "kind": "session",
                "title": summarize_thread(title_source),
                "updated_at": _safe_datetime(str(session.get("updated_at") or meta.get("timestamp") or "")),
                "cwd": cwd,
            }
            self._add_thread(groups, cwd, thread)

        for draft in self.ui_state.list_drafts():
            cwd = str(draft.get("cwd") or "").strip()
            if not cwd:
                continue
            thread = {
                "id": str(draft.get("id")),
                "kind": "draft",
                "title": summarize_thread(str(draft.get("title") or "新线程")),
                "updated_at": _safe_datetime(str(draft.get("updated_at") or draft.get("created_at") or "")),
                "cwd": cwd,
            }
            self._add_thread(groups, cwd, thread)

        workspaces = list(groups.values())
        for workspace in workspaces:
            workspace["threads"].sort(key=lambda item: item.get("updated_at") or "", reverse=True)
            workspace["updated_at"] = workspace["threads"][0]["updated_at"] if workspace["threads"] else ""
        workspaces.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return {
            "workspaces": workspaces,
            "candidate_workspaces": self._candidate_workspaces(workspaces),
        }

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        if thread_id.startswith("draft:"):
            draft = self.ui_state.get_draft(thread_id)
            if not draft:
                return None
            return {
                "id": thread_id,
                "kind": "draft",
                "title": str(draft.get("title") or "新线程"),
                "cwd": str(draft.get("cwd") or ""),
                "entries": list(draft.get("entries") or []),
            }
        if not thread_id.startswith("session:"):
            return None
        session_id = thread_id.split(":", 1)[1]
        path = self._active_session_paths().get(session_id)
        if not path:
            return None
        head = self._read_session_head(path)
        override = self.ui_state.get_session_override(session_id)
        entries: list[dict[str, Any]] = []
        first_user_replaced = False
        for row in _read_jsonl(path):
            row_type = row.get("type")
            payload = row.get("payload")
            timestamp = str(row.get("timestamp") or "")
            if row_type == "response_item" and isinstance(payload, dict):
                item_type = payload.get("type")
                if item_type == "message":
                    text = _message_text(payload.get("content"))
                    role = str(payload.get("role") or "assistant")
                    if role == "developer":
                        continue
                    if role == "user" and self._is_system_user_message(text):
                        continue
                    if role == "user" and override and not first_user_replaced and self._looks_like_supervisor_prompt(text):
                        text = str(override.get("display_first_user_message") or text)
                        first_user_replaced = True
                    elif self.runtime_bridge.is_aclx(text):
                        text = self.runtime_bridge.display_text(text, role=role)
                    if text:
                        entries.append({"kind": "message", "role": role, "timestamp": timestamp, "text": text})
                elif item_type in {"function_call", "custom_tool_call"}:
                    raw = payload.get("arguments")
                    if raw is None:
                        raw = payload.get("input")
                    entries.append(
                        {
                            "kind": "tool_call",
                            "role": "tool",
                            "timestamp": timestamp,
                            "name": payload.get("name"),
                            "text": str(raw or ""),
                        }
                    )
                elif item_type in {"function_call_output", "custom_tool_call_output"}:
                    entries.append(
                        {
                            "kind": "tool_output",
                            "role": "tool",
                            "timestamp": timestamp,
                            "name": payload.get("name"),
                            "text": str(payload.get("output") or ""),
                        }
                    )
        return {
            "id": thread_id,
            "kind": "session",
            "title": summarize_thread(head.get("thread_name") or head.get("first_user_text") or session_id),
            "cwd": head.get("cwd") or "",
            "entries": entries,
            "file_path": str(path),
        }

    def active_session_ids(self) -> set[str]:
        return {str(item.get("id") or "").strip() for item in self._collect_active_sessions(self._active_session_paths()) if item.get("id")}

    def newest_session_id(self, previous_ids: set[str]) -> str | None:
        for session in self._collect_active_sessions(self._active_session_paths()):
            session_id = str(session.get("id") or "").strip()
            if session_id and session_id not in previous_ids:
                return session_id
        return None

    def list_recent_archived_threads(self) -> list[dict[str, Any]]:
        return self.ui_state.list_archived_threads(limit=10)

    def archive_thread(self, thread_id: str) -> dict[str, Any]:
        if thread_id.startswith("draft:"):
            entry = self.ui_state.archive_draft(thread_id)
            if not entry:
                raise FileNotFoundError("thread not found")
            return entry
        if not thread_id.startswith("session:"):
            raise FileNotFoundError("thread not found")
        session_id = thread_id.split(":", 1)[1]
        session = self._find_active_session(session_id)
        if not session:
            raise FileNotFoundError("thread not found")
        path = session["path"]
        cwd = str(session.get("cwd") or "")
        meta = session.get("meta") or {}
        title = summarize_thread(str(session.get("thread_name") or "") or str(meta.get("first_user_text") or "") or session_id)
        original_relpath = str(path.relative_to(self.sessions_dir))
        archived_path = self.archived_sessions_dir / original_relpath
        archived_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(archived_path))
        return self.ui_state.archive_session(
            session_id=session_id,
            title=title,
            cwd=cwd,
            original_relpath=original_relpath,
            archived_relpath=str(archived_path.relative_to(self.codex_home)),
        )

    def restore_archived_thread(self, archive_id: str) -> dict[str, Any]:
        entry = self.ui_state.get_archived_thread(archive_id)
        if not entry:
            raise FileNotFoundError("archive not found")
        if entry.get("kind") == "session":
            archived_relpath = str(entry.get("archived_relpath") or "").strip()
            archived_path = self.codex_home / archived_relpath if archived_relpath else self.archived_sessions_dir
            if not archived_relpath or not archived_path.exists():
                raise FileNotFoundError("archived session file not found")
            original_relpath = str(entry.get("original_relpath") or "").strip() or self._infer_session_relpath(archived_path.name)
            restore_path = self.sessions_dir / original_relpath
            restore_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archived_path), str(restore_path))
        restored = self.ui_state.restore_archived_thread(archive_id)
        if not restored:
            raise FileNotFoundError("archive not found")
        return {
            "restored": restored,
            "thread_id": str(restored.get("thread_id") or ""),
        }

    def _active_rows(self) -> list[dict[str, Any]]:
        rows = [row for row in _read_jsonl(self.index_file) if row.get("id")]
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return rows

    def _collect_active_sessions(self, path_map: dict[str, Path]) -> list[dict[str, Any]]:
        indexed_rows = self._active_rows()
        indexed_ids: set[str] = set()
        sessions: list[dict[str, Any]] = []

        for row in indexed_rows:
            session_id = str(row.get("id") or "").strip()
            path = path_map.get(session_id)
            if not session_id or not path:
                continue
            meta = self._read_session_head(path)
            sessions.append(
                {
                    "id": session_id,
                    "path": path,
                    "thread_name": str(row.get("thread_name") or ""),
                    "updated_at": str(row.get("updated_at") or meta.get("timestamp") or ""),
                    "cwd": str(meta.get("cwd") or ""),
                    "meta": meta,
                }
            )
            indexed_ids.add(session_id)

        for session_id, path in path_map.items():
            if session_id in indexed_ids:
                continue
            meta = self._read_session_head(path)
            sessions.append(
                {
                    "id": session_id,
                    "path": path,
                    "thread_name": "",
                    "updated_at": str(meta.get("timestamp") or datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")),
                    "cwd": str(meta.get("cwd") or ""),
                    "meta": meta,
                }
            )

        sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return sessions

    def _find_active_session(self, session_id: str) -> dict[str, Any] | None:
        for item in self._collect_active_sessions(self._active_session_paths()):
            if str(item.get("id") or "").strip() == session_id:
                return item
        return None

    def _active_session_paths(self) -> dict[str, Path]:
        mapping: dict[str, Path] = {}
        if not self.sessions_dir.exists():
            return mapping
        for path in self.sessions_dir.rglob("*.jsonl"):
            session_id = _extract_session_id_from_name(path.stem)
            if session_id:
                mapping[session_id] = path
        return mapping

    def _read_session_head(self, path: Path) -> dict[str, str]:
        head = {"cwd": "", "timestamp": "", "first_user_text": "", "thread_name": ""}
        for row in _read_jsonl(path)[:20]:
            row_type = row.get("type")
            payload = row.get("payload")
            if row_type == "session_meta" and isinstance(payload, dict):
                head["cwd"] = str(payload.get("cwd") or "")
                head["timestamp"] = str(payload.get("timestamp") or "")
            elif row_type == "response_item" and isinstance(payload, dict) and payload.get("type") == "message":
                if payload.get("role") == "user" and not head["first_user_text"]:
                    text = _message_text(payload.get("content"))
                    if self._is_system_user_message(text):
                        continue
                    head["first_user_text"] = text
                    break
        return head

    @staticmethod
    def _infer_session_relpath(filename: str) -> str:
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})T", filename)
        if not match:
            return filename
        year, month, day = match.groups()
        return str(Path(year) / month / day / filename)

    def _candidate_workspaces(self, workspaces: list[dict[str, Any]]) -> list[str]:
        values: list[str] = []
        values.extend(self._global_active_roots())
        values.extend(workspace["path"] for workspace in workspaces if workspace.get("path"))
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value and value not in seen:
                deduped.append(value)
                seen.add(value)
        return deduped

    def _global_active_roots(self) -> list[str]:
        if not self.global_state_file.exists():
            return []
        try:
            data = json.loads(self.global_state_file.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return []
        roots = data.get("active-workspace-roots", [])
        if not isinstance(roots, list):
            return []
        return [str(root) for root in roots if isinstance(root, str)]

    @staticmethod
    def _add_thread(groups: dict[str, dict[str, Any]], cwd: str, thread: dict[str, Any]) -> None:
        group = groups.setdefault(
            cwd,
            {
                "id": cwd,
                "name": workspace_label(cwd),
                "path": cwd,
                "threads": [],
                "updated_at": "",
            },
        )
        group["threads"].append(thread)

    @staticmethod
    def _looks_like_supervisor_prompt(text: str) -> bool:
        if not text:
            return False
        return text.startswith(DEFAULT_SUPERVISOR_TASK) or "Runtime ACL-X bundle follows." in text

    @staticmethod
    def _is_system_user_message(text: str) -> bool:
        if not text:
            return False
        return text.startswith("# AGENTS.md instructions") or text.startswith("<environment_context>")


class ChatJobManager:
    def __init__(self, codex_home: Path, store: SessionStore, ui_state: UIStateStore) -> None:
        self.codex_home = codex_home
        self.store = store
        self.ui_state = ui_state
        self.supervisor = ACLXSupervisor()
        self.runtime_bridge = ACLXRuntimeBridge()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def launch_send(self, *, thread_id: str, message: str, cwd: str) -> dict[str, Any]:
        job_id = f"job:{uuid.uuid4().hex[:12]}"
        job = {
            "id": job_id,
            "thread_id": thread_id,
            "result_thread_id": thread_id,
            "status": "queued",
            "message": message,
            "cwd": cwd,
            "created_at": _utc_now_iso(),
            "finished_at": None,
            "error": "",
        }
        with self.lock:
            self.jobs[job_id] = job
        thread = threading.Thread(target=self._run_send, args=(job_id, thread_id, message, cwd), daemon=True)
        thread.start()
        return dict(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def _run_send(self, job_id: str, thread_id: str, message: str, cwd: str) -> None:
        self._patch(job_id, status="running")
        try:
            if thread_id.startswith("draft:"):
                result_thread_id = self._run_new_thread(thread_id, message, cwd)
            else:
                result_thread_id = self._run_existing_thread(thread_id, message, cwd)
        except Exception as exc:  # pragma: no cover
            self._patch(job_id, status="failed", finished_at=_utc_now_iso(), error=str(exc))
            return
        self._patch(job_id, status="completed", finished_at=_utc_now_iso(), result_thread_id=result_thread_id)

    def _run_new_thread(self, draft_id: str, message: str, cwd: str) -> str:
        before_ids = self.store.active_session_ids()
        payload = self.supervisor.build_payload(message, cwd=cwd)
        result = self.supervisor.run_codex(payload)
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "新线程创建失败").strip()
            raise RuntimeError(error)
        session_id = self._extract_session_id(result.stdout + "\n" + result.stderr) or self.store.newest_session_id(before_ids)
        if not session_id:
            raise RuntimeError("已完成运行，但未找到新会话编号。")
        self.ui_state.promote_draft(draft_id, session_id, message)
        return f"session:{session_id}"

    def _run_existing_thread(self, thread_id: str, message: str, cwd: str) -> str:
        session_id = thread_id.split(":", 1)[1]
        result = self._resume_codex(session_id=session_id, prompt=message, cwd=cwd)
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "续聊失败").strip()
            raise RuntimeError(error)
        return thread_id

    def _resume_codex(self, *, session_id: str, prompt: str, cwd: str) -> subprocess.CompletedProcess[str]:
        aclx_prompt = self._build_resume_prompt(prompt=prompt, cwd=cwd)
        command = [
            self._resolve_codex_executable(),
            "exec",
            "--skip-git-repo-check",
            "-C",
            cwd,
            "--output-last-message",
        ]
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".txt", delete=False) as handle:
            output_path = Path(handle.name)
        command.append(str(output_path))
        command.extend(["resume", session_id, aclx_prompt])
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        try:
            last_message = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        finally:
            output_path.unlink(missing_ok=True)
        if last_message:
            result.stdout = (result.stdout or "") + ("\n" if result.stdout else "") + last_message
        return result

    def _build_resume_prompt(self, *, prompt: str, cwd: str) -> str:
        session_module = load_ctx_module("session")
        if session_module is not None:
            run_turn = getattr(session_module, "run_codex_turn", None)
            if callable(run_turn):
                try:
                    value = run_turn(
                        active_phase="resume",
                        task_description=prompt,
                        tool_results=[],
                        hard_limit=8000,
                        cwd=cwd,
                    )
                except TypeError:
                    try:
                        value = run_turn(
                            active_phase="resume",
                            task_description=prompt,
                            tool_results=[],
                            hard_limit=8000,
                        )
                    except TypeError:
                        value = ""
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return self.runtime_bridge.encode_user_text(prompt, cwd=cwd)

    def _resolve_codex_executable(self) -> str:
        for candidate in ("codex.cmd", "codex.exe", "codex"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return "codex"

    @staticmethod
    def _extract_session_id(text: str) -> str | None:
        match = UUID_RE.search(text or "")
        return match.group(0) if match else None

    def _patch(self, job_id: str, **updates: Any) -> None:
        with self.lock:
            self.jobs[job_id].update(updates)


class ACLXUIHandler(BaseHTTPRequestHandler):
    store = SessionStore()
    ui_state = UIStateStore(default_codex_home())
    jobs = ChatJobManager(default_codex_home(), store, ui_state)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            return self._respond_asset("index.html", "text/html; charset=utf-8")
        if parsed.path == "/styles.css":
            return self._respond_asset("styles.css", "text/css; charset=utf-8")
        if parsed.path == "/app.js":
            return self._respond_asset("app.js", "application/javascript; charset=utf-8")
        if parsed.path == "/api/health":
            return self._respond_json({"ok": True, "time": _utc_now_iso()})
        if parsed.path == "/api/workspaces":
            return self._respond_json(self.store.list_workspaces())
        if parsed.path == "/api/archived":
            return self._respond_json({"threads": self.store.list_recent_archived_threads()})
        if parsed.path.startswith("/api/thread/"):
            thread_id = unquote(parsed.path.split("/api/thread/", 1)[1])
            thread = self.store.get_thread(thread_id)
            if not thread:
                return self._respond_json({"error": "未找到线程。"}, status=HTTPStatus.NOT_FOUND)
            return self._respond_json(thread)
        if parsed.path.startswith("/api/jobs/"):
            job_id = unquote(parsed.path.rsplit("/", 1)[-1])
            job = self.jobs.get(job_id)
            if not job:
                return self._respond_json({"error": "未找到任务。"}, status=HTTPStatus.NOT_FOUND)
            return self._respond_json(job)
        return self._respond_json({"error": "未找到接口。"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_body()
        except ValueError as exc:
            return self._respond_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        if parsed.path == "/api/thread/new":
            cwd = str(payload.get("cwd") or "").strip()
            if not self._is_valid_workspace(cwd):
                return self._respond_json({"error": "工作区路径无效，必须是存在的绝对文件夹路径。"}, status=HTTPStatus.BAD_REQUEST)
            return self._respond_json(self.ui_state.create_draft(cwd), status=HTTPStatus.CREATED)

        if parsed.path.startswith("/api/thread/") and parsed.path.endswith("/archive"):
            thread_id = unquote(parsed.path[len("/api/thread/") : -len("/archive")]).rstrip("/")
            try:
                archived = self.store.archive_thread(thread_id)
            except FileNotFoundError:
                return self._respond_json({"error": "未找到线程。"}, status=HTTPStatus.NOT_FOUND)
            return self._respond_json({"archived": archived})

        if parsed.path.startswith("/api/thread/") and parsed.path.endswith("/send"):
            thread_id = unquote(parsed.path[len("/api/thread/") : -len("/send")]).rstrip("/")
            thread = self.store.get_thread(thread_id)
            if not thread:
                return self._respond_json({"error": "未找到线程。"}, status=HTTPStatus.NOT_FOUND)
            message = str(payload.get("message") or "").strip()
            if not message:
                return self._respond_json({"error": "消息不能为空。"}, status=HTTPStatus.BAD_REQUEST)
            job = self.jobs.launch_send(thread_id=thread_id, message=message, cwd=str(thread.get("cwd") or DEFAULT_CODEX_CWD))
            return self._respond_json(job, status=HTTPStatus.ACCEPTED)

        if parsed.path.startswith("/api/archived/") and parsed.path.endswith("/restore"):
            archive_id = unquote(parsed.path[len("/api/archived/") : -len("/restore")]).rstrip("/")
            try:
                restored = self.store.restore_archived_thread(archive_id)
            except FileNotFoundError:
                return self._respond_json({"error": "未找到归档线程。"}, status=HTTPStatus.NOT_FOUND)
            return self._respond_json(restored)

        return self._respond_json({"error": "未找到接口。"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _respond_asset(self, name: str, content_type: str) -> None:
        path = ASSET_DIR / name
        if not path.exists():
            return self._respond_json({"error": "缺少界面资源。"}, status=HTTPStatus.NOT_FOUND)
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _respond_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size) if size else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("请求体不是合法 JSON。") from exc
        if not isinstance(value, dict):
            raise ValueError("请求体必须是对象。")
        return value

    @staticmethod
    def _is_valid_workspace(cwd: str) -> bool:
        if not cwd:
            return False
        path = Path(cwd)
        return path.is_absolute() and path.exists() and path.is_dir()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ACL-X supervisor session viewer")
    parser.add_argument("--host", default=DEFAULT_UI_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_UI_PORT)
    parser.add_argument("--codex-home", default=str(default_codex_home()))
    parser.add_argument("--open", action="store_true")
    return parser


def serve(*, host: str, port: int, codex_home: str, open_browser: bool = False) -> None:
    base = Path(codex_home)
    ui_state = UIStateStore(base)
    store = SessionStore(base, ui_state=ui_state)
    ACLXUIHandler.ui_state = ui_state
    ACLXUIHandler.store = store
    ACLXUIHandler.jobs = ChatJobManager(base, store, ui_state)
    server = ThreadingHTTPServer((host, port), ACLXUIHandler)
    url = f"http://{host}:{port}"
    print(f"ACL-X supervisor UI listening on {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    serve(host=args.host, port=args.port, codex_home=args.codex_home, open_browser=args.open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
