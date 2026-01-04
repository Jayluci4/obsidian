"""Tests for configuration loader."""

import pytest
import tempfile
from pathlib import Path

import yaml

from obsidian.config import (
    ObsidianConfig,
    EvaluatorConfig,
    ICRLConfig,
    CircuitBreakerConfig,
    LoggingConfig,
    load_config,
    find_config_file,
    get_state_dir,
)


class TestEvaluatorConfig:
    """Tests for EvaluatorConfig."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = EvaluatorConfig()
        assert config.enabled is True
        assert config.timeout == 120
        assert config.weight == 0.0

    def test_custom_values(self):
        """Should accept custom values."""
        config = EvaluatorConfig(
            enabled=False,
            timeout=60,
            weight=0.5,
        )
        assert config.enabled is False
        assert config.timeout == 60
        assert config.weight == 0.5


class TestICRLConfig:
    """Tests for ICRLConfig."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = ICRLConfig()
        assert config.enabled is True
        assert config.top_k == 5
        assert config.max_context_tokens == 10000
        assert config.filter_strategy == "quality_diversity"

    def test_ratios_sum(self):
        """Ratios should sum to 1.0 by default."""
        config = ICRLConfig()
        total = config.top_k_ratio + config.failure_ratio + config.diversity_ratio
        assert abs(total - 1.0) < 0.001


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = CircuitBreakerConfig()
        assert config.enabled is True
        assert config.no_progress_threshold == 3
        assert config.same_error_threshold == 5


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = LoggingConfig()
        assert config.enabled is True
        assert config.level == "INFO"
        assert config.max_size_mb == 10


class TestObsidianConfig:
    """Tests for main ObsidianConfig."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = ObsidianConfig()
        assert config.max_attempts == 10
        assert config.success_threshold == 0.90
        assert config.state_dir == ".obsidian"

    def test_from_dict_empty(self):
        """Should create from empty dict."""
        config = ObsidianConfig.from_dict({})
        assert config.max_attempts == 10

    def test_from_dict_partial(self):
        """Should create from partial dict."""
        data = {
            "max_attempts": 20,
            "success_threshold": 0.85,
        }
        config = ObsidianConfig.from_dict(data)
        assert config.max_attempts == 20
        assert config.success_threshold == 0.85
        # Defaults for unspecified
        assert config.state_dir == ".obsidian"

    def test_from_dict_evaluators(self):
        """Should parse evaluator config."""
        data = {
            "evaluator": {
                "weights": {
                    "pytest": 0.5,
                    "coverage": 0.5,
                },
                "pytest": {
                    "enabled": True,
                    "timeout": 60,
                },
                "coverage": {
                    "enabled": True,
                    "source": "src",
                    "threshold": 80,
                },
            }
        }
        config = ObsidianConfig.from_dict(data)
        assert config.pytest.weight == 0.5
        assert config.pytest.timeout == 60
        assert config.coverage.threshold == 80

    def test_from_dict_icrl(self):
        """Should parse ICRL config."""
        data = {
            "icrl": {
                "enabled": True,
                "top_k": 10,
                "max_context_tokens": 5000,
            }
        }
        config = ObsidianConfig.from_dict(data)
        assert config.icrl.top_k == 10
        assert config.icrl.max_context_tokens == 5000

    def test_from_dict_circuit_breaker(self):
        """Should parse circuit breaker config."""
        data = {
            "circuit_breaker": {
                "no_progress_threshold": 5,
                "same_error_threshold": 10,
            }
        }
        config = ObsidianConfig.from_dict(data)
        assert config.circuit_breaker.no_progress_threshold == 5
        assert config.circuit_breaker.same_error_threshold == 10

    def test_from_dict_logging(self):
        """Should parse logging config."""
        data = {
            "logging": {
                "enabled": True,
                "level": "DEBUG",
                "json_format": True,
            }
        }
        config = ObsidianConfig.from_dict(data)
        assert config.logging.level == "DEBUG"
        assert config.logging.json_format is True

    def test_from_dict_error_handling(self):
        """Should parse error handling config."""
        data = {
            "error_handling": {
                "max_retries": 5,
                "retry_delay_seconds": 2.0,
                "continue_on_evaluator_failure": False,
            }
        }
        config = ObsidianConfig.from_dict(data)
        assert config.error_handling.max_retries == 5
        assert config.error_handling.continue_on_evaluator_failure is False


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_missing_config(self):
        """Should return defaults if no config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_config(tmpdir)
            assert config.max_attempts == 10

    def test_load_existing_config(self):
        """Should load from config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "obsidian.yaml"
            config_path.write_text(yaml.dump({
                "max_attempts": 25,
                "success_threshold": 0.95,
            }))

            config = load_config(tmpdir)
            assert config.max_attempts == 25
            assert config.success_threshold == 0.95


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_find_in_current_dir(self):
        """Should find config in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "obsidian.yaml"
            config_path.touch()

            found = find_config_file(tmpdir)
            assert found == config_path

    def test_find_in_parent_dir(self):
        """Should find config in parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            child = parent / "subdir"
            child.mkdir()

            config_path = parent / "obsidian.yaml"
            config_path.touch()

            found = find_config_file(child)
            assert found == config_path

    def test_not_found(self):
        """Should return None if not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            found = find_config_file(tmpdir)
            assert found is None


class TestGetStateDir:
    """Tests for get_state_dir function."""

    def test_creates_directory(self):
        """Should create state directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ObsidianConfig(state_dir=".test_obsidian")
            state_dir = get_state_dir(tmpdir, config)

            assert state_dir.exists()
            assert state_dir.is_dir()
            assert state_dir.name == ".test_obsidian"

    def test_uses_existing_directory(self):
        """Should use existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / ".obsidian"
            existing.mkdir()
            marker = existing / "marker.txt"
            marker.write_text("exists")

            config = ObsidianConfig()
            state_dir = get_state_dir(tmpdir, config)

            assert (state_dir / "marker.txt").exists()
