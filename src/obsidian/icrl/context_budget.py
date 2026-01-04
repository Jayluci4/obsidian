"""Context budget manager for ICRL context injection.

Manages token usage to stay within Claude's context limit.
Uses adaptive episode selection based on budget constraints.
"""

from dataclasses import dataclass
from typing import Any


# Approximate tokens per character (conservative estimate)
CHARS_PER_TOKEN = 4

# Claude Opus 4.5 context limit
MAX_CONTEXT_TOKENS = 200_000

# Default budget for ICRL context (5% of total)
DEFAULT_BUDGET = 10_000


@dataclass
class BudgetResult:
    """Result of context budget allocation."""

    episodes_included: int
    tokens_used: int
    budget: int
    budget_exceeded: bool
    compression_applied: bool


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a text string.

    Uses character count / 4 as approximation.
    Claude tokenizer averages ~4 chars per token.
    """
    return len(text) // CHARS_PER_TOKEN


def estimate_episode_tokens(episode: dict[str, Any]) -> int:
    """
    Estimate tokens for a single episode.

    Accounts for:
    - XML tags and structure
    - Action summary
    - Metrics
    - Failures (if present)
    """
    tokens = 0

    # Base structure (tags, attributes)
    tokens += 20

    # Attempt number, reward
    tokens += 10

    # Action summary
    summary = episode.get("action_summary", "")
    tokens += estimate_tokens(summary)

    # Metrics
    metrics = episode.get("metrics", {})
    metrics_str = ", ".join(f"{k}={v:.2f}" for k, v in metrics.items())
    tokens += estimate_tokens(f"Metrics: {metrics_str}")

    # Failures
    failures = episode.get("failures", [])
    for failure in failures[:3]:  # Only first 3 are included
        tokens += estimate_tokens(f"  - {failure}")

    return tokens


def compress_episode(
    episode: dict[str, Any],
    level: int = 1,
) -> dict[str, Any]:
    """
    Compress an episode to reduce token usage.

    Compression levels:
    - 1: Truncate action summary, limit failures
    - 2: Remove failures, minimal summary
    - 3: Metrics only
    """
    compressed = {
        "attempt_number": episode.get("attempt_number"),
        "reward": episode.get("reward"),
        "metrics": episode.get("metrics", {}),
    }

    summary = episode.get("action_summary", "")

    if level == 1:
        # Truncate summary to 100 chars
        if len(summary) > 100:
            summary = summary[:97] + "..."
        compressed["action_summary"] = summary
        # Keep only first failure
        failures = episode.get("failures", [])
        if failures:
            compressed["failures"] = failures[:1]

    elif level == 2:
        # Minimal summary, no failures
        if len(summary) > 50:
            summary = summary[:47] + "..."
        compressed["action_summary"] = summary

    else:
        # Level 3: metrics only
        pass

    return compressed


class ContextBudgetManager:
    """
    Manages context budget for ICRL episode injection.

    Features:
    - Token estimation for episodes
    - Adaptive episode selection within budget
    - Progressive compression for older episodes
    - Budget tracking and reporting
    """

    def __init__(
        self,
        max_tokens: int = DEFAULT_BUDGET,
        compression_threshold: int = 20,
    ):
        """
        Initialize budget manager.

        Args:
            max_tokens: Maximum tokens for ICRL context
            compression_threshold: Compress episodes older than this
        """
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold

        # Track usage
        self._tokens_used = 0
        self._episodes_included = 0

    def allocate_episodes(
        self,
        episodes: list[dict[str, Any]],
        current_attempt: int = 0,
    ) -> tuple[list[dict[str, Any]], BudgetResult]:
        """
        Allocate budget across episodes, applying compression as needed.

        Args:
            episodes: List of episodes (already filtered/sorted)
            current_attempt: Current attempt number (for age calculation)

        Returns:
            Tuple of (allocated episodes, budget result)
        """
        allocated = []
        tokens_used = 0
        compression_applied = False

        # Reserve tokens for meta-instruction and structure
        structure_overhead = 150  # Estimated tokens for headers, tags, etc.
        available = self.max_tokens - structure_overhead

        for episode in episodes:
            attempt_num = episode.get("attempt_number", 0)
            age = current_attempt - attempt_num if current_attempt > 0 else 0

            # Apply compression based on age
            if age > self.compression_threshold * 2:
                compressed = compress_episode(episode, level=3)
                compression_applied = True
            elif age > self.compression_threshold:
                compressed = compress_episode(episode, level=2)
                compression_applied = True
            elif age > self.compression_threshold // 2:
                compressed = compress_episode(episode, level=1)
                compression_applied = True
            else:
                compressed = episode

            # Estimate tokens
            episode_tokens = estimate_episode_tokens(compressed)

            # Check budget
            if tokens_used + episode_tokens > available:
                # Try more aggressive compression
                if age <= self.compression_threshold:
                    compressed = compress_episode(episode, level=2)
                    episode_tokens = estimate_episode_tokens(compressed)
                    compression_applied = True

                    if tokens_used + episode_tokens > available:
                        compressed = compress_episode(episode, level=3)
                        episode_tokens = estimate_episode_tokens(compressed)

                        if tokens_used + episode_tokens > available:
                            # Still over budget, skip this episode
                            continue

            allocated.append(compressed)
            tokens_used += episode_tokens

        # Update tracking
        self._tokens_used = tokens_used + structure_overhead
        self._episodes_included = len(allocated)

        result = BudgetResult(
            episodes_included=len(allocated),
            tokens_used=self._tokens_used,
            budget=self.max_tokens,
            budget_exceeded=self._tokens_used > self.max_tokens,
            compression_applied=compression_applied,
        )

        return allocated, result

    def get_adaptive_top_k(
        self,
        total_episodes: int,
        base_k: int = 5,
    ) -> int:
        """
        Calculate adaptive top-k based on total episodes and budget.

        Early in session: include more episodes
        Later in session: include fewer, more compressed

        Args:
            total_episodes: Total number of episodes available
            base_k: Base number of episodes to include

        Returns:
            Adjusted k value
        """
        if total_episodes <= base_k:
            return total_episodes

        # Estimate average tokens per episode
        avg_tokens_per_episode = 100  # Conservative estimate

        # Calculate max episodes that fit in budget
        max_by_budget = self.max_tokens // avg_tokens_per_episode

        # Scale k based on session progress
        # More episodes = older session = need compression
        if total_episodes > 50:
            # Old session, be more selective
            return min(base_k, max_by_budget // 2)
        elif total_episodes > 20:
            # Mid session
            return min(base_k + 2, max_by_budget)
        else:
            # Early session, can include more
            return min(base_k + 4, total_episodes, max_by_budget)

    def get_usage(self) -> dict[str, Any]:
        """Get current budget usage stats."""
        return {
            "tokens_used": self._tokens_used,
            "budget": self.max_tokens,
            "utilization": self._tokens_used / self.max_tokens if self.max_tokens > 0 else 0,
            "episodes_included": self._episodes_included,
            "remaining": max(0, self.max_tokens - self._tokens_used),
        }

    def reset(self) -> None:
        """Reset usage tracking."""
        self._tokens_used = 0
        self._episodes_included = 0
