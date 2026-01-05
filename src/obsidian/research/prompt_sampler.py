"""
Strategic Prompt Sampler for Research Mode.

Learns which prompt variations work best in different contexts
using contextual bandits (AlphaEvolve-style prompt sampling).

Features:
- Epsilon-greedy selection with context
- Context features from archive state and parent solutions
- Persistence of prompt statistics to SQLite
"""

import json
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from obsidian.research.archive import Solution, SolutionArchive
    from obsidian.research.evolution import OperationType


# Prompt pools by operation type
MUTATION_PROMPTS = {
    "light": [
        "light_efficiency",
        "light_edge_cases",
        "light_simplify",
        "light_error_handling",
    ],
    "medium": [
        "medium_optimize_core",
        "medium_refactor_design",
        "medium_enhance_technique",
        "medium_generalize",
    ],
    "heavy": [
        "heavy_restructure",
        "heavy_replace_component",
        "heavy_combine_strategies",
        "heavy_scalability",
    ],
}

CROSSOVER_PROMPTS = [
    "crossover_hybrid",
    "crossover_algo_from_a_opt_from_b",
    "crossover_merge_techniques",
    "crossover_leverage_strengths",
    "crossover_avoid_weaknesses",
]

MULTI_CROSSOVER_PROMPTS = [
    "multi_crossover_abc_synthesis",
    "multi_crossover_algo_opt_edge",
    "multi_crossover_best_of_three",
    "multi_crossover_foundation_enhance_polish",
    "multi_crossover_structure_insight_efficiency",
]

EXPLORE_PROMPTS = [
    "explore_different_approach",
    "explore_unconventional",
    "explore_paradigm_shift",
    "explore_cross_domain",
    "explore_simplicity_focus",
    "explore_trade_off",
]

EXPLOIT_PROMPTS = [
    "exploit_optimize_further",
    "exploit_micro_optimize",
    "exploit_more_efficient",
    "exploit_polish",
    "exploit_push_limits",
]


@dataclass
class PromptOutcome:
    """Record of a prompt outcome."""

    prompt_id: str
    context: list[float]
    reward: float
    timestamp: float


@dataclass
class PromptStats:
    """Statistics for a single prompt."""

    prompt_id: str
    trials: int = 0
    total_reward: float = 0.0
    context_sum: list[float] | None = None

    @property
    def avg_reward(self) -> float:
        if self.trials == 0:
            return 0.0
        return self.total_reward / self.trials


class PromptSampler:
    """
    Contextual bandit for strategic prompt selection.

    Uses context features to learn which prompts work best
    in different situations (archive state, parent characteristics).
    """

    def __init__(
        self,
        db_path: Path | None = None,
        epsilon: float = 0.1,
        context_bins: int = 5,
    ):
        self.db_path = db_path
        self.epsilon = epsilon
        self.context_bins = context_bins

        # Prompt statistics
        self._stats: dict[str, PromptStats] = {}

        # Recent outcomes for learning
        self._recent_outcomes: list[PromptOutcome] = []
        self._max_recent = 1000

        # Track last prompt for reward attribution
        self._last_prompt_id: str | None = None
        self._last_context: list[float] | None = None

        if db_path:
            self._init_db()
            self._load_stats()

    def _init_db(self) -> None:
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_stats (
                prompt_id TEXT PRIMARY KEY,
                trials INTEGER DEFAULT 0,
                total_reward REAL DEFAULT 0.0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id TEXT,
                context TEXT,
                reward REAL,
                timestamp REAL
            )
        """)
        conn.commit()
        conn.close()

    def _load_stats(self) -> None:
        """Load statistics from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT prompt_id, trials, total_reward FROM prompt_stats")
        for row in cursor:
            self._stats[row[0]] = PromptStats(
                prompt_id=row[0],
                trials=row[1],
                total_reward=row[2],
            )
        conn.close()

    def _save_stats(self) -> None:
        """Save statistics to database."""
        if not self.db_path:
            return

        conn = sqlite3.connect(self.db_path)
        for prompt_id, stats in self._stats.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO prompt_stats (prompt_id, trials, total_reward)
                VALUES (?, ?, ?)
            """,
                (prompt_id, stats.trials, stats.total_reward),
            )
        conn.commit()
        conn.close()

    def get_context_features(
        self,
        archive: "SolutionArchive",
        parent_solutions: list["Solution"] | None = None,
    ) -> list[float]:
        """
        Extract context features for bandit.

        Features:
        - Archive size (normalized)
        - Archive coverage
        - Best score
        - Average score
        - Number of parents
        - Parent diversity (if multiple parents)
        """
        stats = archive.get_stats()

        features = [
            min(1.0, stats["total_solutions"] / 100),  # Normalized archive size
            stats.get("coverage", 0),  # Niche coverage
            stats.get("best_score", 0),  # Best score
            stats.get("avg_score", 0),  # Average score
        ]

        if parent_solutions:
            features.append(min(1.0, len(parent_solutions) / 3))  # Num parents

            # Parent diversity (std dev of scores)
            if len(parent_solutions) > 1:
                scores = [p.score for p in parent_solutions]
                mean = sum(scores) / len(scores)
                variance = sum((s - mean) ** 2 for s in scores) / len(scores)
                features.append(min(1.0, variance**0.5))
            else:
                features.append(0.0)
        else:
            features.extend([0.0, 0.0])

        return features

    def select_prompt(
        self,
        operation_type: "OperationType",
        archive: "SolutionArchive",
        parent_solutions: list["Solution"] | None = None,
        mutation_strength: str = "medium",
    ) -> str:
        """
        Select prompt using epsilon-greedy with context.

        Args:
            operation_type: Type of evolutionary operation
            archive: Current solution archive
            parent_solutions: Parent solutions (if any)
            mutation_strength: For mutation operations

        Returns:
            Selected prompt ID
        """
        from obsidian.research.evolution import OperationType

        # Get candidate prompts for this operation
        if operation_type == OperationType.MUTATE:
            prompts = MUTATION_PROMPTS.get(mutation_strength, MUTATION_PROMPTS["medium"])
        elif operation_type == OperationType.CROSSOVER:
            if parent_solutions and len(parent_solutions) >= 3:
                prompts = MULTI_CROSSOVER_PROMPTS
            else:
                prompts = CROSSOVER_PROMPTS
        elif operation_type == OperationType.EXPLORE:
            prompts = EXPLORE_PROMPTS
        elif operation_type == OperationType.EXPLOIT:
            prompts = EXPLOIT_PROMPTS
        else:
            prompts = EXPLORE_PROMPTS

        # Get context
        context = self.get_context_features(archive, parent_solutions)

        # Epsilon-greedy selection
        if random.random() < self.epsilon:
            selected = random.choice(prompts)
        else:
            # Select best prompt based on historical performance
            best_prompt = None
            best_score = -float("inf")

            for prompt_id in prompts:
                score = self._estimate_reward(prompt_id, context)
                if score > best_score:
                    best_score = score
                    best_prompt = prompt_id

            selected = best_prompt or random.choice(prompts)

        # Track for reward attribution
        self._last_prompt_id = selected
        self._last_context = context

        return selected

    def _estimate_reward(self, prompt_id: str, context: list[float]) -> float:
        """
        Estimate expected reward for prompt in context.

        Uses simple average reward with exploration bonus for
        less-tried prompts.
        """
        if prompt_id not in self._stats:
            return 0.5  # Prior for unknown prompts

        stats = self._stats[prompt_id]

        if stats.trials == 0:
            return 0.5

        # Average reward with uncertainty bonus
        avg = stats.avg_reward
        uncertainty = 1.0 / (stats.trials + 1) ** 0.5

        return avg + 0.1 * uncertainty

    def record_outcome(self, reward: float) -> None:
        """
        Record outcome of last prompt selection.

        Args:
            reward: Observed reward (typically score improvement)
        """
        if self._last_prompt_id is None:
            return

        prompt_id = self._last_prompt_id
        context = self._last_context or []

        # Update statistics
        if prompt_id not in self._stats:
            self._stats[prompt_id] = PromptStats(prompt_id=prompt_id)

        stats = self._stats[prompt_id]
        stats.trials += 1
        stats.total_reward += reward

        # Save outcome
        outcome = PromptOutcome(
            prompt_id=prompt_id,
            context=context,
            reward=reward,
            timestamp=time.time(),
        )
        self._recent_outcomes.append(outcome)

        # Trim recent outcomes
        if len(self._recent_outcomes) > self._max_recent:
            self._recent_outcomes = self._recent_outcomes[-self._max_recent :]

        # Persist
        self._save_stats()
        self._save_outcome(outcome)

        # Reset tracking
        self._last_prompt_id = None
        self._last_context = None

    def _save_outcome(self, outcome: PromptOutcome) -> None:
        """Save outcome to database."""
        if not self.db_path:
            return

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO prompt_outcomes (prompt_id, context, reward, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (
                outcome.prompt_id,
                json.dumps(outcome.context),
                outcome.reward,
                outcome.timestamp,
            ),
        )
        conn.commit()
        conn.close()

    def get_stats(self) -> dict[str, Any]:
        """Get statistics for all prompts."""
        return {
            prompt_id: {
                "trials": stats.trials,
                "avg_reward": stats.avg_reward,
                "total_reward": stats.total_reward,
            }
            for prompt_id, stats in self._stats.items()
        }

    def get_best_prompts(self, n: int = 5) -> list[tuple[str, float]]:
        """Get top N prompts by average reward."""
        sorted_prompts = sorted(
            [(p, s.avg_reward) for p, s in self._stats.items() if s.trials > 0],
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_prompts[:n]

    def reset(self) -> None:
        """Reset all statistics."""
        self._stats.clear()
        self._recent_outcomes.clear()
        self._last_prompt_id = None
        self._last_context = None
        self._save_stats()


def get_prompt_text(prompt_id: str) -> str:
    """
    Get actual prompt text from prompt ID.

    Maps prompt IDs to natural language instructions.
    """
    prompt_texts = {
        # Mutation prompts
        "light_efficiency": "Make a small improvement to the efficiency of this solution",
        "light_edge_cases": "Fix any edge cases that might be missing",
        "light_simplify": "Simplify the code without changing the approach",
        "light_error_handling": "Add better error handling",
        "medium_optimize_core": "Optimize the core algorithm for better performance",
        "medium_refactor_design": "Refactor to improve the design while keeping the approach",
        "medium_enhance_technique": "Enhance the solution with a complementary technique",
        "medium_generalize": "Generalize the solution to handle more cases",
        "heavy_restructure": "Significantly restructure the implementation",
        "heavy_replace_component": "Replace a major component with a better alternative",
        "heavy_combine_strategies": "Combine multiple optimization strategies",
        "heavy_scalability": "Rewrite with a focus on scalability",
        # Crossover prompts
        "crossover_hybrid": "Combine the best aspects of both solutions into a hybrid approach",
        "crossover_algo_from_a_opt_from_b": "Use the core algorithm from Solution A with the optimization from Solution B",
        "crossover_merge_techniques": "Merge the techniques: take the structure from one and the logic from the other",
        "crossover_leverage_strengths": "Create a new solution that leverages the strengths of both parents",
        "crossover_avoid_weaknesses": "Synthesize a solution that avoids the weaknesses of both approaches",
        # Multi-parent crossover
        "multi_crossover_abc_synthesis": "Combine: core algorithm from A, optimizations from B, edge-case handling from C",
        "multi_crossover_algo_opt_edge": "Synthesize: A's approach + B's data structures + C's performance techniques",
        "multi_crossover_best_of_three": "Create hybrid: best algorithmic idea from A, best optimization from B, best validation from C",
        "multi_crossover_foundation_enhance_polish": "Merge three approaches: take the foundation from A, enhance with B's technique, polish with C's refinements",
        "multi_crossover_structure_insight_efficiency": "Build on all three: use A's structure as base, incorporate B's key insight, apply C's efficiency tricks",
        # Explore prompts
        "explore_different_approach": "Try a completely different algorithmic approach",
        "explore_unconventional": "Explore an unconventional solution that others might not consider",
        "explore_paradigm_shift": "Use a different paradigm (e.g., iterative vs recursive, greedy vs dynamic)",
        "explore_cross_domain": "Apply techniques from a different domain to this problem",
        "explore_simplicity_focus": "Start fresh with a focus on simplicity over sophistication",
        "explore_trade_off": "Design a solution optimized for a different trade-off",
        # Exploit prompts
        "exploit_optimize_further": "This is our best solution. Optimize it further without changing the core approach",
        "exploit_micro_optimize": "Fine-tune this solution: focus on micro-optimizations",
        "exploit_more_efficient": "The approach is working. Make it more efficient",
        "exploit_polish": "Polish this solution: improve constants, reduce overhead",
        "exploit_push_limits": "This solution is promising. Push it to its limits",
    }

    return prompt_texts.get(prompt_id, prompt_id)
