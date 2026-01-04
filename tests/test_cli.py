"""Tests for CLI commands."""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from obsidian.cli import (
    ObsidianCLI,
    create_parser,
    main,
    format_reward,
    format_timestamp,
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory with config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)

        # Create config file
        config_content = """
max_attempts: 10
success_threshold: 0.90

evaluator:
  weights:
    pytest: 0.6
    coverage: 0.4
  pytest:
    enabled: true
  coverage:
    enabled: true
"""
        (project_path / "obsidian.yaml").write_text(config_content)

        # Create state directory
        state_dir = project_path / ".obsidian"
        state_dir.mkdir()

        # Create circuit breaker state
        cb_state = {
            "state": "CLOSED",
            "consecutive_no_progress": 0,
            "consecutive_same_error": 0,
            "total_opens": 0,
            "current_loop": 5,
        }
        (state_dir / "circuit_breaker.json").write_text(json.dumps(cb_state))

        yield project_path


class TestFormatHelpers:
    """Tests for format helper functions."""

    def test_format_reward_high(self):
        """Should indicate target met for high rewards."""
        result = format_reward(0.95)
        assert "target met" in result
        assert "0.95" in result

    def test_format_reward_good(self):
        """Should indicate good for medium-high rewards."""
        result = format_reward(0.75)
        assert "good" in result

    def test_format_reward_moderate(self):
        """Should indicate moderate for medium rewards."""
        result = format_reward(0.55)
        assert "moderate" in result

    def test_format_reward_low(self):
        """Should indicate low for low rewards."""
        result = format_reward(0.3)
        assert "low" in result

    def test_format_timestamp_valid(self):
        """Should format valid ISO timestamp."""
        result = format_timestamp("2026-01-04T10:30:00")
        assert "2026-01-04" in result
        assert "10:30:00" in result

    def test_format_timestamp_invalid(self):
        """Should return original for invalid timestamp."""
        result = format_timestamp("not-a-timestamp")
        assert result == "not-a-timestamp"

    def test_format_timestamp_none(self):
        """Should return N/A for None."""
        result = format_timestamp(None)
        assert result == "N/A"


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_creates_parser(self):
        """Should create a valid parser."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "obsidian"

    def test_has_status_command(self):
        """Should have status command."""
        parser = create_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_has_reset_command(self):
        """Should have reset command with target."""
        parser = create_parser()
        args = parser.parse_args(["reset", "circuit"])
        assert args.command == "reset"
        assert args.target == "circuit"

    def test_has_history_command(self):
        """Should have history command with limit option."""
        parser = create_parser()
        args = parser.parse_args(["history", "-n", "5"])
        assert args.command == "history"
        assert args.limit == 5

    def test_has_stats_command(self):
        """Should have stats command."""
        parser = create_parser()
        args = parser.parse_args(["stats"])
        assert args.command == "stats"

    def test_has_config_validate_command(self):
        """Should have config validate subcommand."""
        parser = create_parser()
        args = parser.parse_args(["config", "validate"])
        assert args.command == "config"
        assert args.config_action == "validate"

    def test_has_config_show_command(self):
        """Should have config show subcommand."""
        parser = create_parser()
        args = parser.parse_args(["config", "show"])
        assert args.command == "config"
        assert args.config_action == "show"

    def test_has_test_evaluator_command(self):
        """Should have test-evaluator command."""
        parser = create_parser()
        args = parser.parse_args(["test-evaluator", "pytest"])
        assert args.command == "test-evaluator"
        assert args.evaluator == "pytest"


class TestObsidianCLI:
    """Tests for ObsidianCLI class."""

    def test_initialization(self, temp_project):
        """Should initialize with project path."""
        cli = ObsidianCLI(temp_project)
        assert cli.project_path == temp_project
        assert cli.config is not None

    def test_cmd_status(self, temp_project, capsys):
        """Should show status without errors."""
        cli = ObsidianCLI(temp_project)
        parser = create_parser()
        args = parser.parse_args(["status"])

        result = cli.cmd_status(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "OBSIDIAN STATUS" in captured.out
        assert "CIRCUIT BREAKER" in captured.out

    def test_cmd_stats(self, temp_project, capsys):
        """Should show stats without errors."""
        cli = ObsidianCLI(temp_project)
        parser = create_parser()
        args = parser.parse_args(["stats"])

        result = cli.cmd_stats(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "OBSIDIAN STATISTICS" in captured.out
        assert "CONFIGURATION" in captured.out

    def test_cmd_config_validate(self, temp_project, capsys):
        """Should validate config without errors."""
        cli = ObsidianCLI(temp_project)
        parser = create_parser()
        args = parser.parse_args(["config", "validate"])

        result = cli.cmd_config(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "CONFIGURATION VALIDATION" in captured.out

    def test_cmd_config_show(self, temp_project, capsys):
        """Should show config without errors."""
        cli = ObsidianCLI(temp_project)
        parser = create_parser()
        args = parser.parse_args(["config", "show"])

        result = cli.cmd_config(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "CURRENT CONFIGURATION" in captured.out
        assert "max_attempts" in captured.out

    def test_cmd_history_no_db(self, temp_project, capsys):
        """Should handle missing database gracefully."""
        cli = ObsidianCLI(temp_project)
        parser = create_parser()
        args = parser.parse_args(["history"])

        result = cli.cmd_history(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "No history available" in captured.out

    def test_cmd_reset_circuit(self, temp_project, capsys):
        """Should reset circuit breaker."""
        cli = ObsidianCLI(temp_project)
        parser = create_parser()
        args = parser.parse_args(["reset", "circuit"])

        result = cli.cmd_reset(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Circuit breaker reset" in captured.out


class TestMain:
    """Tests for main entry point."""

    def test_no_command_shows_help(self, capsys):
        """Should show help when no command given."""
        with patch("obsidian.cli.get_project_path") as mock_path:
            mock_path.return_value = Path("/tmp")
            result = main([])

        assert result == 0

    def test_unknown_command(self, capsys):
        """Should exit with error for unknown command."""
        with pytest.raises(SystemExit) as exc_info:
            main(["unknown"])
        assert exc_info.value.code == 2  # argparse exits with 2 on error

    def test_version(self, capsys):
        """Should show version."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.1.0" in captured.out
