from __future__ import annotations

from .model import OntologyPack

SLOT_CODES = {
    "actor": "ac",
    "action": "aa",
    "object": "ob",
    "context": "cx",
    "constraint": "ct",
    "evidence": "ev",
    "status": "st",
}
SLOT_NAMES = {value: key for key, value in SLOT_CODES.items()}

META_CODES = {
    "source": "so",
    "scope": "sc",
    "priority": "py",
    "certainty": "cy",
    "time": "tm",
    "target": "tg",
    "version": "vr",
}
META_NAMES = {value: key for key, value in META_CODES.items()}

MOD_TAG_CODES = {
    "neg": "ng",
    "cond": "cd",
    "goal": "gl",
    "ask": "ak",
    "must": "ms",
    "may": "my",
    "prob": "pb",
    "counterfactual": "cf",
}
MOD_TAG_NAMES = {value: key for key, value in MOD_TAG_CODES.items()}

CORE_SYMBOL_TABLE = {
    "E": {
        "agent": "ga",
        "user": "gu",
        "peer": "gp",
        "task": "tk",
        "plan": "pn",
        "message": "mg",
        "tool": "tl",
        "result": "rs",
        "constraint": "ct",
        "evidence": "ev",
        "error": "er",
        "state": "st",
        "question": "qq",
        "goal": "gl",
        "time": "tm",
        "memory": "mm",
        "context": "cx",
        "proof": "pf",
    },
    "R": {
        "is": "is",
        "has": "hs",
        "causes": "cs",
        "before": "bf",
        "after": "af",
        "needs": "nd",
        "about": "ab",
        "with": "wt",
        "because": "bc",
        "supports": "sp",
        "conflicts": "cf",
        "refers": "rf",
    },
    "A": {
        "say": "sy",
        "ask": "ak",
        "plan": "pl",
        "do": "do",
        "report": "rp",
        "update": "up",
        "verify": "vf",
        "call": "cl",
        "think": "th",
        "explain": "ex",
        "compare": "cm",
        "delegate": "dg",
        "solve": "sv",
    },
    "Q": {
        "true": "tr",
        "false": "fl",
        "goal": "go",
        "open": "op",
        "done": "dn",
        "blocked": "bk",
        "ask": "qa",
        "must": "ms",
        "may": "my",
        "prob": "pb",
        "uncertain": "uc",
        "counterfactual": "cf",
        "urgent": "ug",
        "high": "hi",
        "low": "lo",
    },
    "L": {
        "and": "an",
        "or": "or",
        "not": "nt",
        "if": "if",
        "then": "th",
        "implies": "im",
        "forall": "fa",
        "exists": "ex",
        "counterfactual": "cf",
    },
    "X": {
        "source": "so",
        "scope": "sc",
        "priority": "py",
        "certainty": "cy",
        "time": "tm",
        "version": "vr",
        "target": "tg",
    },
}

CORE_LABELS = {
    "E": {key: key for key in CORE_SYMBOL_TABLE["E"]},
    "R": {key: key for key in CORE_SYMBOL_TABLE["R"]},
    "A": {key: key for key in CORE_SYMBOL_TABLE["A"]},
    "Q": {key: key for key in CORE_SYMBOL_TABLE["Q"]},
    "L": {key: key for key in CORE_SYMBOL_TABLE["L"]},
    "X": {key: key for key in CORE_SYMBOL_TABLE["X"]},
}

CORE_DEFAULTS = {
    "metadata": {
        "source": "self",
        "scope": "session",
        "priority": 0,
        "certainty": 1.0,
    }
}

ACTION_KEYWORDS = {
    "plan": ["plan", "design", "spec", "implement", "build", "draft", "\u8bbe\u8ba1", "\u5b9e\u73b0", "\u6784\u5efa"],
    "report": ["report", "summarize", "summary", "status", "\u603b\u7ed3", "\u6c47\u62a5"],
    "update": ["update", "revise", "patch", "change", "\u66f4\u65b0", "\u4fee\u6539"],
    "verify": ["verify", "check", "validate", "test", "\u9a8c\u8bc1", "\u68c0\u67e5", "\u6d4b\u8bd5"],
    "ask": ["?", "ask", "please", "help", "\u8bf7", "\u5417", "\u5e2e\u6211"],
    "think": ["think", "reason", "reflect", "\u601d\u8003", "\u63a8\u7406"],
    "explain": ["explain", "because", "why", "\u89e3\u91ca", "\u539f\u56e0"],
    "call": ["call", "invoke", "tool", "api", "\u5de5\u5177", "\u8c03\u7528"],
    "solve": ["solve", "fix", "resolve", "\u89e3\u51b3", "\u4fee\u590d"],
}

CONCEPT_KEYWORDS = {
    "task": ["task", "job", "work", "\u4efb\u52a1", "\u5de5\u4f5c"],
    "plan": ["plan", "spec", "design", "\u8ba1\u5212", "\u65b9\u6848"],
    "message": ["message", "prompt", "thread", "\u6d88\u606f", "\u7ebf\u7a0b"],
    "tool": ["tool", "api", "function", "\u5de5\u5177", "\u51fd\u6570"],
    "result": ["result", "output", "answer", "\u7ed3\u679c", "\u8f93\u51fa"],
    "constraint": ["constraint", "rule", "limit", "\u7ea6\u675f", "\u9650\u5236"],
    "evidence": ["evidence", "proof", "trace", "\u8bc1\u636e", "\u8bc1\u660e"],
    "error": ["error", "failure", "bug", "\u9519\u8bef", "\u5931\u8d25"],
    "state": ["state", "status", "phase", "\u72b6\u6001", "\u9636\u6bb5"],
    "question": ["question", "ask", "query", "\u95ee\u9898", "\u8be2\u95ee"],
    "goal": ["goal", "objective", "target", "\u76ee\u6807"],
    "context": ["context", "background", "\u4e0a\u4e0b\u6587", "\u80cc\u666f"],
}

MOD_KEYWORDS = {
    "neg": [" not ", " no ", "never", "without", "\u4e0d", "\u4e0d\u8981", "\u4e0d\u80fd"],
    "cond": ["if", "when", "unless", "\u5982\u679c", "\u5f53", "\u9664\u975e"],
    "goal": ["goal", "aim", "target", "\u76ee\u6807"],
    "ask": ["?", "please", "ask", "\u8bf7", "\u5417"],
    "must": ["must", "should", "need to", "required", "\u5fc5\u987b", "\u9700\u8981", "\u5e94\u5f53"],
    "may": ["may", "can", "optional", "\u53ef\u4ee5"],
    "prob": ["maybe", "probably", "likely", "\u53ef\u80fd", "\u6216\u8bb8"],
    "counterfactual": ["would have", "if only", "counterfactual", "\u672c\u53ef\u4ee5", "\u53cd\u4e8b\u5b9e"],
}

_PACKS: dict[tuple[str, str], OntologyPack] = {}


def core_pack() -> OntologyPack:
    key = ("c0", "1")
    if key not in _PACKS:
        _PACKS[key] = OntologyPack(
            pack_id="c0",
            version="1",
            symbol_table=CORE_SYMBOL_TABLE,
            defaults=CORE_DEFAULTS,
            labels=CORE_LABELS,
        )
    return _PACKS[key]


def get_pack(pack_id: str = "c0", version: str = "1") -> OntologyPack:
    key = (pack_id, version)
    if key == ("c0", "1"):
        return core_pack()
    try:
        return _PACKS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown ontology pack {pack_id}@{version}") from exc
