"""Obsidian: Obsessive learning loop plugin for Claude Code."""

__version__ = "0.1.0"

from .config import (
    ObsidianConfig,
    load_config,
    get_state_dir,
)
from .errors import (
    ObsidianError,
    EvaluatorError,
    MemoryError,
    ConfigurationError,
    TimeoutError,
    HookError,
    ErrorSeverity,
    ErrorCategory,
    with_retry,
    retry,
    GracefulDegradation,
    safe_execute,
)
from .logging import (
    setup_logging,
    get_logger,
    ObsidianLogger,
)

__all__ = [
    # Version
    "__version__",
    # Config
    "ObsidianConfig",
    "load_config",
    "get_state_dir",
    # Errors
    "ObsidianError",
    "EvaluatorError",
    "MemoryError",
    "ConfigurationError",
    "TimeoutError",
    "HookError",
    "ErrorSeverity",
    "ErrorCategory",
    "with_retry",
    "retry",
    "GracefulDegradation",
    "safe_execute",
    # Logging
    "setup_logging",
    "get_logger",
    "ObsidianLogger",
]
