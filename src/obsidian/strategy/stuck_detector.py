"""Stuck pattern detection for the learning loop."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StuckPattern(Enum):
    """Types of stuck patterns that can be detected."""

    FLAT = "flat"  # Reward not changing
    OSCILLATING = "oscillating"  # Reward bouncing up and down
    DECLINING = "declining"  # Reward steadily decreasing
    PLATEAU = "plateau"  # Stuck at local maximum


@dataclass
class StuckAnalysis:
    """Result of stuck pattern analysis."""

    is_stuck: bool
    pattern: StuckPattern | None
    confidence: float  # 0-1
    severity: float  # 0-1, how stuck
    recommendation: str
    details: dict[str, Any]


class StuckDetector:
    """
    Detects when the learning loop is stuck and recommends action.

    Analyzes reward history patterns to identify:
    - Flat rewards (no progress)
    - Oscillating patterns (back and forth)
    - Declining trends (getting worse)
    - Plateaus (stuck at local max)
    """

    def __init__(
        self,
        flat_threshold: float = 0.02,
        oscillation_threshold: float = 0.05,
        decline_threshold: float = -0.03,
        min_window: int = 3,
    ):
        self.flat_threshold = flat_threshold
        self.oscillation_threshold = oscillation_threshold
        self.decline_threshold = decline_threshold
        self.min_window = min_window

    def analyze(self, reward_history: list[float]) -> StuckAnalysis:
        """
        Analyze reward history for stuck patterns.

        Args:
            reward_history: List of rewards from oldest to newest

        Returns:
            StuckAnalysis with detection results
        """
        if len(reward_history) < self.min_window:
            return StuckAnalysis(
                is_stuck=False,
                pattern=None,
                confidence=0.0,
                severity=0.0,
                recommendation="Continue exploring - not enough history",
                details={"attempts": len(reward_history)},
            )

        # Check each pattern type
        analyses = [
            self._detect_flat(reward_history),
            self._detect_oscillating(reward_history),
            self._detect_declining(reward_history),
            self._detect_plateau(reward_history),
        ]

        # Return the most severe stuck pattern
        stuck_analyses = [a for a in analyses if a.is_stuck]

        if not stuck_analyses:
            return StuckAnalysis(
                is_stuck=False,
                pattern=None,
                confidence=0.0,
                severity=0.0,
                recommendation="Progress is healthy - continue current approach",
                details=self._compute_trend_details(reward_history),
            )

        # Return highest severity
        return max(stuck_analyses, key=lambda a: a.severity)

    def _detect_flat(self, history: list[float]) -> StuckAnalysis:
        """Detect flat reward pattern."""
        recent = history[-self.min_window:]
        variance = max(recent) - min(recent)

        is_flat = variance < self.flat_threshold
        severity = 1.0 - (variance / self.flat_threshold) if is_flat else 0.0

        return StuckAnalysis(
            is_stuck=is_flat,
            pattern=StuckPattern.FLAT if is_flat else None,
            confidence=0.9 if is_flat else 0.1,
            severity=severity,
            recommendation=(
                "Reward is flat - try a different approach"
                if is_flat
                else "Reward has variance"
            ),
            details={
                "variance": variance,
                "threshold": self.flat_threshold,
                "recent_rewards": recent,
            },
        )

    def _detect_oscillating(self, history: list[float]) -> StuckAnalysis:
        """Detect oscillating reward pattern (up-down-up-down)."""
        if len(history) < 4:
            return StuckAnalysis(
                is_stuck=False,
                pattern=None,
                confidence=0.0,
                severity=0.0,
                recommendation="Need more history for oscillation detection",
                details={},
            )

        recent = history[-4:]
        deltas = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]

        # Check for alternating signs
        sign_changes = sum(
            1 for i in range(len(deltas) - 1) if deltas[i] * deltas[i + 1] < 0
        )

        # Check magnitude of swings
        swing_magnitude = max(abs(d) for d in deltas)

        is_oscillating = (
            sign_changes >= 2 and swing_magnitude >= self.oscillation_threshold
        )

        return StuckAnalysis(
            is_stuck=is_oscillating,
            pattern=StuckPattern.OSCILLATING if is_oscillating else None,
            confidence=0.85 if is_oscillating else 0.1,
            severity=min(1.0, swing_magnitude / 0.2) if is_oscillating else 0.0,
            recommendation=(
                "Oscillating pattern detected - commit to one approach"
                if is_oscillating
                else "No oscillation detected"
            ),
            details={
                "deltas": deltas,
                "sign_changes": sign_changes,
                "swing_magnitude": swing_magnitude,
            },
        )

    def _detect_declining(self, history: list[float]) -> StuckAnalysis:
        """Detect steadily declining reward trend."""
        recent = history[-self.min_window:]

        # Compute trend (linear regression slope approximation)
        n = len(recent)
        avg_x = (n - 1) / 2
        avg_y = sum(recent) / n

        numerator = sum((i - avg_x) * (recent[i] - avg_y) for i in range(n))
        denominator = sum((i - avg_x) ** 2 for i in range(n))

        slope = numerator / denominator if denominator > 0 else 0

        is_declining = slope < self.decline_threshold

        return StuckAnalysis(
            is_stuck=is_declining,
            pattern=StuckPattern.DECLINING if is_declining else None,
            confidence=0.8 if is_declining else 0.1,
            severity=min(1.0, abs(slope) / 0.1) if is_declining else 0.0,
            recommendation=(
                "Declining trend - current approach is making things worse"
                if is_declining
                else "No decline detected"
            ),
            details={
                "slope": slope,
                "threshold": self.decline_threshold,
            },
        )

    def _detect_plateau(self, history: list[float]) -> StuckAnalysis:
        """Detect plateau at local maximum."""
        if len(history) < 5:
            return StuckAnalysis(
                is_stuck=False,
                pattern=None,
                confidence=0.0,
                severity=0.0,
                recommendation="Need more history for plateau detection",
                details={},
            )

        recent = history[-5:]
        best_recent = max(recent)
        current = recent[-1]

        # Check if we're near the best and not improving
        near_best = abs(current - best_recent) < 0.05
        flat_at_top = (
            max(recent[-3:]) - min(recent[-3:]) < self.flat_threshold
        )

        is_plateau = near_best and flat_at_top and current > 0.7

        return StuckAnalysis(
            is_stuck=is_plateau,
            pattern=StuckPattern.PLATEAU if is_plateau else None,
            confidence=0.7 if is_plateau else 0.1,
            severity=0.6 if is_plateau else 0.0,
            recommendation=(
                "Plateau detected - may need different strategy to break through"
                if is_plateau
                else "Not at plateau"
            ),
            details={
                "current": current,
                "best_recent": best_recent,
                "near_best": near_best,
                "flat_at_top": flat_at_top,
            },
        )

    def _compute_trend_details(self, history: list[float]) -> dict[str, Any]:
        """Compute trend details for non-stuck case."""
        if len(history) < 2:
            return {"trend": 0.0}

        recent = history[-min(5, len(history)) :]
        trend = recent[-1] - recent[0]

        return {
            "trend": trend,
            "improving": trend > 0.02,
            "recent_rewards": recent,
        }


def is_stuck(
    reward_history: list[float],
    threshold: float = 0.02,
    window: int = 3,
) -> bool:
    """Simple stuck detection for quick checks."""
    if len(reward_history) < window:
        return False

    recent = reward_history[-window:]
    variance = max(recent) - min(recent)
    return variance < threshold
