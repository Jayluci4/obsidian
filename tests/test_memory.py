"""Tests for the memory module."""

import tempfile
from pathlib import Path

import pytest

from obsidian.memory import (
    MemoryStore,
    EpisodicMemory,
    Episode,
    SessionState,
    SemanticMemory,
    SemanticFact,
    FactType,
    ProceduralMemory,
    StrategyRecord,
)


class TestMemoryStore:
    """Tests for MemoryStore."""

    def test_create_store(self):
        """Test creating a memory store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = MemoryStore(db_path)

            assert db_path.exists()
            store.close()

    def test_insert_and_retrieve(self):
        """Test inserting and retrieving data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = MemoryStore(db_path)

            # Insert an episode
            store.insert("episodes", {
                "id": "ep_1",
                "session_id": "sess_1",
                "attempt_number": 1,
                "timestamp": "2024-01-01T00:00:00",
                "reward": 0.75,
                "metrics": {"pytest": 0.8, "coverage": 0.7},
            })

            # Retrieve it
            result = store.execute_one(
                "SELECT * FROM episodes WHERE id = ?",
                ("ep_1",),
            )

            assert result is not None
            assert result["id"] == "ep_1"
            assert result["reward"] == 0.75
            store.close()

    def test_update(self):
        """Test updating data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = MemoryStore(db_path)

            store.insert("session_state", {
                "session_id": "sess_1",
                "attempt_count": 0,
                "reward_history": [],
                "best_reward": 0.0,
            })

            store.update(
                "session_state",
                {"attempt_count": 5, "best_reward": 0.9},
                "session_id = ?",
                ("sess_1",),
            )

            result = store.execute_one(
                "SELECT * FROM session_state WHERE session_id = ?",
                ("sess_1",),
            )

            assert result["attempt_count"] == 5
            assert result["best_reward"] == 0.9
            store.close()

    def test_delete(self):
        """Test deleting data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = MemoryStore(db_path)

            store.insert("episodes", {
                "id": "ep_1",
                "session_id": "sess_1",
                "attempt_number": 1,
                "timestamp": "2024-01-01T00:00:00",
                "reward": 0.75,
                "metrics": {},
            })

            store.delete("episodes", "id = ?", ("ep_1",))

            result = store.execute_one(
                "SELECT * FROM episodes WHERE id = ?",
                ("ep_1",),
            )

            assert result is None
            store.close()

    def test_transaction_rollback(self):
        """Test that transactions rollback on error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = MemoryStore(db_path)

            # Insert valid data
            store.insert("episodes", {
                "id": "ep_1",
                "session_id": "sess_1",
                "attempt_number": 1,
                "timestamp": "2024-01-01",
                "reward": 0.5,
                "metrics": {},
            })

            # Verify data exists
            result = store.execute_one(
                "SELECT * FROM episodes WHERE id = ?",
                ("ep_1",),
            )
            assert result is not None
            store.close()


class TestEpisode:
    """Tests for Episode dataclass."""

    def test_episode_creation(self):
        """Test creating an Episode."""
        ep = Episode(
            id="ep_1",
            session_id="sess_1",
            attempt_number=3,
            timestamp="2024-01-01T12:00:00",
            reward=0.85,
            metrics={"pytest": 0.9, "coverage": 0.8},
            action_summary="Fixed test failure",
            failures=["test_foo failed"],
        )

        assert ep.id == "ep_1"
        assert ep.reward == 0.85
        assert len(ep.failures) == 1

    def test_episode_to_dict(self):
        """Test Episode serialization."""
        ep = Episode(
            id="ep_1",
            session_id="sess_1",
            attempt_number=1,
            timestamp="2024-01-01",
            reward=0.5,
            metrics={"pytest": 0.5},
        )

        data = ep.to_dict()

        assert data["id"] == "ep_1"
        assert data["reward"] == 0.5
        assert "metrics" in data

    def test_episode_from_dict(self):
        """Test Episode deserialization."""
        data = {
            "id": "ep_2",
            "session_id": "sess_1",
            "attempt_number": 2,
            "timestamp": "2024-01-02",
            "reward": 0.7,
            "metrics": '{"pytest": 0.7}',  # JSON string
            "failures": '["test_a", "test_b"]',  # JSON string
        }

        ep = Episode.from_dict(data)

        assert ep.id == "ep_2"
        assert ep.reward == 0.7
        assert ep.metrics == {"pytest": 0.7}
        assert ep.failures == ["test_a", "test_b"]


class TestSessionState:
    """Tests for SessionState dataclass."""

    def test_session_state_creation(self):
        """Test creating SessionState."""
        state = SessionState(
            session_id="sess_1",
            attempt_count=5,
            reward_history=[0.3, 0.5, 0.6, 0.7, 0.8],
            best_reward=0.8,
        )

        assert state.attempt_count == 5
        assert state.best_reward == 0.8
        assert len(state.reward_history) == 5

    def test_session_state_from_dict(self):
        """Test SessionState deserialization."""
        data = {
            "session_id": "sess_1",
            "attempt_count": 3,
            "reward_history": '[0.4, 0.5, 0.6]',  # JSON string
            "best_reward": 0.6,
        }

        state = SessionState.from_dict(data)

        assert state.attempt_count == 3
        assert state.reward_history == [0.4, 0.5, 0.6]


class TestEpisodicMemory:
    """Tests for EpisodicMemory."""

    def create_memory(self, tmpdir):
        """Create a test episodic memory."""
        db_path = Path(tmpdir) / "test.db"
        store = MemoryStore(db_path)
        return EpisodicMemory(store), store

    def test_add_episode(self):
        """Test adding an episode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            ep = memory.add_episode(
                session_id="sess_1",
                attempt_number=1,
                reward=0.75,
                metrics={"pytest": 0.8},
                action_summary="Added tests",
            )

            assert ep.id is not None
            assert ep.reward == 0.75
            assert ep.metrics == {"pytest": 0.8}
            store.close()

    def test_get_episodes(self):
        """Test retrieving episodes for a session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Add multiple episodes
            for i in range(5):
                memory.add_episode(
                    session_id="sess_1",
                    attempt_number=i + 1,
                    reward=0.1 * (i + 1),
                    metrics={"test": 0.5},
                )

            episodes = memory.get_episodes("sess_1")

            assert len(episodes) == 5
            assert episodes[0].attempt_number == 1
            assert episodes[4].attempt_number == 5
            store.close()

    def test_get_top_k_episodes(self):
        """Test getting top K episodes by reward."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Add episodes with varying rewards
            rewards = [0.3, 0.9, 0.5, 0.8, 0.2, 0.7]
            for i, reward in enumerate(rewards):
                memory.add_episode(
                    session_id="sess_1",
                    attempt_number=i + 1,
                    reward=reward,
                    metrics={},
                )

            top3 = memory.get_top_k_episodes("sess_1", k=3, include_failures=False)

            assert len(top3) == 3
            assert top3[0].reward == 0.9
            assert top3[1].reward == 0.8
            assert top3[2].reward == 0.7
            store.close()

    def test_get_best_episode(self):
        """Test getting the best episode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.add_episode("sess_1", 1, 0.5, {})
            memory.add_episode("sess_1", 2, 0.9, {})
            memory.add_episode("sess_1", 3, 0.7, {})

            best = memory.get_best_episode("sess_1")

            assert best is not None
            assert best.reward == 0.9
            assert best.attempt_number == 2
            store.close()

    def test_get_recent_episodes(self):
        """Test getting recent episodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            for i in range(10):
                memory.add_episode("sess_1", i + 1, 0.5, {})

            recent = memory.get_recent_episodes("sess_1", n=3)

            assert len(recent) == 3
            # Most recent first
            assert recent[0].attempt_number == 10
            assert recent[1].attempt_number == 9
            assert recent[2].attempt_number == 8
            store.close()

    def test_session_state_management(self):
        """Test session state get/update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Get creates new state
            state = memory.get_session_state("sess_1")
            assert state.attempt_count == 0
            assert state.best_reward == 0.0

            # Update state
            updated = memory.update_session_state("sess_1", reward=0.6)
            assert updated.attempt_count == 1
            assert updated.best_reward == 0.6
            assert updated.reward_history == [0.6]

            # Update again with higher reward
            updated = memory.update_session_state("sess_1", reward=0.8)
            assert updated.attempt_count == 2
            assert updated.best_reward == 0.8
            assert updated.reward_history == [0.6, 0.8]
            store.close()

    def test_compute_reward_trend(self):
        """Test computing reward trend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Add episodes with increasing rewards
            for reward in [0.3, 0.4, 0.5, 0.6, 0.7]:
                memory.update_session_state("sess_1", reward=reward)

            trend = memory.compute_reward_trend("sess_1", window=5)

            # Trend should be positive (0.7 - 0.3 = 0.4)
            assert abs(trend - 0.4) < 0.001
            store.close()

    def test_is_stuck(self):
        """Test stuck detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Add episodes with same reward (stuck)
            for _ in range(5):
                memory.update_session_state("sess_1", reward=0.5)

            assert memory.is_stuck("sess_1", threshold=0.02, window=3) is True

            # Add episode with different reward
            memory.update_session_state("sess_1", reward=0.8)

            assert memory.is_stuck("sess_1", threshold=0.02, window=3) is False
            store.close()

    def test_cross_session_episodes(self):
        """Test getting episodes across sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Add episodes to multiple sessions
            memory.add_episode("sess_1", 1, 0.9, {})
            memory.add_episode("sess_1", 2, 0.6, {})
            memory.add_episode("sess_2", 1, 0.85, {})
            memory.add_episode("sess_2", 2, 0.4, {})

            # Get cross-session high-reward episodes
            top = memory.get_cross_session_episodes(k=5, min_reward=0.7)

            assert len(top) == 2
            assert all(ep.reward >= 0.7 for ep in top)
            store.close()


class TestSemanticFact:
    """Tests for SemanticFact dataclass."""

    def test_fact_creation(self):
        """Test creating a SemanticFact."""
        fact = SemanticFact(
            id="fact_1",
            fact_type=FactType.PATTERN,
            content="Use pytest fixtures for setup",
            confidence=0.85,
            source_episodes=["ep_1", "ep_2"],
        )

        assert fact.fact_type == FactType.PATTERN
        assert fact.confidence == 0.85

    def test_fact_to_dict(self):
        """Test SemanticFact serialization."""
        fact = SemanticFact(
            id="fact_1",
            fact_type=FactType.WARNING,
            content="Avoid global state",
            confidence=0.9,
            source_episodes=["ep_1"],
        )

        data = fact.to_dict()

        assert data["fact_type"] == "warning"
        assert data["confidence"] == 0.9

    def test_fact_from_dict(self):
        """Test SemanticFact deserialization."""
        data = {
            "id": "fact_1",
            "fact_type": "constraint",
            "content": "Must use Python 3.10+",
            "confidence": 1.0,
            "source_episodes": '["ep_1"]',  # JSON string
        }

        fact = SemanticFact.from_dict(data)

        assert fact.fact_type == FactType.CONSTRAINT
        assert fact.source_episodes == ["ep_1"]


class TestSemanticMemory:
    """Tests for SemanticMemory."""

    def create_memory(self, tmpdir):
        """Create a test semantic memory."""
        db_path = Path(tmpdir) / "test.db"
        store = MemoryStore(db_path)
        return SemanticMemory(store), store

    def test_add_fact(self):
        """Test adding a fact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            fact = memory.add_fact(
                fact_type=FactType.PATTERN,
                content="Use dependency injection",
                confidence=0.8,
            )

            assert fact.id is not None
            assert fact.content == "Use dependency injection"
            store.close()

    def test_get_facts(self):
        """Test retrieving facts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.add_fact(FactType.PATTERN, "Pattern 1", confidence=0.9)
            memory.add_fact(FactType.PATTERN, "Pattern 2", confidence=0.7)
            memory.add_fact(FactType.WARNING, "Warning 1", confidence=0.85)

            patterns = memory.get_facts(FactType.PATTERN)
            assert len(patterns) == 2

            all_facts = memory.get_facts()
            assert len(all_facts) == 3
            store.close()

    def test_get_facts_with_min_confidence(self):
        """Test filtering facts by confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.add_fact(FactType.INSIGHT, "High confidence", confidence=0.9)
            memory.add_fact(FactType.INSIGHT, "Medium confidence", confidence=0.6)
            memory.add_fact(FactType.INSIGHT, "Low confidence", confidence=0.3)

            high_conf = memory.get_facts(min_confidence=0.7)
            assert len(high_conf) == 1
            assert high_conf[0].content == "High confidence"
            store.close()

    def test_update_confidence(self):
        """Test updating fact confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            fact = memory.add_fact(FactType.PATTERN, "Test pattern", confidence=0.5)

            memory.update_confidence(fact.id, 0.9, source_episode="ep_new")

            updated = memory.get_fact_by_id(fact.id)
            assert updated.confidence == 0.9
            assert "ep_new" in updated.source_episodes
            store.close()

    def test_search_facts(self):
        """Test searching facts by content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.add_fact(FactType.PATTERN, "Use pytest for testing")
            memory.add_fact(FactType.PATTERN, "Use unittest for legacy code")
            memory.add_fact(FactType.WARNING, "Avoid global variables")

            results = memory.search_facts("pytest")
            assert len(results) == 1
            assert "pytest" in results[0].content
            store.close()

    def test_decay_confidence(self):
        """Test confidence decay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            fact = memory.add_fact(FactType.PATTERN, "Test", confidence=1.0)

            memory.decay_confidence(decay_rate=0.9)

            updated = memory.get_fact_by_id(fact.id)
            assert updated.confidence == 0.9
            store.close()

    def test_prune_low_confidence(self):
        """Test pruning low-confidence facts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.add_fact(FactType.PATTERN, "High", confidence=0.9)
            memory.add_fact(FactType.PATTERN, "Low", confidence=0.05)
            memory.add_fact(FactType.PATTERN, "Very Low", confidence=0.01)

            pruned = memory.prune_low_confidence(threshold=0.1)

            assert pruned == 2

            remaining = memory.get_facts()
            assert len(remaining) == 1
            assert remaining[0].content == "High"
            store.close()

    def test_extract_facts_from_episode(self):
        """Test extracting facts from high-reward episodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Low reward - no facts extracted
            facts_low = memory.extract_facts_from_episode(
                episode_id="ep_1",
                action_summary="Did something",
                reward=0.4,
                metrics={},
            )
            assert len(facts_low) == 0

            # High reward - facts extracted
            facts_high = memory.extract_facts_from_episode(
                episode_id="ep_2",
                action_summary="Fixed all tests",
                reward=0.9,
                metrics={"pytest": 1.0},
            )
            assert len(facts_high) == 1
            assert facts_high[0].content == "Fixed all tests"
            store.close()

    def test_format_for_context(self):
        """Test formatting facts for context injection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.add_fact(FactType.PATTERN, "Use fixtures", confidence=0.9)
            memory.add_fact(FactType.WARNING, "Avoid mocks", confidence=0.8)

            context = memory.format_for_context()

            assert "<learned_facts>" in context
            assert "Use fixtures" in context
            assert "Avoid mocks" in context
            assert "</learned_facts>" in context
            store.close()


class TestStrategyRecord:
    """Tests for StrategyRecord dataclass."""

    def test_strategy_creation(self):
        """Test creating a StrategyRecord."""
        record = StrategyRecord(
            name="exploit",
            description="Refine current approach",
            total_reward_delta=0.5,
            usage_count=10,
            success_count=7,
        )

        assert record.success_rate == 0.7
        assert record.avg_delta == 0.05

    def test_strategy_zero_usage(self):
        """Test StrategyRecord with zero usage."""
        record = StrategyRecord(
            name="new_strategy",
            description="Untested",
            total_reward_delta=0.0,
            usage_count=0,
            success_count=0,
        )

        assert record.success_rate == 0.0
        assert record.avg_delta == 0.0


class TestProceduralMemory:
    """Tests for ProceduralMemory."""

    def create_memory(self, tmpdir):
        """Create a test procedural memory."""
        db_path = Path(tmpdir) / "test.db"
        store = MemoryStore(db_path)
        return ProceduralMemory(store), store

    def test_record_outcome(self):
        """Test recording strategy outcomes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            record = memory.record_outcome(
                strategy_name="exploit",
                reward_before=0.5,
                reward_after=0.7,
                description="Refine approach",
            )

            assert record.name == "exploit"
            assert record.usage_count == 1
            assert record.success_count == 1  # Delta > 0.02
            assert abs(record.total_reward_delta - 0.2) < 0.01
            store.close()

    def test_record_multiple_outcomes(self):
        """Test recording multiple outcomes for same strategy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.record_outcome("explore", 0.3, 0.5)  # +0.2 success
            memory.record_outcome("explore", 0.5, 0.4)  # -0.1 failure
            memory.record_outcome("explore", 0.4, 0.6)  # +0.2 success

            record = memory.get_strategy("explore")

            assert record.usage_count == 3
            assert record.success_count == 2
            assert abs(record.total_reward_delta - 0.3) < 0.01  # 0.2 - 0.1 + 0.2
            store.close()

    def test_get_best_strategies(self):
        """Test getting best performing strategies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Record outcomes for multiple strategies
            for _ in range(3):
                memory.record_outcome("exploit", 0.5, 0.7)  # High delta
            for _ in range(3):
                memory.record_outcome("explore", 0.5, 0.55)  # Low delta
            for _ in range(3):
                memory.record_outcome("random", 0.5, 0.6)  # Medium delta

            best = memory.get_best_strategies(limit=2)

            assert len(best) == 2
            assert best[0].name == "exploit"
            assert best[1].name == "random"
            store.close()

    def test_get_recommended_strategy(self):
        """Test getting recommended strategy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            # Need at least 2 uses for recommendation
            for _ in range(3):
                memory.record_outcome("good_strategy", 0.5, 0.8)
            for _ in range(2):
                memory.record_outcome("ok_strategy", 0.5, 0.6)

            recommended = memory.get_recommended_strategy()
            assert recommended.name == "good_strategy"

            # Test exclusion
            recommended = memory.get_recommended_strategy(exclude=["good_strategy"])
            assert recommended.name == "ok_strategy"
            store.close()

    def test_get_stats(self):
        """Test getting aggregate stats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.record_outcome("a", 0.3, 0.5)
            memory.record_outcome("a", 0.5, 0.7)
            memory.record_outcome("b", 0.4, 0.6)

            stats = memory.get_stats()

            assert stats["total_strategies"] == 2
            assert stats["total_uses"] == 3
            assert stats["total_successes"] == 3  # All had delta > 0.02
            assert stats["overall_success_rate"] == 1.0
            store.close()

    def test_format_for_context(self):
        """Test formatting strategies for context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            for _ in range(3):
                memory.record_outcome("exploit", 0.5, 0.7, "Refine approach")

            context = memory.format_for_context()

            assert "<strategy_knowledge>" in context
            assert "exploit" in context
            assert "Refine approach" in context
            store.close()

    def test_clear(self):
        """Test clearing all strategy records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory, store = self.create_memory(tmpdir)

            memory.record_outcome("a", 0.3, 0.5)
            memory.record_outcome("b", 0.4, 0.6)

            memory.clear()

            strategies = memory.get_all_strategies()
            assert len(strategies) == 0
            store.close()
