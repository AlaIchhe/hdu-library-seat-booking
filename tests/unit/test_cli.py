"""Tests for hdu_library_booking.cli — CLI argument parsing and execution flow."""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from hdu_library_booking.cli import CLI, main
from hdu_library_booking.cli.helpers import ProgressSpinner, format_countdown, setup_logging


# ---------------------------------------------------------------------------
# CLI Argument Parsing Tests
# ---------------------------------------------------------------------------
class TestCLIBuildParser:
    def test_parser_accepts_cookie(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "uid=xxx;auth=yyy", "--plan", "1:1558:296:13:9"])
        assert args.cookie == "uid=xxx;auth=yyy"

    def test_parser_accepts_cookie_file(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(
            ["--cookie-file", "/tmp/cookies.json", "--plan", "1:1558:296:13:9"]
        )
        assert args.cookie_file == "/tmp/cookies.json"

    def test_parser_accepts_multiple_plans(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(
            ["--cookie", "x", "--plan", "1:1558:296:13:9", "--plan", "2:1000:050:8:4"]
        )
        assert len(args.plans) == 2
        assert args.plans[0] == "1:1558:296:13:9"
        assert args.plans[1] == "2:1000:050:8:4"

    def test_parser_accepts_plan_file(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "x", "--plan-file", "plans.yaml"])
        assert args.plan_file == "plans.yaml"

    def test_parser_strategy_choices(self):
        cli = CLI()
        parser = cli._build_parser()
        for choice in ["fixed", "random", "weekday"]:
            args = parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1", "--strategy", choice])
            assert args.strategy == choice

    def test_parser_default_strategy_is_fixed(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1"])
        assert args.strategy == "fixed"

    def test_parser_invalid_strategy_rejected(self):
        cli = CLI()
        parser = cli._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1", "--strategy", "invalid"])

    def test_parser_accepts_at(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1", "--at", "19:59:30"])
        assert args.execute_at == "19:59:30"

    def test_parser_default_max_trials(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1"])
        assert args.max_trials == 5

    def test_parser_custom_max_trials(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1", "--max-trials", "10"])
        assert args.max_trials == 10

    def test_parser_dry_run_flag(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1", "--dry-run"])
        assert args.dry_run is True

    def test_parser_report_flag(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--report"])
        assert args.report is True

    def test_parser_report_json(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--report-json", "/tmp/report.json"])
        assert args.report_json == "/tmp/report.json"

    def test_parser_wechat_webhook(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(
            ["--cookie", "x", "--plan", "1:1:1:1:1", "--wechat-webhook", "http://hook"]
        )
        assert args.wechat_webhook == "http://hook"

    def test_parser_default_log_file(self):
        cli = CLI()
        parser = cli._build_parser()
        args = parser.parse_args(["--cookie", "x", "--plan", "1:1:1:1:1"])
        assert args.log_file == "booking.log"


# ---------------------------------------------------------------------------
# CLI Strategy Building Tests
# ---------------------------------------------------------------------------
class TestCLIBuildStrategy:
    def test_build_fixed_strategy(self):
        cli = CLI()
        args = MagicMock(strategy="fixed")
        strategy = cli._build_strategy(args)
        assert strategy.__class__.__name__ == "FixedSeatStrategy"

    def test_build_random_strategy(self):
        cli = CLI()
        args = MagicMock(strategy="random")
        strategy = cli._build_strategy(args)
        assert strategy.__class__.__name__ == "RandomRangeStrategy"

    def test_build_weekday_strategy(self):
        cli = CLI()
        args = MagicMock(strategy="weekday")
        strategy = cli._build_strategy(args)
        assert strategy.__class__.__name__ == "WeekdayRotationStrategy"


# ---------------------------------------------------------------------------
# CLI Plan Resolution Tests
# ---------------------------------------------------------------------------
class TestCLIResolvePlans:
    def test_resolve_from_plan_codes(self):
        cli = CLI()
        args = MagicMock(plans=["1:1558:296:13:9", "2:1000:050:8:4"], plan_file=None)
        plans = cli._resolve_plans(args)
        assert len(plans) == 2
        assert plans[0].to_plan_code() == "1:1558:296:13:9"

    def test_resolve_from_plan_file(self, tmp_path):
        yaml_content = """
- room_type: 1
  floor_id: 1558
  seat_num: "296"
  start_hour: 13
  duration_hours: 9
  booker_name: test
  book_days: 1
  status: enabled
"""
        plan_file = tmp_path / "plans.yaml"
        plan_file.write_text(yaml_content)

        cli = CLI()
        args = MagicMock(plans=None, plan_file=str(plan_file))
        plans = cli._resolve_plans(args)
        assert len(plans) == 1
        assert plans[0].seat_num == "296"

    def test_resolve_empty_returns_empty(self):
        cli = CLI()
        args = MagicMock(plans=None, plan_file=None)
        plans = cli._resolve_plans(args)
        assert plans == []


# ---------------------------------------------------------------------------
# CLI Report Mode Tests
# ---------------------------------------------------------------------------
class TestCLIRReport:
    def test_report_mode_returns_zero(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["hdu-book", "--report"])
        cli = CLI()
        with patch("hdu_library_booking.cli.error_tracker") as mock_tracker:
            mock_tracker.summary.return_value = '{"errors": 0}'
            result = cli.run()
        assert result == 0

    def test_report_json_mode(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["hdu-book", "--report-json", "/tmp/test_report.json"])
        cli = CLI()
        with patch("hdu_library_booking.cli.error_tracker") as mock_tracker:
            mock_tracker.export_json.return_value = None
            mock_tracker.total.return_value = 42
            result = cli.run()
        assert result == 0
        mock_tracker.export_json.assert_called_once_with("/tmp/test_report.json")


# ---------------------------------------------------------------------------
# Helpers Tests
# ---------------------------------------------------------------------------
class TestFormatCountdown:
    def test_zero_seconds(self):
        assert format_countdown(0) == "00:00"

    def test_seconds_only(self):
        assert format_countdown(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert format_countdown(125) == "02:05"

    def test_hours_minutes_seconds(self):
        assert format_countdown(3661) == "01:01:01"

    def test_large_hours(self):
        assert format_countdown(7200) == "02:00:00"


class TestSetupLogging:
    def test_returns_logger(self, monkeypatch):
        """setup_logging delegates to configure_logging."""
        mock_configure = MagicMock()
        monkeypatch.setattr(
            "hdu_library_booking.observability.configure_logging",
            mock_configure,
        )

        setup_logging(level=20, log_file="test.log")
        mock_configure.assert_called_once_with(level="INFO", log_file="test.log", json_format=False)


class TestProgressSpinner:
    def test_start_stop(self):
        spinner = ProgressSpinner(message="Testing")
        spinner.start()
        time.sleep(0.15)
        spinner.stop(done_message="Done!")
        assert spinner._running is False

    def test_default_message(self):
        spinner = ProgressSpinner()
        assert spinner.message == "处理中"


# ---------------------------------------------------------------------------
# Import time / sys.path guard
# ---------------------------------------------------------------------------
class TestCLIMainGuard:
    def test_main_function_exists(self):
        assert callable(main)

    def test_cli_class_instantiation(self):
        cli = CLI()
        assert cli.exit_code == 0
