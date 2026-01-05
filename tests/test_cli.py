"""Tests for the CLI module."""

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from obsidian.cli import (
    ObsidianCLI,
    format_timestamp,
    format_reward,
    get_project_path,
    PROBLEM_TEMPLATES,
)
from obsidian.config import ObsidianConfig


class TestFormatTimestamp:
    """Tests for format_timestamp function."""

    def test_valid_iso_timestamp(self):
        """Test formatting valid ISO timestamp."""
        result = format_timestamp("2024-01-15T14:30:00")
        assert "2024-01-15" in result
        assert "14:30:00" in result

    def test_invalid_timestamp(self):
        """Test handling invalid timestamp."""
        result = format_timestamp("not-a-date")
        assert result == "not-a-date"

    def test_none_timestamp(self):
        """Test handling None timestamp."""
        result = format_timestamp(None)
        assert result == "N/A"

    def test_empty_timestamp(self):
        """Test handling empty timestamp."""
        result = format_timestamp("")
        assert result == "N/A"


class TestFormatReward:
    """Tests for format_reward function."""

    def test_excellent_reward(self):
        """Test formatting high reward."""
        result = format_reward(0.95)
        assert "0.950" in result
        assert "target met" in result.lower()

    def test_good_reward(self):
        """Test formatting good reward."""
        result = format_reward(0.75)
        assert "0.750" in result
        assert "good" in result.lower()

    def test_moderate_reward(self):
        """Test formatting moderate reward."""
        result = format_reward(0.55)
        assert "0.550" in result
        assert "moderate" in result.lower()

    def test_low_reward(self):
        """Test formatting low reward."""
        result = format_reward(0.3)
        assert "0.300" in result
        assert "low" in result.lower()


class TestGetProjectPath:
    """Tests for get_project_path function."""

    def test_returns_cwd(self):
        """Test that it returns current working directory."""
        result = get_project_path()
        assert result == Path.cwd()


class TestProblemTemplates:
    """Tests for problem templates."""

    def test_algorithm_template_exists(self):
        """Test algorithm template exists."""
        assert "algorithm" in PROBLEM_TEMPLATES

    def test_ml_model_template_exists(self):
        """Test ml_model template exists."""
        assert "ml_model" in PROBLEM_TEMPLATES

    def test_optimization_template_exists(self):
        """Test optimization template exists."""
        assert "optimization" in PROBLEM_TEMPLATES

    def test_custom_template_exists(self):
        """Test custom template exists."""
        assert "custom" in PROBLEM_TEMPLATES

    def test_template_has_placeholders(self):
        """Test templates have name and description placeholders."""
        for name, template in PROBLEM_TEMPLATES.items():
            assert "{name}" in template
            assert "{description}" in template


class TestObsidianCLI:
    """Tests for ObsidianCLI class."""

    def create_project_structure(self, tmpdir):
        """Create a minimal project structure."""
        project_dir = Path(tmpdir)

        # Create obsidian.yaml
        config_content = """
max_attempts: 100
success_threshold: 0.9
state_dir: ".obsidian"

evaluator:
  pytest:
    enabled: true
    weight: 0.6
  coverage:
    enabled: true
    weight: 0.4
  ruff:
    enabled: false
  pyright:
    enabled: false
"""
        (project_dir / "obsidian.yaml").write_text(config_content)

        # Create .obsidian directory
        state_dir = project_dir / ".obsidian"
        state_dir.mkdir(exist_ok=True)

        return project_dir, state_dir

    def test_cli_initialization(self):
        """Test CLI initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, _ = self.create_project_structure(tmpdir)

            cli = ObsidianCLI(project_path=project_dir)

            assert cli.project_path == project_dir
            assert cli.config is not None

    def test_cmd_status(self, capsys):
        """Test status command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_project_structure(tmpdir)

            # Create session state file
            session_state = {
                "attempt_count": 5,
                "best_reward": 0.75,
                "reward_history": [0.3, 0.5, 0.6, 0.7, 0.75],
            }
            (state_dir / "session_state.json").write_text(json.dumps(session_state))

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace()

            result = cli.cmd_status(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "OBSIDIAN STATUS" in captured.out
            assert "CIRCUIT BREAKER" in captured.out

    def test_cmd_reset_circuit(self, capsys):
        """Test reset circuit command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_project_structure(tmpdir)

            # Create circuit breaker state
            cb_state = {"state": "OPEN", "reason": "Test"}
            (state_dir / "circuit_breaker.json").write_text(json.dumps(cb_state))

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(target="circuit")

            result = cli.cmd_reset(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "reset" in captured.out.lower()

    def test_cmd_reset_session(self, capsys):
        """Test reset session command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_project_structure(tmpdir)

            # Create session state
            (state_dir / "session_state.json").write_text("{}")

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(target="session")

            result = cli.cmd_reset(args)

            assert result == 0

            # Session state should be deleted
            assert not (state_dir / "session_state.json").exists()

    def test_cmd_reset_all(self, capsys):
        """Test reset all command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_project_structure(tmpdir)

            # Create various state files
            (state_dir / "session_state.json").write_text("{}")
            (state_dir / "circuit_breaker.json").write_text("{}")

            baselines_dir = state_dir / "baselines"
            baselines_dir.mkdir()
            (baselines_dir / "baseline_1.json").write_text("{}")

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(target="all")

            result = cli.cmd_reset(args)

            assert result == 0

    def test_cmd_history_no_db(self, capsys):
        """Test history command with no database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, _ = self.create_project_structure(tmpdir)

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(limit=10)

            result = cli.cmd_history(args)

            assert result == 1

            captured = capsys.readouterr()
            assert "not found" in captured.out.lower()

    def test_cmd_history_with_episodes(self, capsys):
        """Test history command with episodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_project_structure(tmpdir)

            # Create memory database with episodes
            import sqlite3
            db_path = state_dir / "memory.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE episodes (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    attempt_number INTEGER,
                    timestamp TEXT,
                    reward REAL,
                    action_summary TEXT,
                    metrics TEXT
                )
            """)
            conn.execute("""
                INSERT INTO episodes VALUES
                ('ep1', 'sess1', 1, '2024-01-01T12:00:00', 0.5, 'First attempt', '{"pytest": 0.5}')
            """)
            conn.commit()
            conn.close()

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(limit=10)

            result = cli.cmd_history(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "EPISODE HISTORY" in captured.out
            assert "First attempt" in captured.out

    def test_cmd_stats(self, capsys):
        """Test stats command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_project_structure(tmpdir)

            # Create memory database
            import sqlite3
            db_path = state_dir / "memory.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE episodes (
                    id TEXT, session_id TEXT, attempt_number INTEGER,
                    timestamp TEXT, reward REAL, action_summary TEXT, metrics TEXT
                )
            """)
            for i in range(5):
                conn.execute(
                    "INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"ep{i}", "sess1", i+1, "2024-01-01", 0.5 + i*0.1, "", "{}"),
                )
            conn.commit()
            conn.close()

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace()

            result = cli.cmd_stats(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "STATISTICS" in captured.out
            assert "CONFIGURATION" in captured.out

    def test_cmd_config_validate_defaults(self, capsys):
        """Test config validate with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            # No config file - use defaults

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(config_action="validate")

            result = cli.cmd_config(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "using defaults" in captured.out.lower()

    def test_cmd_config_validate_valid(self, capsys):
        """Test config validate with valid config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, _ = self.create_project_structure(tmpdir)

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(config_action="validate")

            result = cli.cmd_config(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "OK" in captured.out or "VALID" in captured.out

    def test_cmd_config_show(self, capsys):
        """Test config show command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, _ = self.create_project_structure(tmpdir)

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(config_action="show")

            result = cli.cmd_config(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "CURRENT CONFIGURATION" in captured.out
            assert "max_attempts" in captured.out

    def test_cmd_research_init(self, capsys):
        """Test research init command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, _ = self.create_project_structure(tmpdir)

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(
                research_action="init",
                template="algorithm",
                name="Test Problem",
                description="A test problem",
                output=str(project_dir),
            )

            result = cli.cmd_research(args)

            assert result == 0

            # Check problem.yaml was created
            problem_file = project_dir / "problem.yaml"
            assert problem_file.exists()

            content = problem_file.read_text()
            assert "Test Problem" in content

    def test_cmd_research_init_invalid_template(self, capsys):
        """Test research init with invalid template."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, _ = self.create_project_structure(tmpdir)

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(
                research_action="init",
                template="nonexistent",
                name="Test",
                description="Test",
                output=str(project_dir),
            )

            result = cli.cmd_research(args)

            assert result == 1

            captured = capsys.readouterr()
            assert "Unknown template" in captured.out

    def test_cmd_research_status_no_problem(self, capsys):
        """Test research status with no problem.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, _ = self.create_project_structure(tmpdir)

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(research_action="status")

            result = cli.cmd_research(args)

            # Should handle missing problem.yaml gracefully
            assert result in [0, 1]


class TestCLIIntegration:
    """Integration tests for CLI."""

    def test_full_workflow(self):
        """Test a full CLI workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create minimal config
            config = """
max_attempts: 10
success_threshold: 0.9
state_dir: ".obsidian"
evaluator:
  pytest:
    enabled: true
    weight: 1.0
  coverage:
    enabled: false
  ruff:
    enabled: false
  pyright:
    enabled: false
"""
            (project_dir / "obsidian.yaml").write_text(config)
            (project_dir / ".obsidian").mkdir()

            cli = ObsidianCLI(project_path=project_dir)

            # Check status
            args = argparse.Namespace()
            result = cli.cmd_status(args)
            assert result == 0

            # Check stats
            result = cli.cmd_stats(args)
            assert result == 0

            # Reset circuit
            args = argparse.Namespace(target="circuit")
            result = cli.cmd_reset(args)
            assert result == 0


class TestCLIEdgeCases:
    """Edge case tests for CLI."""

    def test_corrupted_session_state(self, capsys):
        """Test handling corrupted session state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            state_dir = project_dir / ".obsidian"
            state_dir.mkdir()

            # Create config
            (project_dir / "obsidian.yaml").write_text("max_attempts: 10")

            # Create corrupted session state
            (state_dir / "session_state.json").write_text("not valid json{")

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace()

            # Should not crash
            result = cli.cmd_status(args)
            assert result == 0

    def test_missing_state_dir(self, capsys):
        """Test handling missing state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create config but no state dir
            (project_dir / "obsidian.yaml").write_text("max_attempts: 10")

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace()

            # Should not crash
            result = cli.cmd_status(args)
            assert result == 0

    def test_empty_history(self, capsys):
        """Test history command with empty database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            state_dir = project_dir / ".obsidian"
            state_dir.mkdir()

            (project_dir / "obsidian.yaml").write_text("max_attempts: 10")

            # Create empty database
            import sqlite3
            db_path = state_dir / "memory.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE episodes (
                    id TEXT, session_id TEXT, attempt_number INTEGER,
                    timestamp TEXT, reward REAL, action_summary TEXT, metrics TEXT
                )
            """)
            conn.commit()
            conn.close()

            cli = ObsidianCLI(project_path=project_dir)
            args = argparse.Namespace(limit=10)

            result = cli.cmd_history(args)

            assert result == 0

            captured = capsys.readouterr()
            assert "No episodes" in captured.out
