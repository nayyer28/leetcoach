from __future__ import annotations

import subprocess
import sys
import unittest
from types import SimpleNamespace
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

    @patch("leetcoach.cli.ask_question")
    @patch("leetcoach.cli.GeminiProvider")
    @patch("leetcoach.cli.load_config")
    def test_admin_ask_runs_service_and_prints_answer(
        self, mock_load_config, mock_provider_cls, mock_ask_question
    ) -> None:
        mock_load_config.return_value = SimpleNamespace(
            db_path="/tmp/leetcoach.db",
            gemini_api_key="test-key",
        )
        mock_provider_cls.return_value = object()
        mock_ask_question.return_value = SimpleNamespace(
            answer="February was your strongest month.",
            model="gemini-2.5-flash-lite",
            request_id="req-123",
            tool_executions=[],
            trace_events=[],
        )
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["admin", "ask", "--user", "u-1", "which", "month", "was", "best?"],
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("February was your strongest month.", result.output)
        mock_provider_cls.assert_called_once()
        mock_ask_question.assert_called_once_with(
            db_path="/tmp/leetcoach.db",
            telegram_user_id="u-1",
            question="which month was best?",
            provider=mock_provider_cls.return_value,
        )

    @patch("leetcoach.cli.ask_question")
    @patch("leetcoach.cli.GeminiProvider")
    @patch("leetcoach.cli.load_config")
    def test_admin_ask_verbose_prints_trace(
        self, mock_load_config, mock_provider_cls, mock_ask_question
    ) -> None:
        mock_load_config.return_value = SimpleNamespace(
            db_path="/tmp/leetcoach.db",
            gemini_api_key="test-key",
        )
        mock_provider_cls.return_value = object()
        mock_ask_question.return_value = SimpleNamespace(
            answer="You can ask about problems and reviews.",
            model="gemini-2.5-flash-lite",
            request_id="req-123",
            tool_executions=[],
            trace_events=[
                SimpleNamespace(
                    event="ask.start",
                    step=None,
                    payload={"question": "what can you do?", "max_steps": 5},
                )
            ],
        )
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["admin", "ask", "--user", "u-1", "--verbose", "what", "can", "you", "do?"],
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("request_id: req-123", result.output)
        self.assertIn("[step -] ask.start", result.output)
        self.assertIn("You can ask about problems and reviews.", result.output)

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
