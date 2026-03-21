from __future__ import annotations

import re


PROBLEM_REF_RE = re.compile(r"^\s*[Pp]?(\d+)\s*$")


def format_problem_ref(display_id: int) -> str:
    return f"P{display_id}"


def parse_problem_ref(raw: str) -> int | None:
    match = PROBLEM_REF_RE.fullmatch(raw)
    if match is None:
        return None
    value = int(match.group(1))
    return value if value > 0 else None
