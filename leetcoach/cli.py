from __future__ import annotations

import json
import subprocess
import sys
from urllib import error, request

import click

from leetcoach.app import run
from leetcoach.config import load_config
from leetcoach.db.migrate import migrate_database
from leetcoach.env import load_environment
from leetcoach.notion_importer import run_import
from leetcoach.reminder_scheduler import run_scheduler_loop, run_scheduler_once


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
    if target:
        cmd = [sys.executable, "-m", "unittest", "-v", target]
    else:
        start_dir = {
            "all": "tests",
            "unit": "tests/unit",
            "integration": "tests/integration",
        }[suite.lower()]
        cmd = [
            sys.executable,
            "-m",
            "unittest",
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
        from leetcoach.telegram_bot import run_bot
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
    if once:
        stats = run_scheduler_once(config=config, progress=click.echo)
        click.echo(
            (
                f"[scheduler] scanned={stats.scanned} sent={stats.sent} "
                f"skipped={stats.skipped_already_reminded_today} failed={stats.failed}"
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
