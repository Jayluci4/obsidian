"""Episodic memory for storing and retrieving attempt histories."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .store import MemoryStore


@dataclass
class Episode:
    """Record of a single attempt in the learning loop."""

    id: str
    session_id: str
    attempt_number: int
    timestamp: str
    reward: float
    metrics: dict[str, float]
    action_summary: str = ""
    failures: list[str] = field(default_factory=list)
    strategy_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "attempt_number": self.attempt_number,
            "timestamp": self.timestamp,
            "reward": self.reward,
            "metrics": self.metrics,
            "action_summary": self.action_summary,
            "failures": self.failures,
            "strategy_used": self.strategy_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        """Create from dictionary."""
        metrics = data.get("metrics", {})
        if isinstance(metrics, str):
            metrics = json.loads(metrics)

        failures = data.get("failures", [])
        if isinstance(failures, str):
            failures = json.loads(failures) if failures else []

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            session_id=data.get("session_id", ""),
            attempt_number=data.get("attempt_number", 0),
            timestamp=data.get("timestamp", ""),
            reward=data.get("reward", 0.0),
            metrics=metrics,
            action_summary=data.get("action_summary", ""),
            failures=failures,
            strategy_used=data.get("strategy_used"),
        )


@dataclass
class SessionState:
    """State for a single session."""

    session_id: str
    attempt_count: int = 0
    reward_history: list[float] = field(default_factory=list)
    best_reward: float = 0.0
    current_strategy: str | None = None
    started_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "attempt_count": self.attempt_count,
            "reward_history": self.reward_history,
            "best_reward": self.best_reward,
            "current_strategy": self.current_strategy,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        """Create from dictionary."""
        reward_history = data.get("reward_history", [])
        if isinstance(reward_history, str):
            reward_history = json.loads(reward_history)

        return cls(
            session_id=data.get("session_id", ""),
            attempt_count=data.get("attempt_count", 0),
            reward_history=reward_history,
            best_reward=data.get("best_reward", 0.0),
            current_strategy=data.get("current_strategy"),
            started_at=data.get("started_at", ""),
        )


class EpisodicMemory:
    """
    Manages episodic memory for the learning loop.

    Stores episodes (attempts) and session state in SQLite.
    Provides retrieval methods for ICRL context building.
    """

    def __init__(self, store: MemoryStore):
        self.store = store

    def add_episode(
        self,
        session_id: str,
        attempt_number: int,
        reward: float,
        metrics: dict[str, float],
        action_summary: str = "",
        failures: list[str] | None = None,
        strategy_used: str | None = None,
    ) -> Episode:
        """Add a new episode to memory."""
        episode = Episode(
            id=str(uuid.uuid4()),
            session_id=session_id,
            attempt_number=attempt_number,
            timestamp=datetime.utcnow().isoformat(),
            reward=reward,
            metrics=metrics,
            action_summary=action_summary,
            failures=failures or [],
            strategy_used=strategy_used,
        )

        self.store.insert("episodes", episode.to_dict())
        return episode

    def get_episodes(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[Episode]:
        """Get all episodes for a session, ordered by attempt number."""
        query = """
            SELECT * FROM episodes
            WHERE session_id = ?
            ORDER BY attempt_number ASC
        """
        if limit:
            query += f" LIMIT {limit}"

        rows = self.store.execute(query, (session_id,))
        return [Episode.from_dict(row) for row in rows]

    def get_top_k_episodes(
        self,
        session_id: str,
        k: int = 5,
        include_failures: bool = True,
    ) -> list[Episode]:
        """
        Get top K episodes by reward for ICRL context.

        Optionally includes 1-2 low-reward episodes to avoid bad patterns.
        """
        # Get top K by reward
        query = """
            SELECT * FROM episodes
            WHERE session_id = ?
            ORDER BY reward DESC
            LIMIT ?
        """
        rows = self.store.execute(query, (session_id, k))
        top_episodes = [Episode.from_dict(row) for row in rows]

        if include_failures and len(top_episodes) >= 2:
            # Also get 1-2 low-reward episodes as negative examples
            fail_query = """
                SELECT * FROM episodes
                WHERE session_id = ? AND reward < 0.5
                ORDER BY reward ASC
                LIMIT 2
            """
            fail_rows = self.store.execute(fail_query, (session_id,))
            fail_episodes = [Episode.from_dict(row) for row in fail_rows]

            # Combine, avoiding duplicates
            seen_ids = {e.id for e in top_episodes}
            for ep in fail_episodes:
                if ep.id not in seen_ids:
                    top_episodes.append(ep)

        return top_episodes

    def get_best_episode(self, session_id: str) -> Episode | None:
        """Get the episode with highest reward."""
        query = """
            SELECT * FROM episodes
            WHERE session_id = ?
            ORDER BY reward DESC
            LIMIT 1
        """
        row = self.store.execute_one(query, (session_id,))
        return Episode.from_dict(row) if row else None

    def get_recent_episodes(
        self,
        session_id: str,
        n: int = 5,
    ) -> list[Episode]:
        """Get N most recent episodes."""
        query = """
            SELECT * FROM episodes
            WHERE session_id = ?
            ORDER BY attempt_number DESC
            LIMIT ?
        """
        rows = self.store.execute(query, (session_id, n))
        return [Episode.from_dict(row) for row in rows]

    def get_session_state(self, session_id: str) -> SessionState:
        """Get or create session state."""
        row = self.store.execute_one(
            "SELECT * FROM session_state WHERE session_id = ?",
            (session_id,),
        )

        if row:
            return SessionState.from_dict(row)

        # Create new session state
        state = SessionState(
            session_id=session_id,
            started_at=datetime.utcnow().isoformat(),
        )
        self.store.insert("session_state", state.to_dict())
        return state

    def update_session_state(
        self,
        session_id: str,
        reward: float,
        strategy: str | None = None,
    ) -> SessionState:
        """Update session state after an attempt."""
        state = self.get_session_state(session_id)

        state.attempt_count += 1
        state.reward_history.append(reward)
        if reward > state.best_reward:
            state.best_reward = reward
        if strategy:
            state.current_strategy = strategy

        self.store.update(
            "session_state",
            {
                "attempt_count": state.attempt_count,
                "reward_history": state.reward_history,
                "best_reward": state.best_reward,
                "current_strategy": state.current_strategy,
                "updated_at": datetime.utcnow().isoformat(),
            },
            "session_id = ?",
            (session_id,),
        )

        return state

    def get_all_sessions(self) -> list[SessionState]:
        """Get all session states."""
        rows = self.store.execute("SELECT * FROM session_state ORDER BY started_at DESC")
        return [SessionState.from_dict(row) for row in rows]

    def get_cross_session_episodes(
        self,
        k: int = 10,
        min_reward: float = 0.7,
    ) -> list[Episode]:
        """
        Get top episodes across all sessions.

        Useful for cross-session learning.
        """
        query = """
            SELECT * FROM episodes
            WHERE reward >= ?
            ORDER BY reward DESC
            LIMIT ?
        """
        rows = self.store.execute(query, (min_reward, k))
        return [Episode.from_dict(row) for row in rows]

    def compute_reward_trend(
        self,
        session_id: str,
        window: int = 5,
    ) -> float:
        """Compute reward trend over recent attempts."""
        state = self.get_session_state(session_id)

        if len(state.reward_history) < 2:
            return 0.0

        recent = state.reward_history[-window:]
        if len(recent) < 2:
            return recent[-1] - recent[0] if recent else 0.0

        # Linear trend
        return recent[-1] - recent[0]

    def is_stuck(
        self,
        session_id: str,
        threshold: float = 0.02,
        window: int = 3,
    ) -> bool:
        """Detect if reward is stuck (not improving)."""
        state = self.get_session_state(session_id)

        if len(state.reward_history) < window:
            return False

        recent = state.reward_history[-window:]
        variance = max(recent) - min(recent)

        return variance < threshold
