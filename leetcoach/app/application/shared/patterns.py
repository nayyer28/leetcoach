from __future__ import annotations

import re

UNKNOWN_PATTERN_LEVEL = 999

# NeetCode roadmap-inspired ordering; same-level groups are alphabetical.
ROADMAP_PATTERN_LEVELS: dict[str, tuple[int, str]] = {
    "arrays and hashing": (1, "Arrays & Hashing"),
    "two pointers": (2, "Two Pointers"),
    "stack": (2, "Stack"),
    "binary search": (3, "Binary Search"),
    "sliding window": (3, "Sliding Window"),
    "linked list": (3, "Linked List"),
    "trees": (4, "Trees"),
    "tries": (5, "Tries"),
    "backtracking": (5, "Backtracking"),
    "heap priority queue": (5, "Heap / Priority Queue"),
    "graphs": (5, "Graphs"),
    "1 d dp": (6, "1-D DP"),
    "intervals": (6, "Intervals"),
    "greedy": (7, "Greedy"),
    "advanced graphs": (7, "Advanced Graphs"),
    "2 d dp": (7, "2-D DP"),
    "bit manipulation": (8, "Bit Manipulation"),
    "math geometry": (8, "Math & Geometry"),
}

ROADMAP_PATTERN_ALIASES: dict[str, str] = {
    "array and hashing": "arrays and hashing",
    "arrays hashing": "arrays and hashing",
    "two pointer": "two pointers",
    "linked lists": "linked list",
    "tree": "trees",
    "tree dfs": "trees",
    "tree bfs": "trees",
    "trie": "tries",
    "heap": "heap priority queue",
    "priority queue": "heap priority queue",
    "heaps": "heap priority queue",
    "graph": "graphs",
    "1d dp": "1 d dp",
    "dp 1d": "1 d dp",
    "1 d dynamic programming": "1 d dp",
    "2d dp": "2 d dp",
    "dp 2d": "2 d dp",
    "2 d dynamic programming": "2 d dp",
    "math and geometry": "math geometry",
    "bitwise": "bit manipulation",
}


def normalize_pattern_key(pattern: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", pattern.lower()).split())


def roadmap_pattern_info(pattern: str) -> tuple[int, str, str]:
    normalized = normalize_pattern_key(pattern)
    canonical = ROADMAP_PATTERN_ALIASES.get(normalized, normalized)
    if canonical in ROADMAP_PATTERN_LEVELS:
        level, label = ROADMAP_PATTERN_LEVELS[canonical]
        return level, label, canonical

    if "advanced" in normalized and "graph" in normalized:
        level, label = ROADMAP_PATTERN_LEVELS["advanced graphs"]
        return level, label, "advanced graphs"
    if "graph" in normalized:
        level, label = ROADMAP_PATTERN_LEVELS["graphs"]
        return level, label, "graphs"
    if "tree" in normalized:
        level, label = ROADMAP_PATTERN_LEVELS["trees"]
        return level, label, "trees"

    return UNKNOWN_PATTERN_LEVEL, pattern.strip() or "Unknown", normalized


def canonical_pattern_label(raw_value: str) -> str | None:
    normalized = normalize_pattern_key(raw_value)
    canonical = ROADMAP_PATTERN_ALIASES.get(normalized, normalized)
    info = ROADMAP_PATTERN_LEVELS.get(canonical)
    if info is not None:
        return info[1]
    if "advanced" in normalized and "graph" in normalized:
        return ROADMAP_PATTERN_LEVELS["advanced graphs"][1]
    if "graph" in normalized:
        return ROADMAP_PATTERN_LEVELS["graphs"][1]
    if "tree" in normalized:
        return ROADMAP_PATTERN_LEVELS["trees"][1]
    return None
