"""Multi-armed bandit algorithms for adaptive selection.

Implements UCB1, Thompson Sampling, and Epsilon-Greedy for:
- Operation selection (mutate, crossover, explore, exploit)
- Prompt selection within operations
"""

import json
import math
import random
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class BanditAlgorithm(Enum):
    """Available bandit algorithms."""

    UCB1 = "ucb1"
    THOMPSON = "thompson"
    EPSILON_GREEDY = "epsilon_greedy"


@dataclass
class ArmStats:
    """Statistics for a single arm (option)."""

    name: str
    trials: int = 0
    total_reward: float = 0.0
    successes: int = 0  # For Thompson sampling (beta distribution)

    @property
    def avg_reward(self) -> float:
        """Average reward for this arm."""
        if self.trials == 0:
            return 0.0
        return self.total_reward / self.trials

    @property
    def success_rate(self) -> float:
        """Success rate for Thompson sampling."""
        if self.trials == 0:
            return 0.5
        return self.successes / self.trials


@dataclass
class BanditConfig:
    """Configuration for bandit algorithm."""

    algorithm: BanditAlgorithm = BanditAlgorithm.UCB1
    exploration_factor: float = 1.0  # UCB1 exploration constant
    epsilon: float = 0.1  # Epsilon-greedy exploration rate
    min_trials_per_arm: int = 2  # Minimum trials before exploitation


class MultiArmedBandit:
    """
    Multi-armed bandit for adaptive selection.

    Used for:
    - Selecting which operation (mutate/crossover/explore/exploit) to use
    - Selecting which prompt to use within an operation
    """

    def __init__(
        self,
        arms: list[str],
        config: BanditConfig | None = None,
        db_path: Path | None = None,
        table_name: str = "bandit_stats",
    ):
        self.arms = arms
        self.config = config or BanditConfig()
        self.db_path = db_path
        self.table_name = table_name

        # Initialize stats
        self._stats: dict[str, ArmStats] = {arm: ArmStats(name=arm) for arm in arms}

        # Load from database if available
        if db_path:
            self._init_db()
            self._load_stats()

    def _init_db(self) -> None:
        """Initialize database table."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                arm TEXT PRIMARY KEY,
                trials INTEGER DEFAULT 0,
                total_reward REAL DEFAULT 0.0,
                successes INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _load_stats(self) -> None:
        """Load stats from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(f"SELECT arm, trials, total_reward, successes FROM {self.table_name}")
        for row in cursor:
            arm, trials, total_reward, successes = row
            if arm in self._stats:
                self._stats[arm] = ArmStats(
                    name=arm,
                    trials=trials,
                    total_reward=total_reward,
                    successes=successes,
                )
        conn.close()

    def _save_stats(self) -> None:
        """Save stats to database."""
        if not self.db_path:
            return

        conn = sqlite3.connect(self.db_path)
        for arm, stats in self._stats.items():
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.table_name} (arm, trials, total_reward, successes)
                VALUES (?, ?, ?, ?)
            """,
                (arm, stats.trials, stats.total_reward, stats.successes),
            )
        conn.commit()
        conn.close()

    def select(self) -> str:
        """Select an arm using the configured algorithm."""
        if self.config.algorithm == BanditAlgorithm.UCB1:
            return self._select_ucb1()
        elif self.config.algorithm == BanditAlgorithm.THOMPSON:
            return self._select_thompson()
        else:
            return self._select_epsilon_greedy()

    def _select_ucb1(self) -> str:
        """
        Upper Confidence Bound (UCB1) selection.

        UCB score = average_reward + c * sqrt(ln(total_trials) / arm_trials)

        Balances exploitation (high average) with exploration (uncertainty).
        """
        total_trials = sum(s.trials for s in self._stats.values())

        # First, try each arm at least min_trials times
        for arm, stats in self._stats.items():
            if stats.trials < self.config.min_trials_per_arm:
                return arm

        # Compute UCB scores
        ucb_scores = {}
        for arm, stats in self._stats.items():
            if stats.trials == 0:
                ucb_scores[arm] = float("inf")
            else:
                exploitation = stats.avg_reward
                exploration = self.config.exploration_factor * math.sqrt(
                    2 * math.log(total_trials) / stats.trials
                )
                ucb_scores[arm] = exploitation + exploration

        return max(ucb_scores, key=ucb_scores.get)

    def _select_thompson(self) -> str:
        """
        Thompson Sampling selection.

        Samples from Beta distribution for each arm and selects highest.
        Beta(successes + 1, failures + 1)
        """
        samples = {}
        for arm, stats in self._stats.items():
            alpha = stats.successes + 1
            beta = (stats.trials - stats.successes) + 1
            samples[arm] = random.betavariate(alpha, beta)

        return max(samples, key=samples.get)

    def _select_epsilon_greedy(self) -> str:
        """
        Epsilon-Greedy selection.

        With probability epsilon, explore randomly.
        Otherwise, exploit best known arm.
        """
        if random.random() < self.config.epsilon:
            return random.choice(self.arms)

        # Select arm with highest average reward
        return max(self._stats.values(), key=lambda s: s.avg_reward).name

    def update(self, arm: str, reward: float, success: bool = None) -> None:
        """
        Update arm statistics after observing reward.

        Args:
            arm: The arm that was pulled
            reward: The observed reward (typically improvement in score)
            success: Whether this was a success (for Thompson sampling)
                    If None, success is determined by reward > 0
        """
        if arm not in self._stats:
            return

        stats = self._stats[arm]
        stats.trials += 1
        stats.total_reward += reward

        if success is None:
            success = reward > 0
        if success:
            stats.successes += 1

        self._save_stats()

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all arms."""
        return {
            arm: {
                "trials": stats.trials,
                "total_reward": stats.total_reward,
                "avg_reward": stats.avg_reward,
                "successes": stats.successes,
                "success_rate": stats.success_rate,
            }
            for arm, stats in self._stats.items()
        }

    def get_best_arm(self) -> str:
        """Get the arm with highest average reward."""
        return max(self._stats.values(), key=lambda s: s.avg_reward).name

    def reset(self) -> None:
        """Reset all statistics."""
        for arm in self._stats:
            self._stats[arm] = ArmStats(name=arm)
        self._save_stats()


class ContextualBandit:
    """
    Contextual bandit for context-dependent selection.

    Uses context features to make decisions. Implements simplified
    LinUCB-style selection without matrix operations.
    """

    def __init__(
        self,
        arms: list[str],
        db_path: Path | None = None,
        epsilon: float = 0.1,
        context_bins: int = 10,
    ):
        self.arms = arms
        self.db_path = db_path
        self.epsilon = epsilon
        self.context_bins = context_bins

        # Stats per arm per context bin
        # context_key -> arm -> ArmStats
        self._stats: dict[str, dict[str, ArmStats]] = {}

        if db_path:
            self._init_db()
            self._load_stats()

    def _init_db(self) -> None:
        """Initialize database table."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contextual_bandit_stats (
                context_key TEXT,
                arm TEXT,
                trials INTEGER DEFAULT 0,
                total_reward REAL DEFAULT 0.0,
                PRIMARY KEY (context_key, arm)
            )
        """)
        conn.commit()
        conn.close()

    def _load_stats(self) -> None:
        """Load stats from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT context_key, arm, trials, total_reward FROM contextual_bandit_stats")
        for row in cursor:
            context_key, arm, trials, total_reward = row
            if context_key not in self._stats:
                self._stats[context_key] = {}
            self._stats[context_key][arm] = ArmStats(
                name=arm,
                trials=trials,
                total_reward=total_reward,
            )
        conn.close()

    def _save_stats(self, context_key: str) -> None:
        """Save stats for a context to database."""
        if not self.db_path:
            return

        conn = sqlite3.connect(self.db_path)
        for arm, stats in self._stats.get(context_key, {}).items():
            conn.execute(
                """
                INSERT OR REPLACE INTO contextual_bandit_stats
                (context_key, arm, trials, total_reward)
                VALUES (?, ?, ?, ?)
            """,
                (context_key, arm, stats.trials, stats.total_reward),
            )
        conn.commit()
        conn.close()

    def _discretize_context(self, context: list[float]) -> str:
        """Convert continuous context to discrete key."""
        # Simple binning: each feature into N bins
        binned = []
        for val in context:
            # Assume features normalized to [0, 1]
            bin_idx = min(int(val * self.context_bins), self.context_bins - 1)
            binned.append(str(bin_idx))
        return "|".join(binned)

    def select(self, context: list[float]) -> str:
        """
        Select arm given context.

        Uses epsilon-greedy with context-specific statistics.
        """
        context_key = self._discretize_context(context)

        # Initialize context if new
        if context_key not in self._stats:
            self._stats[context_key] = {arm: ArmStats(name=arm) for arm in self.arms}

        # Epsilon-greedy with context
        if random.random() < self.epsilon:
            return random.choice(self.arms)

        # Select best arm for this context
        stats = self._stats[context_key]
        return max(stats.values(), key=lambda s: s.avg_reward if s.trials > 0 else 0.5).name

    def update(self, context: list[float], arm: str, reward: float) -> None:
        """Update statistics for context-arm pair."""
        context_key = self._discretize_context(context)

        if context_key not in self._stats:
            self._stats[context_key] = {a: ArmStats(name=a) for a in self.arms}

        if arm in self._stats[context_key]:
            stats = self._stats[context_key][arm]
            stats.trials += 1
            stats.total_reward += reward

        self._save_stats(context_key)

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get all statistics."""
        result = {}
        for context_key, arms in self._stats.items():
            result[context_key] = {
                arm: {"trials": s.trials, "avg_reward": s.avg_reward} for arm, s in arms.items()
            }
        return result
