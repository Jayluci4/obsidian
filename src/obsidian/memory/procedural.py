"""Procedural memory for tracking strategy effectiveness."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .store import MemoryStore


@dataclass
class StrategyRecord:
    """Record of strategy effectiveness."""

    name: str
    description: str
    total_reward_delta: float
    usage_count: int
    success_count: int
    updated_at: str = ""

    @property
    def success_rate(self) -> float:
        """Compute success rate."""
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    @property
    def avg_delta(self) -> float:
        """Compute average reward delta per use."""
        if self.usage_count == 0:
            return 0.0
        return self.total_reward_delta / self.usage_count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "total_reward_delta": self.total_reward_delta,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "avg_delta": self.avg_delta,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyRecord":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            total_reward_delta=data.get("total_reward_delta", 0.0),
            usage_count=data.get("usage_count", 0),
            success_count=data.get("success_count", 0),
            updated_at=data.get("updated_at", ""),
        )


class ProceduralMemory:
    """
    Procedural memory for tracking what strategies work.

    Stores:
    - Strategy usage counts
    - Cumulative reward deltas
    - Success rates

    Used to inform strategy selection over time.
    """

    def __init__(self, store: MemoryStore):
        self.store = store

    def record_outcome(
        self,
        strategy_name: str,
        reward_before: float,
        reward_after: float,
        description: str = "",
    ) -> StrategyRecord:
        """
        Record the outcome of using a strategy.

        Args:
            strategy_name: Name of the strategy used
            reward_before: Reward before applying strategy
            reward_after: Reward after applying strategy
            description: Optional description of strategy

        Returns:
            Updated strategy record
        """
        delta = reward_after - reward_before
        success = delta > 0.02  # Consider >2% improvement as success

        # Upsert strategy record
        self.store.execute(
            """
            INSERT INTO procedural_strategies (name, description, total_reward_delta, usage_count, success_count, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = COALESCE(NULLIF(?, ''), description),
                total_reward_delta = total_reward_delta + ?,
                usage_count = usage_count + 1,
                success_count = success_count + ?,
                updated_at = ?
            """,
            (
                strategy_name,
                description,
                delta,
                1 if success else 0,
                datetime.utcnow().isoformat(),
                description,
                delta,
                1 if success else 0,
                datetime.utcnow().isoformat(),
            ),
        )

        return self.get_strategy(strategy_name)

    def get_strategy(self, name: str) -> StrategyRecord | None:
        """Get a specific strategy record."""
        row = self.store.execute_one(
            "SELECT * FROM procedural_strategies WHERE name = ?",
            (name,),
        )
        return StrategyRecord.from_dict(row) if row else None

    def get_all_strategies(self) -> list[StrategyRecord]:
        """Get all strategy records."""
        rows = self.store.execute(
            "SELECT * FROM procedural_strategies ORDER BY total_reward_delta DESC"
        )
        return [StrategyRecord.from_dict(row) for row in rows]

    def get_best_strategies(self, limit: int = 5) -> list[StrategyRecord]:
        """Get strategies ranked by effectiveness."""
        rows = self.store.execute(
            """
            SELECT * FROM procedural_strategies
            WHERE usage_count >= 2
            ORDER BY (total_reward_delta / usage_count) DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [StrategyRecord.from_dict(row) for row in rows]

    def get_most_used(self, limit: int = 5) -> list[StrategyRecord]:
        """Get most frequently used strategies."""
        rows = self.store.execute(
            """
            SELECT * FROM procedural_strategies
            ORDER BY usage_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [StrategyRecord.from_dict(row) for row in rows]

    def get_recommended_strategy(
        self,
        exclude: list[str] | None = None,
        min_uses: int = 2,
    ) -> StrategyRecord | None:
        """
        Get recommended strategy based on historical performance.

        Args:
            exclude: Strategy names to exclude
            min_uses: Minimum usage count to consider

        Returns:
            Best performing strategy or None
        """
        exclude = exclude or []

        # Build query with exclusions
        if exclude:
            placeholders = ", ".join(["?"] * len(exclude))
            query = f"""
                SELECT * FROM procedural_strategies
                WHERE usage_count >= ? AND name NOT IN ({placeholders})
                ORDER BY (total_reward_delta / usage_count) DESC
                LIMIT 1
            """
            params = (min_uses, *exclude)
        else:
            query = """
                SELECT * FROM procedural_strategies
                WHERE usage_count >= ?
                ORDER BY (total_reward_delta / usage_count) DESC
                LIMIT 1
            """
            params = (min_uses,)

        row = self.store.execute_one(query, params)
        return StrategyRecord.from_dict(row) if row else None

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics across all strategies."""
        rows = self.store.execute(
            """
            SELECT
                COUNT(*) as total_strategies,
                SUM(usage_count) as total_uses,
                SUM(success_count) as total_successes,
                SUM(total_reward_delta) as total_delta,
                AVG(total_reward_delta / NULLIF(usage_count, 0)) as avg_delta_per_use
            FROM procedural_strategies
            """
        )

        if not rows:
            return {
                "total_strategies": 0,
                "total_uses": 0,
                "total_successes": 0,
                "overall_success_rate": 0.0,
                "total_delta": 0.0,
                "avg_delta_per_use": 0.0,
            }

        row = rows[0]
        total_uses = row.get("total_uses") or 0
        total_successes = row.get("total_successes") or 0

        return {
            "total_strategies": row.get("total_strategies") or 0,
            "total_uses": total_uses,
            "total_successes": total_successes,
            "overall_success_rate": total_successes / total_uses if total_uses > 0 else 0.0,
            "total_delta": row.get("total_delta") or 0.0,
            "avg_delta_per_use": row.get("avg_delta_per_use") or 0.0,
        }

    def format_for_context(self, max_strategies: int = 5) -> str:
        """Format strategy knowledge for context injection."""
        strategies = self.get_best_strategies(max_strategies)

        if not strategies:
            return ""

        lines = ["<strategy_knowledge>"]
        for s in strategies:
            lines.append(
                f"<strategy name=\"{s.name}\" success_rate=\"{s.success_rate:.0%}\" "
                f"avg_delta=\"{s.avg_delta:+.3f}\" uses=\"{s.usage_count}\">"
            )
            if s.description:
                lines.append(f"  {s.description}")
            lines.append("</strategy>")
        lines.append("</strategy_knowledge>")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all strategy records."""
        self.store.delete("procedural_strategies", "1 = 1")
