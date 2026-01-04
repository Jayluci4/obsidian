"""Base classes for metric evaluation."""

import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalResult:
    """Result from a metric evaluator."""

    name: str
    score: float  # Normalized 0-1 score
    passed: bool  # Binary pass/fail
    raw_value: Any = None  # Original value from tool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    execution_time_ms: float = 0.0

    @property
    def failed(self) -> bool:
        """Return True if evaluation failed (had error or didn't pass)."""
        return self.error is not None or not self.passed


class MetricCollector(ABC):
    """Abstract base class for metric collectors."""

    def __init__(self, name: str, timeout: int = 120):
        self.name = name
        self.timeout = timeout

    @abstractmethod
    def collect(self, project_path: str) -> EvalResult:
        """
        Collect metrics from the project.

        Args:
            project_path: Root path of the project to analyze

        Returns:
            EvalResult with normalized score
        """
        pass

    def run_command(
        self,
        cmd: list[str],
        cwd: str,
        timeout: int | None = None,
    ) -> tuple[str, str, int]:
        """
        Run a subprocess command.

        Args:
            cmd: Command and arguments
            cwd: Working directory
            timeout: Optional timeout override

        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", f"Command timed out after {timeout or self.timeout}s", -1
        except FileNotFoundError as e:
            return "", f"Command not found: {e}", -1
        except Exception as e:
            return "", f"Error running command: {e}", -1


def compute_composite_reward(
    results: list[EvalResult],
    weights: dict[str, float],
) -> float:
    """
    Compute weighted composite reward from multiple evaluator results.

    Args:
        results: List of EvalResult from different evaluators
        weights: Mapping of evaluator name to weight

    Returns:
        Composite reward in range [0, 1]
    """
    if not results:
        return 0.0

    # Only use results that succeeded
    valid_results = [r for r in results if r.error is None]
    if not valid_results:
        return 0.0

    # Normalize weights for valid results only
    total_weight = sum(weights.get(r.name, 0.0) for r in valid_results)
    if total_weight == 0:
        # Equal weight if no weights specified
        total_weight = len(valid_results)
        weights = {r.name: 1.0 for r in valid_results}

    weighted_sum = sum(r.score * weights.get(r.name, 0.0) for r in valid_results)

    return weighted_sum / total_weight
