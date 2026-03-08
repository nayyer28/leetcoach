from __future__ import annotations

import click
import subprocess
import sys

from leetcoach.app import run
from leetcoach.config import load_config
from leetcoach.db.migrate import migrate_database
from leetcoach.env import load_environment
from leetcoach.notion_importer import run_import


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
      python main.py test
      python main.py test unit
      python main.py test integration
      python main.py test unit tests.unit.dao.test_problem_reviews_dao
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
    )
    mode = "APPLY" if apply else "DRY-RUN"
    click.echo(f"Mode: {mode}")
    click.echo(f"Parsed total: {stats.parsed_total}")
    click.echo(f"Parsed valid: {stats.parsed_valid}")
    click.echo(f"Parsed invalid: {stats.parsed_invalid}")
    click.echo(f"Inserted/updated: {stats.inserted_or_updated}")


if __name__ == "__main__":
    cli()
