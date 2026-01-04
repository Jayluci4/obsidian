"""
Episode Filtering for ICRL Context.

Based on "Filtering Learning Histories Enhances In-Context Reinforcement Learning"
(Chen et al., 2025) - filtering which episodes to include improves learning.

Key insights:
1. Not all history is equally valuable
2. Quality over quantity - fewer good examples beat many mediocre ones
3. Diversity matters - include different approaches, not just top-K similar ones
4. Negative examples help avoid bad patterns
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class FilteredEpisode:
    """Episode with filtering metadata."""

    episode_id: str
    attempt_number: int
    reward: float
    metrics: dict[str, float]
    action_summary: str
    failures: list[str]

    # Filtering metadata
    inclusion_reason: str  # Why this episode was included
    diversity_score: float  # How different from other selected episodes
    informativeness: float  # How much can be learned from this


class EpisodeFilter:
    """
    Filters episodes for optimal ICRL context.

    Selection criteria:
    1. Top performers (high reward)
    2. Diverse approaches (not just similar attempts)
    3. Informative failures (what to avoid)
    4. Recent context (freshness)
    """

    def __init__(
        self,
        max_episodes: int = 7,
        top_k_ratio: float = 0.6,  # 60% from top performers
        failure_ratio: float = 0.2,  # 20% from failures
        diversity_ratio: float = 0.2,  # 20% for diversity
        min_reward_for_top: float = 0.5,
        max_reward_for_failure: float = 0.4,
    ):
        self.max_episodes = max_episodes
        self.top_k_ratio = top_k_ratio
        self.failure_ratio = failure_ratio
        self.diversity_ratio = diversity_ratio
        self.min_reward_for_top = min_reward_for_top
        self.max_reward_for_failure = max_reward_for_failure

    def filter(
        self,
        episodes: list[dict[str, Any]],
        current_metrics: dict[str, float] | None = None,
    ) -> list[FilteredEpisode]:
        """
        Filter episodes for ICRL context injection.

        Args:
            episodes: List of episode dicts with reward, metrics, action_summary, etc.
            current_metrics: Current evaluation metrics (for relevance scoring)

        Returns:
            Filtered list of episodes with inclusion metadata
        """
        if not episodes:
            return []

        # Calculate slot allocation
        n_top = max(1, int(self.max_episodes * self.top_k_ratio))
        n_failures = max(1, int(self.max_episodes * self.failure_ratio))
        n_diverse = max(1, self.max_episodes - n_top - n_failures)

        selected: list[FilteredEpisode] = []
        selected_ids: set[str] = set()

        # 1. Select top performers
        top_episodes = sorted(
            [e for e in episodes if e.get("reward", 0) >= self.min_reward_for_top],
            key=lambda e: e.get("reward", 0),
            reverse=True,
        )

        for ep in top_episodes[:n_top]:
            if len(selected) >= self.max_episodes:
                break

            ep_id = str(ep.get("attempt_number", len(selected)))
            if ep_id not in selected_ids:
                selected.append(self._create_filtered(
                    ep, "top_performer", diversity_score=0.8
                ))
                selected_ids.add(ep_id)

        # 2. Select informative failures
        failure_episodes = sorted(
            [e for e in episodes if e.get("reward", 0) <= self.max_reward_for_failure],
            key=lambda e: e.get("reward", 0),  # Lowest first
        )

        for ep in failure_episodes[:n_failures]:
            if len(selected) >= self.max_episodes:
                break

            ep_id = str(ep.get("attempt_number", len(selected)))
            if ep_id not in selected_ids:
                # Prefer failures with clear action summaries
                informativeness = self._compute_failure_informativeness(ep)
                selected.append(self._create_filtered(
                    ep, "informative_failure", informativeness=informativeness
                ))
                selected_ids.add(ep_id)

        # 3. Select for diversity
        remaining = [
            e for e in episodes
            if str(e.get("attempt_number", "")) not in selected_ids
        ]

        if remaining and current_metrics:
            # Select episodes that are different from what's already selected
            diverse = self._select_diverse(
                remaining, selected, current_metrics, n_diverse
            )
            selected.extend(diverse)

        return selected

    def _create_filtered(
        self,
        episode: dict[str, Any],
        reason: str,
        diversity_score: float = 0.5,
        informativeness: float = 0.5,
    ) -> FilteredEpisode:
        """Create FilteredEpisode from episode dict."""
        return FilteredEpisode(
            episode_id=str(episode.get("id", episode.get("attempt_number", ""))),
            attempt_number=episode.get("attempt_number", 0),
            reward=episode.get("reward", 0.0),
            metrics=episode.get("metrics", {}),
            action_summary=episode.get("action_summary", ""),
            failures=episode.get("failures", []),
            inclusion_reason=reason,
            diversity_score=diversity_score,
            informativeness=informativeness,
        )

    def _compute_failure_informativeness(self, episode: dict[str, Any]) -> float:
        """
        Compute how informative a failure is.

        More informative failures:
        - Have clear action summaries (we know what was tried)
        - Have specific failures listed
        - Are not too old
        """
        score = 0.5

        # Has action summary
        if episode.get("action_summary"):
            score += 0.2

        # Has specific failures
        failures = episode.get("failures", [])
        if failures:
            score += min(0.2, len(failures) * 0.05)

        # Normalize
        return min(1.0, score)

    def _select_diverse(
        self,
        candidates: list[dict[str, Any]],
        already_selected: list[FilteredEpisode],
        current_metrics: dict[str, float],
        n: int,
    ) -> list[FilteredEpisode]:
        """
        Select diverse episodes that cover different approaches.

        Uses metric distance to find episodes that explored different strategies.
        """
        if not candidates:
            return []

        diverse = []
        selected_metrics = [ep.metrics for ep in already_selected]

        for ep in candidates:
            if len(diverse) >= n:
                break

            ep_metrics = ep.get("metrics", {})
            diversity = self._compute_diversity(ep_metrics, selected_metrics)

            if diversity > 0.3:  # Threshold for "different enough"
                diverse.append(self._create_filtered(
                    ep, "diversity", diversity_score=diversity
                ))
                selected_metrics.append(ep_metrics)

        return diverse

    def _compute_diversity(
        self,
        metrics: dict[str, float],
        existing_metrics: list[dict[str, float]],
    ) -> float:
        """
        Compute how different this episode is from existing selections.

        Uses average metric distance.
        """
        if not existing_metrics:
            return 1.0

        total_distance = 0.0
        for existing in existing_metrics:
            distance = 0.0
            count = 0
            for key in set(metrics.keys()) | set(existing.keys()):
                v1 = metrics.get(key, 0.0)
                v2 = existing.get(key, 0.0)
                distance += abs(v1 - v2)
                count += 1
            if count > 0:
                total_distance += distance / count

        return total_distance / len(existing_metrics) if existing_metrics else 1.0


def filter_episodes_for_context(
    episodes: list[dict[str, Any]],
    max_episodes: int = 7,
    current_metrics: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Convenience function to filter episodes.

    Returns episode dicts (not FilteredEpisode) for compatibility.
    """
    filter_obj = EpisodeFilter(max_episodes=max_episodes)
    filtered = filter_obj.filter(episodes, current_metrics)

    return [
        {
            "attempt_number": f.attempt_number,
            "reward": f.reward,
            "metrics": f.metrics,
            "action_summary": f.action_summary,
            "failures": f.failures,
            "inclusion_reason": f.inclusion_reason,
        }
        for f in filtered
    ]
