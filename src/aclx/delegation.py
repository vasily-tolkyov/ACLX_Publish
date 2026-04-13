from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .adapters import ACLXAdapter


DEFAULT_HEADER = "Continue from this ACL-X state bundle."


@dataclass(slots=True)
class DelegationPayload:
    task: str | None
    aclx: str
    mode: str = "c"
    aclx_only: bool = False

    def render(self) -> str:
        if self.aclx_only or not self.task:
            return self.aclx
        return f"{self.task}\n{self.aclx}"


class ACLXDelegation:
    def __init__(self, adapter: ACLXAdapter | None = None):
        self.adapter = adapter or ACLXAdapter()

    def from_handoff_obj(
        self,
        data: dict[str, Any],
        *,
        task: str | None = DEFAULT_HEADER,
        mode: str = "c",
        aclx_only: bool = False,
    ) -> DelegationPayload:
        aclx = self.adapter.handoff_obj_to_aclx(data, mode=mode)
        return DelegationPayload(task=task, aclx=aclx, mode=mode, aclx_only=aclx_only)

    def from_handoff_json(
        self,
        text: str,
        *,
        task: str | None = DEFAULT_HEADER,
        mode: str = "c",
        aclx_only: bool = False,
    ) -> DelegationPayload:
        return self.from_handoff_obj(json.loads(text), task=task, mode=mode, aclx_only=aclx_only)

    def from_aclx(
        self,
        aclx: str,
        *,
        task: str | None = DEFAULT_HEADER,
        aclx_only: bool = False,
    ) -> DelegationPayload:
        return DelegationPayload(task=task, aclx=aclx, mode="c", aclx_only=aclx_only)

    def payload_obj(self, payload: DelegationPayload) -> dict[str, Any]:
        obj = {"a": payload.aclx}
        if payload.task and not payload.aclx_only:
            obj["t"] = payload.task
        if payload.mode != "c":
            obj["m"] = payload.mode
        if payload.aclx_only:
            obj["o"] = 1
        return obj

    def payload_json(self, payload: DelegationPayload, *, pretty: bool = False) -> str:
        obj = self.payload_obj(payload)
        if pretty:
            return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)
        return json.dumps(obj, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    def payload_from_json(self, text: str) -> DelegationPayload:
        data = json.loads(text)
        return DelegationPayload(
            task=data.get("t"),
            aclx=data["a"],
            mode=data.get("m", "c"),
            aclx_only=bool(data.get("o", 0)),
        )
