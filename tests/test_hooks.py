"""Integration tests for hook scripts."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from obsidian.config import ObsidianConfig
from obsidian.memory import MemoryStore, EpisodicMemory
from obsidian.strategy import CircuitBreaker, CircuitState


class TestSessionStartHook:
    """Tests for session_start.py hook."""

    def create_test_environment(self, tmpdir):
        """Create test environment for hooks."""
        project_dir = Path(tmpdir)
        state_dir = project_dir / ".obsidian"
        state_dir.mkdir(exist_ok=True)

        # Create minimal config
        config_content = """
max_attempts: 100
success_threshold: 0.9
state_dir: ".obsidian"

icrl:
  enabled: true
  top_k: 3
  max_context_tokens: 5000
  compression_threshold: 10
  include_failures: true

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

logging:
  enabled: false
"""
        (project_dir / "obsidian.yaml").write_text(config_content)

        return project_dir, state_dir

    def test_no_history(self):
        """Test hook with no history (first run)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_test_environment(tmpdir)

            hook_script = Path(__file__).parent.parent / "scripts" / "session_start.py"

            input_data = {
                "session_id": "test_session",
                "cwd": str(project_dir),
            }

            result = subprocess.run(
                ["python", str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0

            output = json.loads(result.stdout)
            assert output["continue"] is True
            # No system message when no history
            assert "systemMessage" not in output or output.get("systemMessage") == ""

    def test_with_history(self):
        """Test hook with existing history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_test_environment(tmpdir)

            # Create memory database with episodes
            db_path = state_dir / "memory.db"
            store = MemoryStore(db_path)
            memory = EpisodicMemory(store)

            # Add episodes
            for i in range(3):
                memory.add_episode(
                    session_id="test_session",
                    attempt_number=i + 1,
                    reward=0.5 + i * 0.1,
                    metrics={"pytest": 0.6},
                    action_summary=f"Attempt {i + 1}",
                )
                memory.update_session_state("test_session", reward=0.5 + i * 0.1)

            store.close()

            hook_script = Path(__file__).parent.parent / "scripts" / "session_start.py"

            input_data = {
                "session_id": "test_session",
                "cwd": str(project_dir),
            }

            result = subprocess.run(
                ["python", str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0

            output = json.loads(result.stdout)
            assert output["continue"] is True
            assert "systemMessage" in output
            # Context should include attempt history
            assert "OBSIDIAN LEARNING CONTEXT" in output["systemMessage"]

    def test_icrl_disabled(self):
        """Test hook when ICRL is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_test_environment(tmpdir)

            # Modify config to disable ICRL
            config_content = """
max_attempts: 10
icrl:
  enabled: false
"""
            (project_dir / "obsidian.yaml").write_text(config_content)

            hook_script = Path(__file__).parent.parent / "scripts" / "session_start.py"

            input_data = {
                "session_id": "test_session",
                "cwd": str(project_dir),
            }

            result = subprocess.run(
                ["python", str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0

            output = json.loads(result.stdout)
            assert output["continue"] is True


class TestStopHook:
    """Tests for stop_hook.py hook."""

    def create_test_environment(self, tmpdir):
        """Create test environment for stop hook."""
        project_dir = Path(tmpdir)
        state_dir = project_dir / ".obsidian"
        state_dir.mkdir(exist_ok=True)

        # Create minimal config
        config_content = """
max_attempts: 100
success_threshold: 0.9
state_dir: ".obsidian"

evaluator:
  pytest:
    enabled: true
    weight: 1.0
    timeout: 5
  coverage:
    enabled: false
  ruff:
    enabled: false
  pyright:
    enabled: false

circuit_breaker:
  enabled: true
  no_progress_threshold: 3

logging:
  enabled: false

response_analysis:
  enabled: false
"""
        (project_dir / "obsidian.yaml").write_text(config_content)

        # Create minimal test file
        (project_dir / "test_sample.py").write_text("""
def test_passing():
    assert True
""")

        return project_dir, state_dir

    def test_first_attempt(self):
        """Test stop hook on first attempt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_test_environment(tmpdir)

            hook_script = Path(__file__).parent.parent / "scripts" / "stop_hook.py"

            input_data = {
                "session_id": "test_session",
                "cwd": str(project_dir),
                "transcript": "I fixed the tests",
            }

            result = subprocess.run(
                ["python", str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Exit code 2 = block (continue learning)
            # Exit code 0 = allow stop (target met)
            assert result.returncode in [0, 2]

            if result.stdout:
                output = json.loads(result.stdout)
                # Should have either decision or continue field
                assert "decision" in output or "continue" in output

    def test_circuit_breaker_triggers(self):
        """Test that circuit breaker can trigger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir, state_dir = self.create_test_environment(tmpdir)

            # Set circuit breaker to OPEN
            cb = CircuitBreaker(state_dir)
            cb.record_result(1, has_progress=False, has_errors=False)
            cb.record_result(2, has_progress=False, has_errors=False)
            cb.record_result(3, has_progress=False, has_errors=False)

            assert cb.get_state() == CircuitState.OPEN

            hook_script = Path(__file__).parent.parent / "scripts" / "stop_hook.py"

            input_data = {
                "session_id": "test_session",
                "cwd": str(project_dir),
            }

            result = subprocess.run(
                ["python", str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should exit with 0 (allow stop) due to circuit breaker
            assert result.returncode == 0

            output = json.loads(result.stdout)
            assert output["continue"] is False
            assert "Circuit breaker" in output.get("stopReason", "")


class TestUnifiedStopHook:
    """Tests for unified_stop_hook.py."""

    def test_routes_to_standard_mode(self):
        """Test routing to standard mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            state_dir = project_dir / ".obsidian"
            state_dir.mkdir()

            # Create config without problem.yaml (standard mode)
            config = """
max_attempts: 10
evaluator:
  pytest:
    enabled: true
    weight: 1.0
"""
            (project_dir / "obsidian.yaml").write_text(config)
            (project_dir / "test_sample.py").write_text("def test_pass(): assert True")

            hook_script = Path(__file__).parent.parent / "scripts" / "unified_stop_hook.py"

            input_data = {
                "session_id": "test",
                "cwd": str(project_dir),
            }

            result = subprocess.run(
                ["python", str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should execute without error
            assert result.returncode in [0, 2]


class TestResearchHook:
    """Tests for research_hook.py."""

    def test_requires_problem_yaml(self):
        """Test that research hook requires problem.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            state_dir = project_dir / ".obsidian"
            state_dir.mkdir()

            hook_script = Path(__file__).parent.parent / "scripts" / "research_hook.py"

            input_data = {
                "session_id": "test",
                "cwd": str(project_dir),
            }

            result = subprocess.run(
                ["python", str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Should handle missing problem.yaml gracefully
            assert result.returncode in [0, 1]
