from __future__ import annotations

import re
from typing import Iterable

from .codec import ACLXCodec
from .ir import frame_from_dict, frame_to_dict
from .model import Clause, EscapeBlock, EscapeRef, ModTag, MsgFrame, SymbolRef, ThoughtFrame
from .ontology import ACTION_KEYWORDS, CONCEPT_KEYWORDS, MOD_KEYWORDS, core_pack

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class ACLXTranscoder:
    def __init__(self, codec: ACLXCodec | None = None):
        self.pack = core_pack()
        self.codec = codec or ACLXCodec(self.pack)

    def nl_to_frame(self, text: str, mode: str = "c") -> MsgFrame:
        normalized = f" {text.lower()} "
        action = self._best_action(normalized)
        obj = self._best_match(normalized, CONCEPT_KEYWORDS, default="message")
        mods = self._detect_mods(normalized)

        clause = Clause(
            ref="1",
            slots={
                "actor": SymbolRef("E", "agent"),
                "action": SymbolRef("A", action),
                "object": SymbolRef("E", obj),
            },
            mods=mods,
        )

        if any(mod.key == "ask" for mod in mods) and "status" not in clause.slots:
            clause.slots["status"] = SymbolRef("Q", "ask")
        elif any(mod.key == "goal" for mod in mods) and "status" not in clause.slots:
            clause.slots["status"] = SymbolRef("Q", "goal")

        frame_type = ThoughtFrame if mode == "t" else MsgFrame
        frame = frame_type(mode=mode, pack_ref=self.pack.pack_id, version=self.pack.version)
        frame.body.append(clause)

        coverage_hits = self._coverage_hits(normalized)
        if coverage_hits < 2 or (len(text) > 72 and coverage_hits < 4):
            frame.escapes.append(EscapeBlock(ref="1", kind="raw", payload=text, mime="text/plain"))
            clause.slots["context"] = EscapeRef("1")

        certainty = self._certainty_from_mods(mods)
        if certainty != 1.0:
            frame.metadata["certainty"] = certainty
        return frame

    def nl_to_aclx(self, text: str, mode: str = "c") -> str:
        return self.codec.encode(self.nl_to_frame(text, mode=mode))

    def aclx_to_frame(self, text: str) -> MsgFrame:
        return self.codec.decode(text)

    def aclx_to_json_ir(self, text: str) -> dict:
        return frame_to_dict(self.aclx_to_frame(text))

    def aclx_to_nl_gloss(self, text: str) -> str:
        return self.frame_to_gloss(self.aclx_to_frame(text))

    def frame_to_gloss(self, frame: MsgFrame) -> str:
        if not frame.body:
            return "empty frame"
        clause = frame.body[0]
        actor = self._resolve_value(frame, clause.slots.get("actor"))
        action = self._resolve_value(frame, clause.slots.get("action"))
        obj = self._resolve_value(frame, clause.slots.get("object"))
        context = self._resolve_value(frame, clause.slots.get("context"))
        status = self._resolve_value(frame, clause.slots.get("status"))

        prefixes = []
        if any(mod.key == "counterfactual" and mod.value for mod in clause.mods):
            prefixes.append("counterfactually")
        if any(mod.key == "cond" and mod.value for mod in clause.mods):
            prefixes.append("if needed")
        if any(mod.key == "neg" and mod.value for mod in clause.mods):
            prefixes.append("not")
        if any(mod.key == "must" and mod.value for mod in clause.mods):
            prefixes.append("must")
        elif any(mod.key == "may" and mod.value for mod in clause.mods):
            prefixes.append("may")

        sentence = " ".join(part for part in prefixes + [actor, action, obj] if part)
        if status:
            sentence += f" with status {status}"
        if context:
            sentence += f" in context {context}"
        certainty = frame.metadata.get("certainty")
        if isinstance(certainty, (int, float)) and certainty != 1:
            sentence += f" (certainty {certainty:.2f})"
        return sentence.strip()

    def json_ir_to_frame(self, data: dict) -> MsgFrame:
        return frame_from_dict(data)

    def _best_match(self, normalized: str, table: dict[str, list[str]], default: str) -> str:
        best = default
        best_score = 0
        for name, keywords in table.items():
            score = sum(1 for keyword in keywords if self._keyword_hit(normalized, keyword))
            if score > best_score:
                best = name
                best_score = score
        return best

    def _best_action(self, normalized: str) -> str:
        scores = {
            name: sum(1 for keyword in keywords if self._keyword_hit(normalized, keyword))
            for name, keywords in ACTION_KEYWORDS.items()
        }
        non_ask = {name: score for name, score in scores.items() if name != "ask"}
        best_name = max(non_ask, key=non_ask.get, default="say")
        if non_ask.get(best_name, 0) > 0:
            return best_name
        if scores.get("ask", 0) > 0:
            return "ask"
        return "say"

    def _detect_mods(self, normalized: str) -> list[ModTag]:
        mods = []
        for name, keywords in MOD_KEYWORDS.items():
            score = sum(1 for keyword in keywords if self._keyword_hit(normalized, keyword))
            if not score:
                continue
            if name == "prob":
                mods.append(ModTag(name, 0.6))
            else:
                mods.append(ModTag(name, True))
        return mods

    def _certainty_from_mods(self, mods: Iterable[ModTag]) -> float:
        for mod in mods:
            if mod.key == "prob":
                value = mod.value
                if isinstance(value, (int, float)):
                    return float(value)
                return 0.6
            if mod.key == "counterfactual":
                return 0.4
        return 1.0

    def _coverage_hits(self, normalized: str) -> int:
        hits = 0
        for table in (ACTION_KEYWORDS, CONCEPT_KEYWORDS, MOD_KEYWORDS):
            if any(self._keyword_hit(normalized, keyword) for keywords in table.values() for keyword in keywords):
                hits += 1
        tokens = TOKEN_RE.findall(normalized)
        hits += min(2, len(tokens) // 8)
        return hits

    def _keyword_hit(self, normalized: str, keyword: str) -> bool:
        if keyword in {"?", "!"}:
            return keyword in normalized
        if keyword.isascii() and " " not in keyword and keyword.replace("_", "").isalnum():
            return re.search(rf"\b{re.escape(keyword)}\b", normalized) is not None
        return keyword in normalized

    def _resolve_value(self, frame: MsgFrame, value, seen: set[str] | None = None) -> str:
        if value is None:
            return ""
        seen = seen or set()
        if isinstance(value, SymbolRef):
            return self.pack.label_for_symbol(value)
        if isinstance(value, EscapeRef):
            escape = next((item for item in frame.escapes if item.ref == value.value), None)
            if escape is None:
                return f"escape:{value.value}"
            return str(escape.payload)
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if hasattr(value, "value"):
            token = value.value
            if token in seen:
                return token
            seen.add(token)
            if value.__class__.__name__ == "AliasRef":
                return self._resolve_value(frame, frame.session_aliases.get(token), seen)
            if value.__class__.__name__ == "NodeRef":
                node = next((item for item in frame.nodes if item.ref == token), None)
                if node is None:
                    return f"node:{token}"
                return self._resolve_value(frame, node.symbol, seen)
            if value.__class__.__name__ == "FrameRef":
                return f"frame:{token}"
        return str(value)
