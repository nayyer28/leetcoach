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
def test_command() -> None:
    """Run integration tests."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
            "-v",
        ],
        check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    cli()
