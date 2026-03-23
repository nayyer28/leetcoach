from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from leetcoach.cli import cli


class CliUnitTest(unittest.TestCase):
    @patch("leetcoach.cli.subprocess.run")
    def test_test_command_runs_unit_discovery(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        runner = CliRunner()

        result = runner.invoke(cli, ["test", "unit"])

        self.assertEqual(result.exit_code, 0)
        mock_run.assert_called_once_with(
            [
                sys.executable,
                "-W",
                "ignore::ResourceWarning",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests/unit",
                "-p",
                "test_*.py",
                "-v",
            ],
            check=False,
        )

    @patch("leetcoach.cli.subprocess.run")
    def test_test_command_runs_target_directly(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["test", "unit", "tests.unit.dao.test_problem_reviews_dao"],
        )

        self.assertEqual(result.exit_code, 0)
        mock_run.assert_called_once_with(
            [
                sys.executable,
                "-W",
                "ignore::ResourceWarning",
                "-m",
                "unittest",
                "-v",
                "tests.unit.dao.test_problem_reviews_dao",
            ],
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
