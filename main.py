from __future__ import annotations

import click
import subprocess
import sys

from leetcoach.app import run
from leetcoach.config import load_config
from leetcoach.db.migrate import migrate_database


@click.group(invoke_without_command=True, help="Leetcoach CLI")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """CLI entrypoint."""
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


if __name__ == "__main__":
    cli()
