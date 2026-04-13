from __future__ import annotations

from typing import Any

from .adapters import ACLXAdapter
from .transcoder import ACLXTranscoder


class ACLXRuntimeBridge:
    def __init__(self, transcoder: ACLXTranscoder | None = None, adapter: ACLXAdapter | None = None) -> None:
        self.transcoder = transcoder or ACLXTranscoder()
        self.adapter = adapter or ACLXAdapter(transcoder=self.transcoder)

    def encode_user_text(self, text: str, *, cwd: str | None = None, source: str = "user") -> str:
        handoff: dict[str, Any] = {
            "goal": text,
            "source": source,
            "scope": "session",
            "certainty": 1.0,
        }
        if cwd:
            handoff["evidence"] = [f"cwd={cwd}"]
        return self.adapter.handoff_obj_to_aclx(handoff, mode="c")

    def encode_supervisor_task(self, task: str, *, cwd: str) -> str:
        handoff = {
            "goal": task,
            "current_state": "Execute the user task with ACL-X-first runtime-visible state.",
            "next_actions": [
                "Use ACL-X for visible machine-only state and handoffs.",
                "Keep human output short unless the user asked otherwise.",
                "Avoid unnecessary shell commands.",
            ],
            "evidence": [f"cwd={cwd}"],
            "priority": 1,
            "certainty": 0.9,
            "scope": "local",
            "source": "aclx-supervisor",
        }
        return self.adapter.handoff_obj_to_aclx(handoff, mode="c")

    def is_aclx(self, text: str) -> bool:
        candidate = (text or "").strip()
        if not candidate.startswith("h|"):
            return False
        try:
            self.transcoder.aclx_to_frame(candidate)
        except Exception:
            return False
        return True

    def display_text(self, text: str, *, role: str = "assistant") -> str:
        if not self.is_aclx(text):
            return text
        frame = self.transcoder.aclx_to_frame(text)
        raw_texts = self._raw_texts(frame)
        handoff = self.adapter.frame_to_handoff_obj(frame)

        if role == "user":
            user_goals = self._normalize_list(handoff.get("g") or handoff.get("goal"))
            if user_goals:
                return "\n".join(user_goals)
            if raw_texts:
                return "\n".join(raw_texts)

        summary = self._handoff_to_zh(handoff)
        if summary:
            return summary
        if raw_texts:
            return "\n".join(raw_texts)
        return self.transcoder.aclx_to_nl_gloss(text)

    def aclx_to_tool_json(self, text: str, *, pretty: bool = False) -> str:
        return self.adapter.aclx_to_tool_json(text, pretty=pretty)

    def tool_json_to_aclx(self, text: str) -> str:
        return self.adapter.tool_json_to_aclx(text)

    def _raw_texts(self, frame) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for escape in frame.escapes:
            if escape.kind != "raw":
                continue
            payload = escape.payload
            if isinstance(payload, str):
                text = payload.strip()
                if text and text not in seen:
                    values.append(text)
                    seen.add(text)
        return values

    def _handoff_to_zh(self, handoff: dict[str, Any]) -> str:
        lines: list[str] = []
        completed = self._normalize_list(handoff.get("d") or handoff.get("completed"))
        current_state = self._normalize_list(handoff.get("s") or handoff.get("current_state"))
        risks = self._normalize_list(handoff.get("r") or handoff.get("risks"))
        next_actions = self._normalize_list(handoff.get("n") or handoff.get("next_actions"))
        goals = self._normalize_list(handoff.get("g") or handoff.get("goal"))
        evidence = [
            item
            for item in self._normalize_list(handoff.get("e") or handoff.get("evidence"))
            if not item.startswith("cwd=")
        ]

        if completed:
            lines.append("已完成：" + "；".join(completed))
        if current_state:
            lines.append("当前状态：" + "；".join(current_state))
        if next_actions:
            lines.append("下一步：" + "；".join(next_actions))
        if risks:
            lines.append("风险：" + "；".join(risks))
        if not lines and goals:
            lines.append("目标：" + "；".join(goals))
        if evidence and len(lines) < 3:
            lines.append("依据：" + "；".join(evidence[:2]))
        return "\n".join(lines)

    @staticmethod
    def _normalize_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                text = str(item or "").strip()
                if text:
                    result.append(text)
            return result
        text = str(value or "").strip()
        return [text] if text else []
