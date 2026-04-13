from __future__ import annotations


def collect_ready_steps(steps: list[str]) -> list[str]:
    cleaned: list[str] = []
    for step in steps:
        text = (step or "").strip().lower()
        if not text:
            continue
        cleaned.append(text)
    return sorted(set(cleaned))
