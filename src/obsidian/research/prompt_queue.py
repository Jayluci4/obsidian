"""
Prompt Pre-computation Queue.

Pre-computes candidate prompts for different evaluation outcomes
to enable faster iteration during the research loop.

Since Claude Code plugins cannot run background servers, this
uses file-based caching to store pre-computed prompts.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from obsidian.research.archive import SolutionArchive
    from obsidian.research.evolution import EvolutionController, OperationContext
    from obsidian.research.problem import ProblemSpec
    from obsidian.research.prompt_builder import ResearchPromptBuilder


@dataclass
class CachedPrompt:
    """A cached prompt for a specific scenario."""

    scenario: str
    operation_type: str
    prompt: str
    iteration: int
    timestamp: float


@dataclass
class PromptQueueConfig:
    """Configuration for prompt queue."""

    enabled: bool = True
    cache_dir: Path | None = None
    scenarios: list[str] | None = None  # Which scenarios to pre-compute


DEFAULT_SCENARIOS = [
    "failed",  # Solution failed correctness
    "low_score",  # Score < 0.4
    "medium_score",  # Score 0.4-0.7
    "high_score",  # Score > 0.7
    "known_algorithm",  # Known algorithm detected
]


class PromptQueue:
    """
    Pre-computes and caches prompts for different evaluation outcomes.

    Generates prompts for various scenarios ahead of time so they're
    instantly available after evaluation completes.
    """

    def __init__(
        self,
        problem: "ProblemSpec",
        archive: "SolutionArchive",
        evolution_controller: "EvolutionController",
        prompt_builder: "ResearchPromptBuilder",
        cache_dir: Path | None = None,
    ):
        self.problem = problem
        self.archive = archive
        self.evolution_controller = evolution_controller
        self.prompt_builder = prompt_builder
        self.cache_dir = cache_dir

        # In-memory cache
        self._cache: dict[str, CachedPrompt] = {}

        # Load from disk if available
        if cache_dir:
            self._load_cache()

    def _load_cache(self) -> None:
        """Load cached prompts from disk."""
        if not self.cache_dir:
            return

        cache_file = self.cache_dir / "prompt_cache.json"
        if not cache_file.exists():
            return

        try:
            with open(cache_file) as f:
                data = json.load(f)

            for scenario, cached_data in data.items():
                self._cache[scenario] = CachedPrompt(
                    scenario=cached_data["scenario"],
                    operation_type=cached_data["operation_type"],
                    prompt=cached_data["prompt"],
                    iteration=cached_data["iteration"],
                    timestamp=cached_data["timestamp"],
                )
        except (json.JSONDecodeError, KeyError):
            pass

    def _save_cache(self) -> None:
        """Save cached prompts to disk."""
        if not self.cache_dir:
            return

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.cache_dir / "prompt_cache.json"

        data = {}
        for scenario, cached in self._cache.items():
            data[scenario] = {
                "scenario": cached.scenario,
                "operation_type": cached.operation_type,
                "prompt": cached.prompt,
                "iteration": cached.iteration,
                "timestamp": cached.timestamp,
            }

        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)

    def precompute_prompts(
        self,
        current_iteration: int,
        scenarios: list[str] | None = None,
    ) -> dict[str, CachedPrompt]:
        """
        Pre-compute prompts for different evaluation scenarios.

        Args:
            current_iteration: Current iteration number
            scenarios: Which scenarios to compute (uses defaults if None)

        Returns:
            Dict of scenario -> CachedPrompt
        """
        if scenarios is None:
            scenarios = DEFAULT_SCENARIOS

        computed = {}

        for scenario in scenarios:
            operation = self._get_operation_for_scenario(scenario)
            if operation:
                prompt = self.prompt_builder.build_iteration_prompt(
                    operation=operation,
                    archive=self.archive,
                    iteration=current_iteration + 1,
                )

                cached = CachedPrompt(
                    scenario=scenario,
                    operation_type=operation.operation_type.value,
                    prompt=prompt,
                    iteration=current_iteration,
                    timestamp=time.time(),
                )

                self._cache[scenario] = cached
                computed[scenario] = cached

        self._save_cache()
        return computed

    def _get_operation_for_scenario(
        self,
        scenario: str,
    ) -> "OperationContext | None":
        """Get appropriate operation for a scenario."""
        from obsidian.research.evolution import OperationType

        # Select operation based on scenario
        if scenario == "failed":
            # Mutation to fix issues
            return self.evolution_controller.mutate_op.get_context(
                self.archive, self.problem
            )

        elif scenario == "low_score":
            # Explore to try different approach
            return self.evolution_controller.explore_op.get_context(
                self.archive, self.problem
            )

        elif scenario == "medium_score":
            # Adaptive selection based on archive state
            return self.evolution_controller.select_operation(
                self.archive, self.problem, iteration=0
            )

        elif scenario == "high_score":
            # Exploit to refine
            return self.evolution_controller.exploit_op.get_context(
                self.archive, self.problem
            )

        elif scenario == "known_algorithm":
            # Explore to find novel approach
            return self.evolution_controller.explore_op.get_context(
                self.archive, self.problem
            )

        return None

    def get_prompt_for_outcome(
        self,
        score: float,
        passed: bool,
        is_known_algorithm: bool = False,
        current_iteration: int = 0,
    ) -> str | None:
        """
        Get pre-computed prompt based on evaluation outcome.

        Args:
            score: Evaluation score
            passed: Whether correctness passed
            is_known_algorithm: Whether known algorithm was detected
            current_iteration: Current iteration for cache validation

        Returns:
            Cached prompt if available, None otherwise
        """
        # Determine scenario
        if not passed:
            scenario = "failed"
        elif is_known_algorithm:
            scenario = "known_algorithm"
        elif score < 0.4:
            scenario = "low_score"
        elif score < 0.7:
            scenario = "medium_score"
        else:
            scenario = "high_score"

        # Get cached prompt
        cached = self._cache.get(scenario)
        if cached:
            # Check if cache is still valid (not too old)
            age = current_iteration - cached.iteration
            if age <= 1:  # Cache valid for 1 iteration
                return cached.prompt

        return None

    def get_cached_scenarios(self) -> list[str]:
        """Get list of scenarios with cached prompts."""
        return list(self._cache.keys())

    def clear_cache(self) -> None:
        """Clear all cached prompts."""
        self._cache.clear()
        if self.cache_dir:
            cache_file = self.cache_dir / "prompt_cache.json"
            if cache_file.exists():
                cache_file.unlink()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "cached_scenarios": len(self._cache),
            "scenarios": list(self._cache.keys()),
            "cache_ages": {
                s: c.iteration for s, c in self._cache.items()
            },
        }


def classify_evaluation_scenario(
    score: float,
    passed: bool,
    is_known_algorithm: bool = False,
) -> str:
    """
    Classify evaluation outcome into a scenario.

    Args:
        score: Evaluation score
        passed: Whether correctness passed
        is_known_algorithm: Whether known algorithm detected

    Returns:
        Scenario name
    """
    if not passed:
        return "failed"
    if is_known_algorithm:
        return "known_algorithm"
    if score < 0.4:
        return "low_score"
    if score < 0.7:
        return "medium_score"
    return "high_score"
