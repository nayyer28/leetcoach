from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib import error, request

import click

from leetcoach.app.application.ask.ask_service import (
    AskServiceError,
    AskServiceResult,
    ask_question,
)
from leetcoach.app.bootstrap.bootstrap import run
from leetcoach.app.infrastructure.config.app_config import load_config
from leetcoach.app.infrastructure.config.env import load_environment
from leetcoach.app.infrastructure.llm.gemini_provider import (
    DEFAULT_GEMINI_MODEL_PRIORITY,
    GeminiProvider,
)
from leetcoach.app.interface.scheduler.runner import (
    run_scheduler_loop,
    run_scheduler_once,
    scheduler_preflight,
)
from leetcoach.app.misc.migrate import migrate_database
from leetcoach.app.misc.notion_importer import run_import


@click.group(invoke_without_command=True, help="Leetcoach CLI")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """CLI entrypoint."""
    load_environment()
    if ctx.invoked_subcommand is None:
        raise SystemExit(run())


@cli.command("run")
def run_command() -> None:
    """Start app bootstrap."""
    raise SystemExit(run())


@cli.command("migrate")
def migrate_command() -> None:
    """Apply DB migrations."""
    config = load_config()
    raise SystemExit(migrate_database(config.db_path))


@cli.command("test")
@click.argument(
    "suite",
    required=False,
    default="all",
    type=click.Choice(["all", "unit", "integration"], case_sensitive=False),
)
@click.argument("target", required=False)
def test_command(suite: str, target: str | None) -> None:
    """Run test suites.

    Examples:
      lch test
      lch test unit
      lch test integration
      lch test unit tests.unit.dao.test_problem_reviews_dao
    """
    cmd_prefix = [sys.executable, "-W", "ignore::ResourceWarning", "-m", "unittest"]
    if target:
        cmd = [*cmd_prefix, "-v", target]
    else:
        start_dir = {
            "all": "tests",
            "unit": "tests/unit",
            "integration": "tests/integration",
        }[suite.lower()]
        cmd = [
            *cmd_prefix,
            "discover",
            "-s",
            start_dir,
            "-p",
            "test_*.py",
            "-v",
        ]
    result = subprocess.run(cmd, check=False)
    raise SystemExit(result.returncode)


def _mask_token(token: str | None) -> str:
    if not token:
        return "missing"
    if len(token) <= 10:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


def _check_telegram_get_me(
    token: str | None, timeout_seconds: float = 10.0
) -> tuple[bool, str]:
    if not token:
        return False, "LEETCOACH_TELEGRAM_BOT_TOKEN is missing"

    url = f"https://api.telegram.org/bot{token}/getMe"
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {detail}"
    except error.URLError as exc:
        return False, f"Network error: {exc.reason}"
    except TimeoutError:
        return False, "Request timed out"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False, f"Invalid JSON response: {body[:200]}"

    if payload.get("ok") is True:
        result = payload.get("result") or {}
        username = result.get("username", "unknown")
        bot_id = result.get("id", "unknown")
        return True, f"Telegram API reachable (bot @{username}, id={bot_id})"

    return False, f"Telegram API responded with error payload: {payload}"


@cli.command("bot")
def bot_command() -> None:
    """Run Telegram bot (long polling)."""
    try:
        from leetcoach.app.interface.bot.handlers import run_bot
    except ModuleNotFoundError as exc:
        raise click.ClickException(
            "Telegram dependencies are missing. Run: python -m pip install -e ."
        ) from exc
    config = load_config()
    raise SystemExit(run_bot(config))


@cli.command("scheduler")
@click.option("--once", is_flag=True, help="Run one scheduler tick and exit.")
@click.option(
    "--interval-seconds",
    default=60,
    show_default=True,
    type=int,
    help="Loop interval when running continuously.",
)
def scheduler_command(once: bool, interval_seconds: int) -> None:
    """Run reminder scheduler loop (outbound Telegram reminders)."""
    config = load_config()
    preflight = scheduler_preflight(config)
    if not preflight.ok:
        for issue in preflight.issues:
            click.echo(f"[scheduler.preflight] FAIL: {issue}")
        raise SystemExit(1)
    click.echo("[scheduler.preflight] OK")

    if once:
        stats = run_scheduler_once(config=config, progress=click.echo)
        click.echo(
            (
                f"[scheduler] scanned={stats.scanned} sent={stats.sent} "
                f"skipped={stats.skipped_already_reminded_today} "
                f"outside_hour={stats.skipped_outside_send_hour} failed={stats.failed} "
                f"due_unsent={stats.due_and_unsent} selected={stats.selected} "
                f"header_sent={stats.header_sent}"
            )
        )
        raise SystemExit(0 if stats.failed == 0 else 1)
    click.echo(
        f"[scheduler] starting loop (interval_seconds={interval_seconds})"
    )
    try:
        run_scheduler_loop(
            config=config, interval_seconds=interval_seconds, progress=click.echo
        )
    except KeyboardInterrupt:
        click.echo("[scheduler] stopped by user")
        raise SystemExit(0)


@cli.command("scheduler-doctor")
def scheduler_doctor_command() -> None:
    """Validate scheduler preflight state (token, db schema, scheduler config)."""
    config = load_config()
    click.echo("LeetCoach Scheduler Doctor")
    click.echo(f"- db_path: {config.db_path}")
    click.echo(f"- reminder_hour_local: {config.reminder_hour_local}")
    click.echo(f"- reminder_daily_max: {config.reminder_daily_max}")
    click.echo(f"- telegram_token: {_mask_token(config.telegram_bot_token)}")

    result = scheduler_preflight(config)
    if result.ok:
        click.echo("- scheduler_preflight: OK")
        raise SystemExit(0)

    click.echo("- scheduler_preflight: FAIL")
    for issue in result.issues:
        click.echo(f"  - {issue}")
    raise SystemExit(1)


@cli.command("doctor")
def doctor_command() -> None:
    """Check local config and Telegram connectivity."""
    config = load_config()
    click.echo("LeetCoach Doctor")
    click.echo(f"- env: {config.environment}")
    click.echo(f"- timezone: {config.timezone}")
    click.echo(f"- db_path: {config.db_path}")
    click.echo(f"- allowed_user_ids: {len(config.allowed_user_ids)} configured")
    click.echo(f"- telegram_token: {_mask_token(config.telegram_bot_token)}")

    ok, detail = _check_telegram_get_me(config.telegram_bot_token)
    status = "OK" if ok else "FAIL"
    click.echo(f"- telegram_getMe: {status} ({detail})")

    raise SystemExit(0 if ok else 1)


def _render_ask_trace(result: AskServiceResult) -> None:
    click.echo(f"request_id: {result.request_id}")
    click.echo(f"model: {result.model}")
    for event in result.trace_events:
        step_label = "-" if event.step is None else str(event.step)
        click.echo(f"[step {step_label}] {event.event}")
        click.echo(json.dumps(event.payload, indent=2, ensure_ascii=True, sort_keys=True))


def _render_ask_failure(exc: AskServiceError, *, json_output: bool, verbose: bool) -> None:
    if json_output:
        click.echo(
            json.dumps(
                {
                    "error": str(exc),
                    "model": exc.model,
                    "request_id": exc.request_id,
                    "tool_executions": [
                        {
                            "tool_name": execution.tool_name,
                            "arguments": execution.arguments,
                            "result": execution.result,
                        }
                        for execution in exc.tool_executions
                    ],
                    "trace_events": [
                        {
                            "event": event.event,
                            "step": event.step,
                            "payload": event.payload,
                        }
                        for event in exc.trace_events
                    ],
                },
                indent=2,
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return
    if verbose:
        _render_ask_trace(
            AskServiceResult(
                response_type="failure",
                model=exc.model,
                answer="",
                request_id=exc.request_id,
                tool_executions=exc.tool_executions,
                trace_events=exc.trace_events,
            )
        )
        click.echo("")
    raise click.ClickException(str(exc))


def _render_ask_result_text(result: AskServiceResult) -> str:
    parts: list[str] = []
    if result.response_type == "final_answer" and result.answer:
        parts.append(result.answer)
        parts.append(f"Confidence: {result.confidence}")
        parts.append(f"Tool fit: {result.tool_fit}")
        parts.append(f"Answer basis: {result.answer_basis}")
        parts.append(f"Comments: {result.comments}")
        return "\n\n".join(parts)
    if result.response_type == "cannot_answer_confidently":
        return f"I cannot answer this confidently right now.\n\nComments: {result.comments}"
    return result.answer or ""


@cli.group("admin")
def admin_group() -> None:
    """Developer/admin interfaces into app services."""


@admin_group.command("ask")
@click.option(
    "--user",
    "telegram_user_id",
    required=True,
    help="Telegram user id whose data should be queried.",
)
@click.option("--verbose", is_flag=True, help="Print ask trace events to the terminal.")
@click.option("--json-output", is_flag=True, help="Print the full ask result as JSON.")
@click.option(
    "--debug-prompts",
    is_flag=True,
    help="Include prompt/raw-model text in ask trace output.",
)
@click.argument("question", nargs=-1, required=True)
def admin_ask_command(
    telegram_user_id: str,
    verbose: bool,
    json_output: bool,
    debug_prompts: bool,
    question: tuple[str, ...],
) -> None:
    """Run the ask service locally for diagnostics."""
    cfg = load_config()
    if not cfg.gemini_api_key:
        raise click.ClickException("GEMINI_API_KEY is not configured")

    provider = GeminiProvider(
        api_key=cfg.gemini_api_key,
        model_priority=DEFAULT_GEMINI_MODEL_PRIORITY,
        max_transient_retries=1,
    )
    prompt_debug_previous = os.environ.get("LEETCOACH_ASK_DEBUG_PROMPTS")
    if debug_prompts:
        os.environ["LEETCOACH_ASK_DEBUG_PROMPTS"] = "1"
    try:
        try:
            result = ask_question(
                db_path=cfg.db_path,
                telegram_user_id=telegram_user_id,
                question=" ".join(question).strip(),
                provider=provider,
            )
        except AskServiceError as exc:
            _render_ask_failure(exc, json_output=json_output, verbose=verbose)
            return
    finally:
        if debug_prompts:
            if prompt_debug_previous is None:
                os.environ.pop("LEETCOACH_ASK_DEBUG_PROMPTS", None)
            else:
                os.environ["LEETCOACH_ASK_DEBUG_PROMPTS"] = prompt_debug_previous

    if json_output:
        click.echo(
            json.dumps(
                {
                    "response_type": result.response_type,
                    "answer": result.answer,
                    "confidence": result.confidence,
                    "tool_fit": result.tool_fit,
                    "answer_basis": result.answer_basis,
                    "comments": result.comments,
                    "model": result.model,
                    "request_id": result.request_id,
                    "tool_executions": [
                        {
                            "tool_name": execution.tool_name,
                            "arguments": execution.arguments,
                            "result": execution.result,
                        }
                        for execution in result.tool_executions
                    ],
                    "trace_events": [
                        {
                            "event": event.event,
                            "step": event.step,
                            "payload": event.payload,
                        }
                        for event in result.trace_events
                    ],
                },
                indent=2,
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return

    if verbose:
        _render_ask_trace(result)
        click.echo("")
    click.echo(_render_ask_result_text(result))


@cli.command("import-notion")
@click.option("--root-page-url", required=True, help="Notion root page URL")
@click.option("--telegram-user-id", required=True, help="Target Telegram user id")
@click.option(
    "--telegram-chat-id",
    default="import",
    show_default=True,
    help="Chat id placeholder for import-created user rows",
)
@click.option(
    "--notion-token-env",
    default="MCP_BEARER_TOKEN",
    show_default=True,
    help="Environment variable name containing Notion token",
)
@click.option(
    "--default-year",
    default=2026,
    show_default=True,
    type=int,
    help="Year used when source date has no year component",
)
@click.option("--apply", is_flag=True, help="Persist changes to DB (default is dry-run)")
def import_notion_command(
    root_page_url: str,
    telegram_user_id: str,
    telegram_chat_id: str,
    notion_token_env: str,
    default_year: int,
    apply: bool,
) -> None:
    """Import problems from Notion root page into local DB."""
    config = load_config()
    stats = run_import(
        config=config,
        root_page_url=root_page_url,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        notion_token_env=notion_token_env,
        default_year=default_year,
        apply=apply,
        progress=lambda message: click.echo(f"[import] {message}"),
    )
    mode = "APPLY" if apply else "DRY-RUN"
    click.echo(f"Mode: {mode}")
    click.echo(f"Parsed total: {stats.parsed_total}")
    click.echo(f"Parsed valid: {stats.parsed_valid}")
    click.echo(f"Parsed invalid: {stats.parsed_invalid}")
    click.echo(f"Inserted/updated: {stats.inserted_or_updated}")
