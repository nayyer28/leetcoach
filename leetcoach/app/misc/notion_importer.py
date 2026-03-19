from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Callable
import json
import os
import re
from typing import Any
from urllib import error, parse, request

from leetcoach.app.application.problems.log_problem import LogProblemInput, log_problem
from leetcoach.app.infrastructure.config.app_config import AppConfig


NOTION_VERSION = "2022-06-28"

LEETCODE_RE = re.compile(r"https?://leetcode\.com/problems/([^/?#]+)/?", re.IGNORECASE)
NEETCODE_RE = re.compile(r"https?://neetcode\.io/problems/([^/?#]+)/?", re.IGNORECASE)
TITLE_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?P<title>.+?)(?:\s*\((?P<difficulty>Easy|Medium|Hard)\))?(?:\s*\((?P<date>[^)]+)\))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedProblem:
    title: str
    difficulty: str
    pattern: str
    solved_at: str
    leetcode_slug: str | None
    neetcode_slug: str | None
    concepts: str | None
    time_complexity: str | None
    space_complexity: str | None
    notes: str | None
    source_page_title: str
    source_problem_line: str


@dataclass(frozen=True)
class ImportStats:
    parsed_total: int
    parsed_valid: int
    parsed_invalid: int
    inserted_or_updated: int


def _hyphenate_notion_id(raw: str) -> str:
    value = raw.replace("-", "").strip()
    if len(value) != 32:
        return raw
    return (
        f"{value[0:8]}-{value[8:12]}-{value[12:16]}-"
        f"{value[16:20]}-{value[20:32]}"
    )


def _extract_page_id(page_url: str) -> str:
    no_query = page_url.split("?", 1)[0]
    token = no_query.rstrip("/").split("-")[-1]
    if len(token) != 32:
        raise ValueError(f"Could not extract Notion page id from URL: {page_url}")
    return _hyphenate_notion_id(token)


class NotionApiClient:
    def __init__(self, token: str, *, timeout_seconds: int = 30) -> None:
        self._token = token
        self._timeout_seconds = timeout_seconds

    def _get_json(self, url: str) -> dict[str, Any]:
        req = request.Request(
            url=url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Notion API error ({exc.code}): {detail}") from exc
        return json.loads(payload)

    def list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        children: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            query = {"page_size": "100"}
            if cursor:
                query["start_cursor"] = cursor
            qs = parse.urlencode(query)
            url = f"https://api.notion.com/v1/blocks/{block_id}/children?{qs}"
            payload = self._get_json(url)
            children.extend(payload.get("results", []))
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
        return children


def _rich_text_plain(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not block_type:
        return ""
    payload = block.get(block_type, {})
    rich_text = payload.get("rich_text", [])
    return "".join(part.get("plain_text", "") for part in rich_text).strip()


def _rich_text_links(block: dict[str, Any]) -> list[str]:
    block_type = block.get("type")
    if not block_type:
        return []
    payload = block.get(block_type, {})
    links: list[str] = []
    for part in payload.get("rich_text", []):
        href = part.get("href")
        if href:
            links.append(href)
    return links


def _parse_title_difficulty_date(
    line: str, *, default_year: int, timezone_name: str
) -> tuple[str, str, str] | None:
    text = line.strip().rstrip(":")
    match = TITLE_RE.match(text)
    if not match:
        return None

    title = match.group("title").strip().rstrip(":")
    difficulty = (match.group("difficulty") or "medium").lower()
    date_text = (match.group("date") or "").strip()
    solved_at = _parse_date_to_utc_iso(
        date_text=date_text, default_year=default_year, timezone_name=timezone_name
    )
    return (title, difficulty, solved_at)


def _parse_date_to_utc_iso(
    *, date_text: str, default_year: int, timezone_name: str
) -> str:
    if not date_text:
        return datetime.now(UTC).isoformat()

    date_text = date_text.strip()
    patterns = [
        ("%d.%m.%Y", date_text),
        ("%d.%m.%y", date_text),
    ]
    if re.fullmatch(r"\d{1,2}\.\d{1,2}", date_text):
        patterns.append(("%d.%m.%Y", f"{date_text}.{default_year}"))

    for fmt, value in patterns:
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            parsed = None
    else:
        return datetime.now(UTC).isoformat()

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = UTC
    local = parsed.replace(tzinfo=tz)
    return local.astimezone(UTC).isoformat()


def _slug_from_urls(urls: list[str], regex: re.Pattern[str]) -> str | None:
    for url in urls:
        match = regex.search(url)
        if match:
            return match.group(1)
    return None


def _extract_labeled_text(lines: list[str], label: str) -> str | None:
    matches: list[str] = []
    prefix = f"{label.lower()}:"
    for line in lines:
        normalized = line.strip()
        low = normalized.lower()
        if prefix in low:
            idx = low.index(prefix)
            content = normalized[idx + len(prefix) :].strip()
            if content:
                matches.append(content)
    if not matches:
        return None
    return "\n".join(matches)


def _parse_problem_from_block(
    block: dict[str, Any],
    *,
    notion_client: NotionApiClient,
    pattern_title: str,
    default_year: int,
    timezone_name: str,
) -> ParsedProblem | None:
    title_line = _rich_text_plain(block)
    parsed = _parse_title_difficulty_date(
        title_line, default_year=default_year, timezone_name=timezone_name
    )
    if parsed is None:
        return None
    title, difficulty, solved_at = parsed

    children: list[dict[str, Any]] = []
    if block.get("has_children"):
        children = notion_client.list_block_children(_hyphenate_notion_id(block["id"]))
    lines: list[str] = []
    urls: list[str] = []

    stack = list(children)
    while stack:
        node = stack.pop(0)
        lines.append(_rich_text_plain(node))
        urls.extend(_rich_text_links(node))
        node_type = node.get("type")
        if node.get("has_children"):
            node_children = notion_client.list_block_children(
                _hyphenate_notion_id(node["id"])
            )
            stack.extend(node_children)

    leetcode_slug = _slug_from_urls(urls, LEETCODE_RE)
    neetcode_slug = _slug_from_urls(urls, NEETCODE_RE)

    concepts = _extract_labeled_text(lines, "concept")
    time_complexity = _extract_labeled_text(lines, "time")
    space_complexity = _extract_labeled_text(lines, "space")

    notes_lines = [
        line
        for line in lines
        if line
        and "url:" not in line.lower()
        and "leetcode:" not in line.lower()
        and "neetcode:" not in line.lower()
        and "concept:" not in line.lower()
        and not line.lower().startswith("time:")
        and not line.lower().startswith("space:")
    ]
    notes = "\n".join(notes_lines).strip() if notes_lines else None

    return ParsedProblem(
        title=title,
        difficulty=difficulty,
        pattern=pattern_title,
        solved_at=solved_at,
        leetcode_slug=leetcode_slug,
        neetcode_slug=neetcode_slug,
        concepts=concepts,
        time_complexity=time_complexity,
        space_complexity=space_complexity,
        notes=notes,
        source_page_title=pattern_title,
        source_problem_line=title_line,
    )


def parse_root_page(
    *,
    notion_client: NotionApiClient,
    root_page_url: str,
    default_year: int,
    timezone_name: str,
    progress: Callable[[str], None] | None = None,
) -> list[ParsedProblem]:
    root_id = _extract_page_id(root_page_url)
    if progress:
        progress(f"Fetching root page blocks: {root_id}")
    root_children = notion_client.list_block_children(root_id)
    pattern_pages = [b for b in root_children if b.get("type") == "child_page"]
    if progress:
        progress(f"Found {len(pattern_pages)} pattern pages")

    parsed: list[ParsedProblem] = []
    for idx, page in enumerate(pattern_pages, start=1):
        pattern_title = page.get("child_page", {}).get("title", "").strip() or "unknown"
        page_id = _hyphenate_notion_id(page.get("id", ""))
        if not page_id:
            continue
        if progress:
            progress(f"[{idx}/{len(pattern_pages)}] Parsing pattern page: {pattern_title}")
        blocks = notion_client.list_block_children(page_id)
        before = len(parsed)
        for block in blocks:
            if block.get("type") != "numbered_list_item":
                continue
            problem = _parse_problem_from_block(
                block,
                notion_client=notion_client,
                pattern_title=pattern_title,
                default_year=default_year,
                timezone_name=timezone_name,
            )
            if problem:
                parsed.append(problem)
        if progress:
            progress(
                f"[{idx}/{len(pattern_pages)}] Parsed {len(parsed) - before} problems from {pattern_title}"
            )
    return parsed


def run_import(
    *,
    config: AppConfig,
    root_page_url: str,
    telegram_user_id: str,
    telegram_chat_id: str,
    notion_token_env: str,
    default_year: int,
    apply: bool,
    progress: Callable[[str], None] | None = None,
) -> ImportStats:
    token = os.getenv(notion_token_env)
    if not token:
        raise RuntimeError(f"{notion_token_env} is not set")

    notion_client = NotionApiClient(token)
    if progress:
        progress("Starting Notion import")
    parsed = parse_root_page(
        notion_client=notion_client,
        root_page_url=root_page_url,
        default_year=default_year,
        timezone_name=config.timezone,
        progress=progress,
    )
    if progress:
        progress(f"Parsed total problem entries: {len(parsed)}")

    invalid = [problem for problem in parsed if not problem.neetcode_slug]
    valid = [problem for problem in parsed if problem.neetcode_slug]

    if invalid:
        print("Missing required neetcode slug for:")
        for idx, item in enumerate(invalid, start=1):
            print(
                f"{idx}. [{item.source_page_title}] {item.source_problem_line} "
                f"(parsed title: {item.title})"
            )
        if apply:
            raise RuntimeError("Cannot apply import: missing required neetcode slugs.")
    if progress:
        progress(f"Valid problems: {len(valid)} | Invalid problems: {len(invalid)}")

    applied = 0
    for idx, problem in enumerate(valid, start=1):
        if not apply:
            continue
        payload = LogProblemInput(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            timezone=config.timezone,
            title=problem.title,
            difficulty=problem.difficulty,
            leetcode_slug=problem.leetcode_slug,
            neetcode_slug=problem.neetcode_slug,
            pattern=problem.pattern,
            solved_at=problem.solved_at,
            concepts=problem.concepts,
            time_complexity=problem.time_complexity,
            space_complexity=problem.space_complexity,
            notes=problem.notes,
        )
        log_problem(config.db_path, payload)
        applied += 1
        if progress and idx % 10 == 0:
            progress(f"Applied {applied}/{len(valid)} problems")

    if progress:
        if apply:
            progress(f"Apply complete: {applied} upserted rows")
        else:
            progress("Dry-run complete (no writes)")

    return ImportStats(
        parsed_total=len(parsed),
        parsed_valid=len(valid),
        parsed_invalid=len(invalid),
        inserted_or_updated=applied,
    )
