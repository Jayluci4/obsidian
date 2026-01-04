"""Configuration loader for Obsidian plugin."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EvaluatorConfig:
    """Configuration for a single evaluator."""

    enabled: bool = True
    timeout: int = 120
    weight: float = 0.0
    args: list[str] = field(default_factory=list)
    source: str = "src"
    threshold: float = 0.0
    max_errors: int = 100


@dataclass
class ICRLConfig:
    """Configuration for In-Context Reinforcement Learning."""

    enabled: bool = True
    top_k: int = 5
    include_failures: bool = True
    max_context_tokens: int = 10000
    compression_threshold: int = 20
    filter_strategy: str = "quality_diversity"
    top_k_ratio: float = 0.6
    failure_ratio: float = 0.2
    diversity_ratio: float = 0.2


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    enabled: bool = True
    no_progress_threshold: int = 3
    same_error_threshold: int = 5
    reward_decline_threshold: float = 0.1
    half_open_threshold: int = 2


@dataclass
class StrategyConfig:
    """Configuration for strategy controller."""

    improve_threshold: float = 0.05
    decline_threshold: float = -0.05
    stuck_threshold: float = 0.02
    min_variance_window: int = 3
    max_consecutive_mode: int = 5


@dataclass
class PerformanceConfig:
    """Configuration for performance settings."""

    parallel_evaluators: bool = True
    max_workers: int = 4
    cache_enabled: bool = False
    cache_by_file_hash: bool = False


@dataclass
class DatabaseConfig:
    """Configuration for database settings."""

    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    cache_size: int = -64000


@dataclass
class FeedbackConfig:
    """Configuration for feedback formatting."""

    include_failed_tests: bool = True
    max_failures_shown: int = 5
    include_coverage_delta: bool = True
    verbose: bool = False
    show_circuit_status: bool = True
    show_strategy_mode: bool = True
    compress_old_feedback: bool = False


@dataclass
class LoggingConfig:
    """Configuration for logging."""

    enabled: bool = True
    level: str = "INFO"
    file: str = "obsidian.log"
    max_size_mb: int = 10
    backup_count: int = 3
    json_format: bool = False
    log_evaluations: bool = True
    log_state_changes: bool = True
    log_circuit_breaker: bool = True
    log_strategy_changes: bool = True


@dataclass
class ResponseAnalysisConfig:
    """Configuration for response analysis."""

    enabled: bool = True
    completion_threshold: int = 40
    stuck_error_count: int = 5
    detect_test_only: bool = True
    detect_no_work: bool = True
    detect_stuck: bool = True


@dataclass
class ErrorHandlingConfig:
    """Configuration for error handling."""

    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    global_timeout_seconds: int = 300
    continue_on_evaluator_failure: bool = True
    fallback_reward: float = 0.0


@dataclass
class HookConfig:
    """Configuration for a single hook."""

    enabled: bool = True
    timeout: int = 60


@dataclass
class HooksConfig:
    """Configuration for all hooks."""

    session_start: HookConfig = field(default_factory=lambda: HookConfig(timeout=10))
    stop: HookConfig = field(default_factory=lambda: HookConfig(timeout=300))
    post_tool_use: HookConfig = field(default_factory=lambda: HookConfig(enabled=False))


@dataclass
class AdvancedConfig:
    """Advanced configuration options."""

    prune_old_episodes: bool = True
    prune_threshold: int = 100
    semantic_confidence_threshold: float = 0.5
    semantic_decay_rate: float = 0.95
    track_strategy_effectiveness: bool = True
    debug: bool = False
    dry_run: bool = False


@dataclass
class ObsidianConfig:
    """Main configuration for Obsidian plugin."""

    max_attempts: int = 10
    success_threshold: float = 0.90
    state_dir: str = ".obsidian"

    # Evaluators
    pytest: EvaluatorConfig = field(default_factory=lambda: EvaluatorConfig(weight=0.6))
    coverage: EvaluatorConfig = field(default_factory=lambda: EvaluatorConfig(weight=0.4))
    ruff: EvaluatorConfig = field(default_factory=lambda: EvaluatorConfig(enabled=False))
    pyright: EvaluatorConfig = field(default_factory=lambda: EvaluatorConfig(enabled=False))

    # Components
    icrl: ICRLConfig = field(default_factory=ICRLConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    response_analysis: ResponseAnalysisConfig = field(default_factory=ResponseAnalysisConfig)
    error_handling: ErrorHandlingConfig = field(default_factory=ErrorHandlingConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObsidianConfig":
        """Create config from dictionary."""
        evaluator = data.get("evaluator", {})
        weights = evaluator.get("weights", {})

        pytest_cfg = evaluator.get("pytest", {})
        coverage_cfg = evaluator.get("coverage", {})
        ruff_cfg = evaluator.get("ruff", {})
        pyright_cfg = evaluator.get("pyright", {})

        icrl_data = data.get("icrl", {})
        circuit_breaker_data = data.get("circuit_breaker", {})
        strategy_data = data.get("strategy", {})
        performance_data = data.get("performance", {})
        database_data = data.get("database", {})
        feedback_data = data.get("feedback", {})
        logging_data = data.get("logging", {})
        response_analysis_data = data.get("response_analysis", {})
        error_handling_data = data.get("error_handling", {})
        hooks_data = data.get("hooks", {})
        advanced_data = data.get("advanced", {})

        return cls(
            max_attempts=data.get("max_attempts", 10),
            success_threshold=data.get("success_threshold", 0.90),
            state_dir=data.get("state_dir", ".obsidian"),
            pytest=EvaluatorConfig(
                enabled=pytest_cfg.get("enabled", True),
                timeout=pytest_cfg.get("timeout", 120),
                weight=pytest_cfg.get("weight", weights.get("pytest", 0.6)),
                args=pytest_cfg.get("args", ["--tb=short", "-q"]),
            ),
            coverage=EvaluatorConfig(
                enabled=coverage_cfg.get("enabled", True),
                timeout=coverage_cfg.get("timeout", 180),
                weight=coverage_cfg.get("weight", weights.get("coverage", 0.4)),
                source=coverage_cfg.get("source", "src"),
                threshold=coverage_cfg.get("threshold", 70),
            ),
            ruff=EvaluatorConfig(
                enabled=ruff_cfg.get("enabled", False),
                timeout=ruff_cfg.get("timeout", 30),
                weight=ruff_cfg.get("weight", weights.get("ruff", 0.0)),
                max_errors=ruff_cfg.get("max_errors", 100),
                source=ruff_cfg.get("source", "src"),
            ),
            pyright=EvaluatorConfig(
                enabled=pyright_cfg.get("enabled", False),
                timeout=pyright_cfg.get("timeout", 60),
                weight=pyright_cfg.get("weight", weights.get("pyright", 0.0)),
                max_errors=pyright_cfg.get("max_errors", 50),
                source=pyright_cfg.get("source", "src"),
            ),
            icrl=ICRLConfig(
                enabled=icrl_data.get("enabled", True),
                top_k=icrl_data.get("top_k", 5),
                include_failures=icrl_data.get("include_failures", True),
                max_context_tokens=icrl_data.get("max_context_tokens", 10000),
                compression_threshold=icrl_data.get("compression_threshold", 20),
                filter_strategy=icrl_data.get("filter_strategy", "quality_diversity"),
                top_k_ratio=icrl_data.get("top_k_ratio", 0.6),
                failure_ratio=icrl_data.get("failure_ratio", 0.2),
                diversity_ratio=icrl_data.get("diversity_ratio", 0.2),
            ),
            circuit_breaker=CircuitBreakerConfig(
                enabled=circuit_breaker_data.get("enabled", True),
                no_progress_threshold=circuit_breaker_data.get("no_progress_threshold", 3),
                same_error_threshold=circuit_breaker_data.get("same_error_threshold", 5),
                reward_decline_threshold=circuit_breaker_data.get("reward_decline_threshold", 0.1),
                half_open_threshold=circuit_breaker_data.get("half_open_threshold", 2),
            ),
            strategy=StrategyConfig(
                improve_threshold=strategy_data.get("improve_threshold", 0.05),
                decline_threshold=strategy_data.get("decline_threshold", -0.05),
                stuck_threshold=strategy_data.get("stuck_threshold", 0.02),
                min_variance_window=strategy_data.get("min_variance_window", 3),
                max_consecutive_mode=strategy_data.get("max_consecutive_mode", 5),
            ),
            performance=PerformanceConfig(
                parallel_evaluators=performance_data.get("parallel_evaluators", True),
                max_workers=performance_data.get("max_workers", 4),
                cache_enabled=performance_data.get("cache_enabled", False),
                cache_by_file_hash=performance_data.get("cache_by_file_hash", False),
            ),
            database=DatabaseConfig(
                journal_mode=database_data.get("journal_mode", "WAL"),
                synchronous=database_data.get("synchronous", "NORMAL"),
                cache_size=database_data.get("cache_size", -64000),
            ),
            feedback=FeedbackConfig(
                include_failed_tests=feedback_data.get("include_failed_tests", True),
                max_failures_shown=feedback_data.get("max_failures_shown", 5),
                include_coverage_delta=feedback_data.get("include_coverage_delta", True),
                verbose=feedback_data.get("verbose", False),
                show_circuit_status=feedback_data.get("show_circuit_status", True),
                show_strategy_mode=feedback_data.get("show_strategy_mode", True),
                compress_old_feedback=feedback_data.get("compress_old_feedback", False),
            ),
            logging=LoggingConfig(
                enabled=logging_data.get("enabled", True),
                level=logging_data.get("level", "INFO"),
                file=logging_data.get("file", "obsidian.log"),
                max_size_mb=logging_data.get("max_size_mb", 10),
                backup_count=logging_data.get("backup_count", 3),
                json_format=logging_data.get("json_format", False),
                log_evaluations=logging_data.get("log_evaluations", True),
                log_state_changes=logging_data.get("log_state_changes", True),
                log_circuit_breaker=logging_data.get("log_circuit_breaker", True),
                log_strategy_changes=logging_data.get("log_strategy_changes", True),
            ),
            response_analysis=ResponseAnalysisConfig(
                enabled=response_analysis_data.get("enabled", True),
                completion_threshold=response_analysis_data.get("completion_threshold", 40),
                stuck_error_count=response_analysis_data.get("stuck_error_count", 5),
                detect_test_only=response_analysis_data.get("detect_test_only", True),
                detect_no_work=response_analysis_data.get("detect_no_work", True),
                detect_stuck=response_analysis_data.get("detect_stuck", True),
            ),
            error_handling=ErrorHandlingConfig(
                max_retries=error_handling_data.get("max_retries", 3),
                retry_delay_seconds=error_handling_data.get("retry_delay_seconds", 5.0),
                global_timeout_seconds=error_handling_data.get("global_timeout_seconds", 300),
                continue_on_evaluator_failure=error_handling_data.get("continue_on_evaluator_failure", True),
                fallback_reward=error_handling_data.get("fallback_reward", 0.0),
            ),
            hooks=HooksConfig(
                session_start=HookConfig(
                    enabled=hooks_data.get("session_start", {}).get("enabled", True),
                    timeout=hooks_data.get("session_start", {}).get("timeout", 10),
                ),
                stop=HookConfig(
                    enabled=hooks_data.get("stop", {}).get("enabled", True),
                    timeout=hooks_data.get("stop", {}).get("timeout", 300),
                ),
                post_tool_use=HookConfig(
                    enabled=hooks_data.get("post_tool_use", {}).get("enabled", False),
                    timeout=hooks_data.get("post_tool_use", {}).get("timeout", 5),
                ),
            ),
            advanced=AdvancedConfig(
                prune_old_episodes=advanced_data.get("prune_old_episodes", True),
                prune_threshold=advanced_data.get("prune_threshold", 100),
                semantic_confidence_threshold=advanced_data.get("semantic_confidence_threshold", 0.5),
                semantic_decay_rate=advanced_data.get("semantic_decay_rate", 0.95),
                track_strategy_effectiveness=advanced_data.get("track_strategy_effectiveness", True),
                debug=advanced_data.get("debug", False),
                dry_run=advanced_data.get("dry_run", False),
            ),
        )


def find_config_file(start_path: str | Path) -> Path | None:
    """Find obsidian.yaml config file by walking up from start_path."""
    current = Path(start_path).resolve()

    while current != current.parent:
        config_path = current / "obsidian.yaml"
        if config_path.exists():
            return config_path
        current = current.parent

    return None


def load_config(project_path: str | Path) -> ObsidianConfig:
    """Load configuration from obsidian.yaml or use defaults."""
    config_file = find_config_file(project_path)

    if config_file is None:
        return ObsidianConfig()

    with open(config_file) as f:
        data = yaml.safe_load(f) or {}

    return ObsidianConfig.from_dict(data)


def get_state_dir(project_path: str | Path, config: ObsidianConfig) -> Path:
    """Get the state directory path, creating it if needed."""
    state_dir = Path(project_path) / config.state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir
