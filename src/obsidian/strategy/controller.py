"""Strategy controller for adaptive mode selection."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..memory.store import MemoryStore
from ..memory.episodic import EpisodicMemory
from ..memory.procedural import ProceduralMemory
from .modes import StrategyMode, ModeRecommendation, get_mode_prompt
from .stuck_detector import StuckDetector, StuckAnalysis


@dataclass
class StrategyState:
    """Current state of the strategy controller."""

    current_mode: StrategyMode
    mode_history: list[str]  # History of mode names
    consecutive_same_mode: int
    last_recommendation: ModeRecommendation | None
    stuck_analysis: StuckAnalysis | None


class StrategyController:
    """
    Adaptive strategy controller for the learning loop.

    Analyzes reward patterns and recommends strategy modes:
    - EXPLOIT: Refine working approach
    - EXPLORE: Try something different
    - AUTONOMOUS: Let model decide

    Tracks strategy effectiveness over time.
    """

    def __init__(
        self,
        state_dir: Path,
        session_id: str,
        improve_threshold: float = 0.05,
        decline_threshold: float = -0.05,
        max_consecutive_mode: int = 5,
        use_procedural_memory: bool = True,
    ):
        self.state_dir = state_dir
        self.session_id = session_id
        self.improve_threshold = improve_threshold
        self.decline_threshold = decline_threshold
        self.max_consecutive_mode = max_consecutive_mode
        self.use_procedural_memory = use_procedural_memory

        # Initialize components
        db_path = state_dir / "memory.db"
        self._store = MemoryStore(db_path)
        self._memory = EpisodicMemory(self._store)
        self._procedural = ProceduralMemory(self._store)
        self._stuck_detector = StuckDetector()

        # Track state
        self._mode_history: list[StrategyMode] = []
        self._last_recommendation: ModeRecommendation | None = None

    def get_reward_history(self) -> list[float]:
        """Get reward history from memory."""
        state = self._memory.get_session_state(self.session_id)
        return state.reward_history

    def compute_trend(self, window: int = 5) -> float:
        """Compute recent reward trend."""
        history = self.get_reward_history()
        if len(history) < 2:
            return 0.0

        recent = history[-window:]
        return recent[-1] - recent[0]

    def analyze_stuck(self) -> StuckAnalysis:
        """Analyze if learning is stuck."""
        history = self.get_reward_history()
        return self._stuck_detector.analyze(history)

    def recommend_mode(self) -> ModeRecommendation:
        """
        Recommend strategy mode based on current state.

        Decision logic:
        1. If stuck → EXPLORE (unless EXPLORE has poor track record)
        2. If improving significantly → EXPLOIT
        3. If declining → EXPLORE
        4. Check procedural memory for strategy effectiveness
        5. Otherwise → AUTONOMOUS
        """
        history = self.get_reward_history()

        if len(history) < 3:
            # Too early to make informed decision
            recommendation = ModeRecommendation(
                mode=StrategyMode.AUTONOMOUS,
                confidence=0.5,
                reason="Insufficient history for informed recommendation",
                evidence={"attempts": len(history)},
            )
            self._last_recommendation = recommendation
            return recommendation

        # Check stuck patterns
        stuck_analysis = self.analyze_stuck()
        if stuck_analysis.is_stuck:
            # Recommend explore, but check if it has been ineffective
            mode = StrategyMode.EXPLORE

            if self.use_procedural_memory:
                explore_record = self._procedural.get_strategy("explore")
                if explore_record and explore_record.usage_count >= 3 and explore_record.avg_delta < -0.01:
                    # Explore has been making things worse, try exploit instead
                    mode = StrategyMode.EXPLOIT

            recommendation = ModeRecommendation(
                mode=mode,
                confidence=stuck_analysis.confidence,
                reason=f"Stuck pattern detected: {stuck_analysis.pattern.value if stuck_analysis.pattern else 'unknown'}",
                evidence={
                    "stuck_analysis": {
                        "pattern": stuck_analysis.pattern.value if stuck_analysis.pattern else None,
                        "severity": stuck_analysis.severity,
                        "details": stuck_analysis.details,
                    }
                },
            )
            self._last_recommendation = recommendation
            return recommendation

        # Analyze trend
        trend = self.compute_trend()

        if trend > self.improve_threshold:
            # Improving significantly - exploit
            recommendation = ModeRecommendation(
                mode=StrategyMode.EXPLOIT,
                confidence=min(0.9, 0.6 + abs(trend)),
                reason=f"Positive trend ({trend:+.3f}) suggests current approach is working",
                evidence={"trend": trend, "threshold": self.improve_threshold},
            )
        elif trend < self.decline_threshold:
            # Declining - explore
            recommendation = ModeRecommendation(
                mode=StrategyMode.EXPLORE,
                confidence=min(0.85, 0.6 + abs(trend)),
                reason=f"Negative trend ({trend:+.3f}) suggests need for different approach",
                evidence={"trend": trend, "threshold": self.decline_threshold},
            )
        else:
            # Neutral - check procedural memory for best strategy
            mode = StrategyMode.AUTONOMOUS
            reason = "Trend is neutral - autonomous decision appropriate"

            if self.use_procedural_memory:
                recommended = self._procedural.get_recommended_strategy(min_uses=2)
                if recommended and recommended.avg_delta > 0.02:
                    # Use the historically best strategy
                    if recommended.name == "exploit":
                        mode = StrategyMode.EXPLOIT
                        reason = f"Procedural memory suggests EXPLOIT (avg delta: {recommended.avg_delta:+.3f})"
                    elif recommended.name == "explore":
                        mode = StrategyMode.EXPLORE
                        reason = f"Procedural memory suggests EXPLORE (avg delta: {recommended.avg_delta:+.3f})"

            recommendation = ModeRecommendation(
                mode=mode,
                confidence=0.7,
                reason=reason,
                evidence={"trend": trend},
            )

        # Check for mode fatigue (too many consecutive same mode)
        if self._should_force_switch(recommendation.mode):
            recommendation = ModeRecommendation(
                mode=self._get_alternative_mode(recommendation.mode),
                confidence=0.6,
                reason=f"Forced mode switch after {self.max_consecutive_mode} consecutive attempts",
                evidence={
                    "consecutive_count": len(self._mode_history),
                    "original_recommendation": recommendation.mode.value,
                },
            )

        self._mode_history.append(recommendation.mode)
        self._last_recommendation = recommendation
        return recommendation

    def _should_force_switch(self, mode: StrategyMode) -> bool:
        """Check if we should force a mode switch."""
        if len(self._mode_history) < self.max_consecutive_mode:
            return False

        recent = self._mode_history[-self.max_consecutive_mode :]
        return all(m == mode for m in recent)

    def _get_alternative_mode(self, current: StrategyMode) -> StrategyMode:
        """Get alternative mode when forcing switch."""
        if current == StrategyMode.EXPLOIT:
            return StrategyMode.EXPLORE
        elif current == StrategyMode.EXPLORE:
            return StrategyMode.EXPLOIT
        else:
            # For AUTONOMOUS, check what we've been doing
            exploits = sum(1 for m in self._mode_history[-5:] if m == StrategyMode.EXPLOIT)
            return StrategyMode.EXPLORE if exploits > 2 else StrategyMode.EXPLOIT

    def get_mode_prompt(self, mode: StrategyMode | None = None) -> str:
        """Get prompt guidance for a mode."""
        if mode is None:
            recommendation = self.recommend_mode()
            mode = recommendation.mode
        return get_mode_prompt(mode)

    def get_state(self) -> StrategyState:
        """Get current strategy state."""
        current_mode = (
            self._mode_history[-1] if self._mode_history else StrategyMode.AUTONOMOUS
        )

        # Count consecutive same mode
        consecutive = 1
        for i in range(len(self._mode_history) - 2, -1, -1):
            if self._mode_history[i] == current_mode:
                consecutive += 1
            else:
                break

        return StrategyState(
            current_mode=current_mode,
            mode_history=[m.value for m in self._mode_history],
            consecutive_same_mode=consecutive,
            last_recommendation=self._last_recommendation,
            stuck_analysis=self.analyze_stuck() if self.get_reward_history() else None,
        )

    def record_strategy_outcome(
        self,
        mode: StrategyMode,
        reward_before: float,
        reward_after: float,
        description: str = "",
    ) -> None:
        """
        Record the outcome of a strategy for learning.

        Updates procedural memory with strategy effectiveness.
        """
        self._procedural.record_outcome(
            strategy_name=mode.value,
            reward_before=reward_before,
            reward_after=reward_after,
            description=description or mode.name,
        )

    def get_strategy_stats(self) -> dict[str, Any]:
        """
        Get strategy effectiveness statistics.

        Returns per-strategy stats keyed by strategy name.
        """
        strategies = self._procedural.get_all_strategies()
        stats = {}
        for s in strategies:
            stats[s.name] = {
                "total_delta": s.total_reward_delta,
                "usage_count": s.usage_count,
                "success_count": s.success_count,
                "success_rate": s.success_rate,
                "avg_delta": s.avg_delta,
            }
        return stats

    def get_aggregate_stats(self) -> dict[str, Any]:
        """Get aggregate statistics across all strategies."""
        return self._procedural.get_stats()

    def close(self) -> None:
        """Close database connection."""
        self._store.close()
