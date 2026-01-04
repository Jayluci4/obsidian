"""Delta tracking for measuring improvement/regression from baseline."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .composite import CompositeResult


@dataclass
class Baseline:
    """Stored baseline metrics."""

    timestamp: str
    reward: float
    metrics: dict[str, float]
    attempt_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "reward": self.reward,
            "metrics": self.metrics,
            "attempt_number": self.attempt_number,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Baseline":
        """Create from dictionary."""
        return cls(
            timestamp=data.get("timestamp", ""),
            reward=data.get("reward", 0.0),
            metrics=data.get("metrics", {}),
            attempt_number=data.get("attempt_number", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DeltaResult:
    """Result of comparing current metrics to baseline."""

    current_reward: float
    baseline_reward: float
    delta: float  # current - baseline
    delta_percent: float  # percentage change
    is_improvement: bool
    metric_deltas: dict[str, float]  # per-metric deltas
    improved_metrics: list[str]
    regressed_metrics: list[str]


class DeltaTracker:
    """Tracks deltas between current metrics and baseline."""

    def __init__(
        self,
        state_dir: Path,
        significance_threshold: float = 0.01,
    ):
        self.state_dir = state_dir
        self.baseline_file = state_dir / "baseline.json"
        self.significance_threshold = significance_threshold
        self._baseline: Baseline | None = None

    def load_baseline(self) -> Baseline | None:
        """Load baseline from disk."""
        if self._baseline is not None:
            return self._baseline

        if not self.baseline_file.exists():
            return None

        try:
            with open(self.baseline_file) as f:
                data = json.load(f)
            self._baseline = Baseline.from_dict(data)
            return self._baseline
        except (json.JSONDecodeError, KeyError):
            return None

    def save_baseline(
        self,
        result: CompositeResult,
        attempt_number: int = 0,
    ) -> Baseline:
        """Save current result as new baseline."""
        baseline = Baseline(
            timestamp=datetime.utcnow().isoformat(),
            reward=result.reward,
            metrics=result.metrics,
            attempt_number=attempt_number,
            metadata={
                "evaluators": [r.name for r in result.results],
                "weights": result.weights,
            },
        )

        self.state_dir.mkdir(parents=True, exist_ok=True)

        with open(self.baseline_file, "w") as f:
            json.dump(baseline.to_dict(), f, indent=2)

        self._baseline = baseline
        return baseline

    def compute_delta(self, result: CompositeResult) -> DeltaResult | None:
        """Compute delta between current result and baseline."""
        baseline = self.load_baseline()
        if baseline is None:
            return None

        current = result.reward
        base = baseline.reward

        delta = current - base
        delta_percent = (delta / base * 100) if base > 0 else 0.0

        # Compute per-metric deltas
        metric_deltas = {}
        improved = []
        regressed = []

        for name, current_score in result.metrics.items():
            baseline_score = baseline.metrics.get(name, 0.0)
            metric_delta = current_score - baseline_score
            metric_deltas[name] = metric_delta

            if metric_delta > self.significance_threshold:
                improved.append(name)
            elif metric_delta < -self.significance_threshold:
                regressed.append(name)

        return DeltaResult(
            current_reward=current,
            baseline_reward=base,
            delta=delta,
            delta_percent=delta_percent,
            is_improvement=delta > self.significance_threshold,
            metric_deltas=metric_deltas,
            improved_metrics=improved,
            regressed_metrics=regressed,
        )

    def should_update_baseline(
        self,
        result: CompositeResult,
        threshold: float = 0.05,
    ) -> bool:
        """Check if current result should become new baseline."""
        baseline = self.load_baseline()
        if baseline is None:
            return True

        # Update if improvement exceeds threshold
        delta = result.reward - baseline.reward
        return delta > threshold


def format_delta_feedback(delta: DeltaResult | None) -> str:
    """Format delta result for feedback message."""
    if delta is None:
        return "No baseline for comparison"

    lines = []

    # Overall delta
    sign = "+" if delta.delta >= 0 else ""
    lines.append(f"Change from baseline: {sign}{delta.delta:.3f} ({sign}{delta.delta_percent:.1f}%)")

    # Improved metrics
    if delta.improved_metrics:
        lines.append(f"Improved: {', '.join(delta.improved_metrics)}")

    # Regressed metrics
    if delta.regressed_metrics:
        lines.append(f"Regressed: {', '.join(delta.regressed_metrics)}")

    return "\n".join(lines)
