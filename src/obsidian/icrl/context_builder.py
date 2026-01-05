"""ICRL context builder for injecting experience into prompts."""

from pathlib import Path
from typing import Any

from ..memory.store import MemoryStore
from ..memory.episodic import EpisodicMemory, Episode
from ..memory.semantic import SemanticMemory
from ..memory.procedural import ProceduralMemory
from .prompt_templates import (
    format_experience_buffer,
    format_meta_instruction,
    format_full_context,
)


class ICRLContextBuilder:
    """
    Builds ICRL context for prompt injection.

    Retrieves top-K episodes from memory and formats them
    for injection into Claude's context. Also includes:
    - Semantic memory (learned facts and patterns)
    - Procedural memory (strategy effectiveness)
    """

    def __init__(
        self,
        state_dir: Path,
        session_id: str,
        top_k: int = 5,
        include_failures: bool = True,
        include_semantic: bool = True,
        include_procedural: bool = True,
    ):
        self.state_dir = state_dir
        self.session_id = session_id
        self.top_k = top_k
        self.include_failures = include_failures
        self.include_semantic = include_semantic
        self.include_procedural = include_procedural

        # Initialize memory systems
        db_path = state_dir / "memory.db"
        self._store = MemoryStore(db_path)
        self._memory = EpisodicMemory(self._store)
        self._semantic = SemanticMemory(self._store)
        self._procedural = ProceduralMemory(self._store)

    def _episode_to_dict(self, episode: Episode) -> dict[str, Any]:
        """Convert Episode to dictionary for template formatting."""
        return {
            "attempt_number": episode.attempt_number,
            "reward": episode.reward,
            "action_summary": episode.action_summary,
            "metrics": episode.metrics,
            "failures": episode.failures,
        }

    def get_top_attempts(self) -> list[dict[str, Any]]:
        """Retrieve top-K attempts for context injection."""
        episodes = self._memory.get_top_k_episodes(
            self.session_id,
            k=self.top_k,
            include_failures=self.include_failures,
        )
        return [self._episode_to_dict(e) for e in episodes]

    def get_best_attempt(self) -> dict[str, Any] | None:
        """Get the best attempt so far."""
        episode = self._memory.get_best_episode(self.session_id)
        return self._episode_to_dict(episode) if episode else None

    def get_session_state(self) -> dict[str, Any]:
        """Get current session state."""
        state = self._memory.get_session_state(self.session_id)
        return {
            "attempt_count": state.attempt_count,
            "best_reward": state.best_reward,
            "reward_history": state.reward_history,
            "current_strategy": state.current_strategy,
        }

    def compute_trend(self, window: int = 5) -> float:
        """Compute recent reward trend."""
        return self._memory.compute_reward_trend(self.session_id, window)

    def is_stuck(self, threshold: float = 0.02, window: int = 3) -> bool:
        """Check if progress is stuck."""
        return self._memory.is_stuck(self.session_id, threshold, window)

    def determine_mode(self) -> str:
        """
        Determine strategy mode based on reward patterns.

        Returns:
            "EXPLOIT", "EXPLORE", or "AUTONOMOUS"
        """
        state = self._memory.get_session_state(self.session_id)

        if state.attempt_count < 3:
            # Too early to determine mode
            return "AUTONOMOUS"

        if self.is_stuck():
            return "EXPLORE"

        trend = self.compute_trend()

        if trend > 0.05:
            # Improving, keep refining
            return "EXPLOIT"
        elif trend < -0.05:
            # Declining, try something new
            return "EXPLORE"
        else:
            # Let model decide
            return "AUTONOMOUS"

    def build_experience_buffer(self) -> str:
        """Build formatted experience buffer from top attempts."""
        attempts = self.get_top_attempts()
        if not attempts:
            return ""

        best = self.get_best_attempt()
        best_id = best.get("attempt_number") if best else None

        return format_experience_buffer(attempts, best_id)

    def build_meta_instruction(
        self,
        mode: str | None = None,
        custom_instruction: str | None = None,
    ) -> str:
        """Build meta-instruction based on current state."""
        if mode is None:
            mode = self.determine_mode()

        return format_meta_instruction(
            mode=mode,
            custom_instruction=custom_instruction,
            best_attempt=self.get_best_attempt(),
            trend=self.compute_trend(),
            is_stuck=self.is_stuck(),
        )

    def build_full_context(
        self,
        mode: str | None = None,
        custom_instruction: str | None = None,
    ) -> str:
        """
        Build complete ICRL context for prompt injection.

        Returns formatted context with:
        - Experience buffer (top-K attempts)
        - Meta-instruction (strategy mode + guidance)
        """
        attempts = self.get_top_attempts()
        if not attempts:
            # No history yet, minimal context
            return format_meta_instruction(
                mode="AUTONOMOUS",
                custom_instruction="This is the first attempt. Start fresh.",
            )

        best = self.get_best_attempt()

        if mode is None:
            mode = self.determine_mode()

        return format_full_context(
            attempts=attempts,
            mode=mode,
            best_attempt=best,
            trend=self.compute_trend(),
            is_stuck=self.is_stuck(),
            custom_instruction=custom_instruction,
        )

    def build_session_start_context(self) -> str:
        """
        Build context for SessionStart hook injection.

        This is injected at the start of a session to provide
        historical context including:
        - Episodic memory (past attempts)
        - Semantic memory (learned facts)
        - Procedural memory (strategy effectiveness)
        """
        state = self.get_session_state()

        if state["attempt_count"] == 0:
            return ""  # No history to inject

        # Build compact context
        context = self.build_full_context()

        # Add session summary header
        header = (
            f"=== OBSIDIAN LEARNING CONTEXT ===\n"
            f"Session: {self.session_id}\n"
            f"Previous attempts: {state['attempt_count']}\n"
            f"Best reward: {state['best_reward']:.3f}\n"
            f"================================\n\n"
        )

        # Add semantic memory (learned facts)
        semantic_context = ""
        if self.include_semantic:
            semantic_context = self._semantic.format_for_context(max_facts=5)
            if semantic_context:
                semantic_context = "\n" + semantic_context + "\n"

        # Add procedural memory (strategy knowledge)
        procedural_context = ""
        if self.include_procedural:
            procedural_context = self._procedural.format_for_context(max_strategies=3)
            if procedural_context:
                procedural_context = "\n" + procedural_context + "\n"

        return header + context + semantic_context + procedural_context

    def extract_facts_from_episode(
        self,
        episode_id: str,
        action_summary: str,
        reward: float,
        metrics: dict[str, float],
    ) -> None:
        """
        Extract and store semantic facts from a high-reward episode.

        Called after successful episodes to build long-term memory.
        """
        self._semantic.extract_facts_from_episode(
            episode_id=episode_id,
            action_summary=action_summary,
            reward=reward,
            metrics=metrics,
        )

    def record_strategy_outcome(
        self,
        strategy_name: str,
        reward_before: float,
        reward_after: float,
        description: str = "",
    ) -> None:
        """
        Record the outcome of a strategy for procedural memory.

        Called after each attempt to track strategy effectiveness.
        """
        self._procedural.record_outcome(
            strategy_name=strategy_name,
            reward_before=reward_before,
            reward_after=reward_after,
            description=description,
        )

    def get_recommended_strategy(self) -> str | None:
        """
        Get recommended strategy from procedural memory.

        Returns the most effective strategy based on historical performance.
        """
        record = self._procedural.get_recommended_strategy()
        return record.name if record else None

    def get_semantic_facts(self, max_facts: int = 10) -> list[dict]:
        """Get learned facts from semantic memory."""
        facts = self._semantic.get_facts(min_confidence=0.5, limit=max_facts)
        return [
            {
                "type": f.fact_type.value,
                "content": f.content,
                "confidence": f.confidence,
            }
            for f in facts
        ]

    def get_strategy_stats(self) -> dict[str, Any]:
        """Get strategy effectiveness statistics."""
        return self._procedural.get_stats()

    def close(self) -> None:
        """Close database connection."""
        self._store.close()
