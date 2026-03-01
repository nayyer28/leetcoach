import argparse

from leetcoach.app import run
from leetcoach.config import load_config
from leetcoach.db.migrate import migrate_database


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Leetcoach CLI")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run", "migrate"),
        help="run app skeleton or apply database migrations",
    )
    args = parser.parse_args()

    if args.command == "migrate":
        config = load_config()
        raise SystemExit(migrate_database(config.db_path))

    raise SystemExit(run())
