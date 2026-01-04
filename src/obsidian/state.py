"""Session state management for Obsidian plugin."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .memory.store import MemoryStore
from .memory.episodic import EpisodicMemory
from .memory.episodic import Episode as SQLiteEpisode
from .memory.episodic import SessionState as SQLiteSessionState


@dataclass
class Episode:
    """Record of a single attempt."""

    attempt_number: int
    timestamp: str
    reward: float
    metrics: dict[str, float]
    action_summary: str = ""
    failures: list[str] = field(default_factory=list)


@dataclass
class SessionState:
    """State for current session."""

    session_id: str
    attempt_count: int = 0
    reward_history: list[float] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    best_reward: float = 0.0
    started_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "attempt_count": self.attempt_count,
            "reward_history": self.reward_history,
            "episodes": [
                {
                    "attempt_number": e.attempt_number,
                    "timestamp": e.timestamp,
                    "reward": e.reward,
                    "metrics": e.metrics,
                    "action_summary": e.action_summary,
                    "failures": e.failures,
                }
                for e in self.episodes
            ],
            "best_reward": self.best_reward,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        """Create from dictionary."""
        episodes = [
            Episode(
                attempt_number=e["attempt_number"],
                timestamp=e["timestamp"],
                reward=e["reward"],
                metrics=e["metrics"],
                action_summary=e.get("action_summary", ""),
                failures=e.get("failures", []),
            )
            for e in data.get("episodes", [])
        ]

        return cls(
            session_id=data["session_id"],
            attempt_count=data.get("attempt_count", 0),
            reward_history=data.get("reward_history", []),
            episodes=episodes,
            best_reward=data.get("best_reward", 0.0),
            started_at=data.get("started_at", ""),
        )


class StateManager:
    """Manages persistent session state."""

    def __init__(self, state_dir: Path, session_id: str):
        self.state_dir = state_dir
        self.session_id = session_id
        self.state_file = state_dir / f"session_{session_id}.json"
        self._state: SessionState | None = None

    def load(self) -> SessionState:
        """Load state from disk or create new."""
        if self._state is not None:
            return self._state

        if self.state_file.exists():
            with open(self.state_file) as f:
                data = json.load(f)
            self._state = SessionState.from_dict(data)
        else:
            self._state = SessionState(
                session_id=self.session_id,
                started_at=datetime.utcnow().isoformat(),
            )
            self.save()

        return self._state

    def save(self) -> None:
        """Save state to disk."""
        if self._state is None:
            return

        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def add_episode(
        self,
        reward: float,
        metrics: dict[str, float],
        action_summary: str = "",
        failures: list[str] | None = None,
    ) -> Episode:
        """Add a new episode to the session."""
        state = self.load()

        state.attempt_count += 1
        state.reward_history.append(reward)
        state.best_reward = max(state.best_reward, reward)

        episode = Episode(
            attempt_number=state.attempt_count,
            timestamp=datetime.utcnow().isoformat(),
            reward=reward,
            metrics=metrics,
            action_summary=action_summary,
            failures=failures or [],
        )
        state.episodes.append(episode)

        self.save()
        return episode

    def get_recent_episodes(self, n: int = 5) -> list[Episode]:
        """Get the N most recent episodes."""
        state = self.load()
        return state.episodes[-n:]

    def get_best_episodes(self, n: int = 3) -> list[Episode]:
        """Get the N highest reward episodes."""
        state = self.load()
        return sorted(state.episodes, key=lambda e: e.reward, reverse=True)[:n]


class SQLiteStateManager:
    """
    SQLite-backed state manager for persistent memory.

    Provides the same interface as StateManager but uses SQLite
    for better cross-session querying and scalability.
    """

    def __init__(self, state_dir: Path, session_id: str):
        self.state_dir = state_dir
        self.session_id = session_id
        self.db_path = state_dir / "memory.db"

        # Initialize store and memory
        state_dir.mkdir(parents=True, exist_ok=True)
        self._store = MemoryStore(self.db_path)
        self._memory = EpisodicMemory(self._store)
        self._state: SessionState | None = None

    @property
    def memory(self) -> EpisodicMemory:
        """Access to episodic memory for advanced queries."""
        return self._memory

    def load(self) -> SessionState:
        """Load state from SQLite or create new."""
        if self._state is not None:
            return self._state

        sqlite_state = self._memory.get_session_state(self.session_id)

        # Convert to local SessionState format
        episodes = self._memory.get_episodes(self.session_id)

        self._state = SessionState(
            session_id=self.session_id,
            attempt_count=sqlite_state.attempt_count,
            reward_history=sqlite_state.reward_history,
            episodes=[
                Episode(
                    attempt_number=e.attempt_number,
                    timestamp=e.timestamp,
                    reward=e.reward,
                    metrics=e.metrics,
                    action_summary=e.action_summary,
                    failures=e.failures,
                )
                for e in episodes
            ],
            best_reward=sqlite_state.best_reward,
            started_at=sqlite_state.started_at,
        )

        return self._state

    def save(self) -> None:
        """Save state to SQLite. (No-op since writes are immediate.)"""
        pass

    def add_episode(
        self,
        reward: float,
        metrics: dict[str, float],
        action_summary: str = "",
        failures: list[str] | None = None,
    ) -> Episode:
        """Add a new episode to the session."""
        state = self.load()

        # Update session state
        self._memory.update_session_state(self.session_id, reward)

        # Add episode
        attempt_number = state.attempt_count + 1
        sqlite_episode = self._memory.add_episode(
            session_id=self.session_id,
            attempt_number=attempt_number,
            reward=reward,
            metrics=metrics,
            action_summary=action_summary,
            failures=failures,
        )

        # Update local state
        episode = Episode(
            attempt_number=attempt_number,
            timestamp=sqlite_episode.timestamp,
            reward=reward,
            metrics=metrics,
            action_summary=action_summary,
            failures=failures or [],
        )

        state.attempt_count = attempt_number
        state.reward_history.append(reward)
        state.best_reward = max(state.best_reward, reward)
        state.episodes.append(episode)

        return episode

    def get_recent_episodes(self, n: int = 5) -> list[Episode]:
        """Get the N most recent episodes."""
        episodes = self._memory.get_recent_episodes(self.session_id, n)
        return [
            Episode(
                attempt_number=e.attempt_number,
                timestamp=e.timestamp,
                reward=e.reward,
                metrics=e.metrics,
                action_summary=e.action_summary,
                failures=e.failures,
            )
            for e in episodes
        ]

    def get_best_episodes(self, n: int = 3) -> list[Episode]:
        """Get the N highest reward episodes."""
        episodes = self._memory.get_top_k_episodes(
            self.session_id, k=n, include_failures=False
        )
        return [
            Episode(
                attempt_number=e.attempt_number,
                timestamp=e.timestamp,
                reward=e.reward,
                metrics=e.metrics,
                action_summary=e.action_summary,
                failures=e.failures,
            )
            for e in episodes
        ]

    def get_top_k_for_icrl(self, k: int = 5) -> list[Episode]:
        """Get top K episodes for ICRL context injection."""
        episodes = self._memory.get_top_k_episodes(
            self.session_id, k=k, include_failures=True
        )
        return [
            Episode(
                attempt_number=e.attempt_number,
                timestamp=e.timestamp,
                reward=e.reward,
                metrics=e.metrics,
                action_summary=e.action_summary,
                failures=e.failures,
            )
            for e in episodes
        ]

    def is_stuck(self, threshold: float = 0.02, window: int = 3) -> bool:
        """Check if reward is stuck."""
        return self._memory.is_stuck(self.session_id, threshold, window)

    def compute_trend(self, window: int = 5) -> float:
        """Compute reward trend."""
        return self._memory.compute_reward_trend(self.session_id, window)

    def close(self) -> None:
        """Close database connection."""
        self._store.close()
