"""Semantic memory for storing learned facts and patterns."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .store import MemoryStore


class FactType(Enum):
    """Types of semantic facts."""

    PATTERN = "pattern"  # Code pattern that works
    CONSTRAINT = "constraint"  # Limitation or requirement
    PREFERENCE = "preference"  # User preference
    INSIGHT = "insight"  # Learned insight about codebase
    WARNING = "warning"  # Something to avoid


@dataclass
class SemanticFact:
    """A learned fact stored in semantic memory."""

    id: str
    fact_type: FactType
    content: str
    confidence: float  # 0-1
    source_episodes: list[str]  # Episode IDs that support this fact
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "fact_type": self.fact_type.value,
            "content": self.content,
            "confidence": self.confidence,
            "source_episodes": self.source_episodes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticFact":
        """Create from dictionary."""
        source_episodes = data.get("source_episodes", [])
        if isinstance(source_episodes, str):
            source_episodes = json.loads(source_episodes) if source_episodes else []

        metadata = data.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            fact_type=FactType(data.get("fact_type", "insight")),
            content=data.get("content", ""),
            confidence=data.get("confidence", 1.0),
            source_episodes=source_episodes,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=metadata,
        )


class SemanticMemory:
    """
    Semantic memory for storing and retrieving learned facts.

    Facts are accumulated from successful episodes and can be
    used to guide future attempts.
    """

    def __init__(self, store: MemoryStore):
        self.store = store

    def add_fact(
        self,
        fact_type: FactType,
        content: str,
        confidence: float = 1.0,
        source_episodes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticFact:
        """Add a new fact to semantic memory."""
        fact = SemanticFact(
            id=str(uuid.uuid4()),
            fact_type=fact_type,
            content=content,
            confidence=confidence,
            source_episodes=source_episodes or [],
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            metadata=metadata or {},
        )

        self.store.insert("semantic_facts", {
            "id": fact.id,
            "fact_type": fact.fact_type.value,
            "content": fact.content,
            "confidence": fact.confidence,
            "source_episodes": json.dumps(fact.source_episodes),
            "created_at": fact.created_at,
            "updated_at": fact.updated_at,
        })

        return fact

    def get_facts(
        self,
        fact_type: FactType | None = None,
        min_confidence: float = 0.0,
        limit: int | None = None,
    ) -> list[SemanticFact]:
        """Get facts from memory, optionally filtered by type."""
        if fact_type:
            query = """
                SELECT * FROM semantic_facts
                WHERE fact_type = ? AND confidence >= ?
                ORDER BY confidence DESC, updated_at DESC
            """
            params = (fact_type.value, min_confidence)
        else:
            query = """
                SELECT * FROM semantic_facts
                WHERE confidence >= ?
                ORDER BY confidence DESC, updated_at DESC
            """
            params = (min_confidence,)

        if limit:
            query += f" LIMIT {limit}"

        rows = self.store.execute(query, params)
        return [SemanticFact.from_dict(row) for row in rows]

    def get_patterns(self, min_confidence: float = 0.5) -> list[SemanticFact]:
        """Get learned patterns above confidence threshold."""
        return self.get_facts(FactType.PATTERN, min_confidence)

    def get_constraints(self) -> list[SemanticFact]:
        """Get all known constraints."""
        return self.get_facts(FactType.CONSTRAINT)

    def get_warnings(self) -> list[SemanticFact]:
        """Get all warnings (things to avoid)."""
        return self.get_facts(FactType.WARNING)

    def update_confidence(
        self,
        fact_id: str,
        new_confidence: float,
        source_episode: str | None = None,
    ) -> None:
        """Update confidence for a fact, optionally adding source episode."""
        fact = self.get_fact_by_id(fact_id)
        if not fact:
            return

        updates = {
            "confidence": new_confidence,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if source_episode:
            sources = fact.source_episodes
            if source_episode not in sources:
                sources.append(source_episode)
            updates["source_episodes"] = json.dumps(sources)

        self.store.update("semantic_facts", updates, "id = ?", (fact_id,))

    def get_fact_by_id(self, fact_id: str) -> SemanticFact | None:
        """Get a specific fact by ID."""
        row = self.store.execute_one(
            "SELECT * FROM semantic_facts WHERE id = ?",
            (fact_id,),
        )
        return SemanticFact.from_dict(row) if row else None

    def search_facts(self, query: str, limit: int = 10) -> list[SemanticFact]:
        """Search facts by content."""
        rows = self.store.execute(
            """
            SELECT * FROM semantic_facts
            WHERE content LIKE ?
            ORDER BY confidence DESC
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )
        return [SemanticFact.from_dict(row) for row in rows]

    def decay_confidence(self, decay_rate: float = 0.95) -> None:
        """
        Apply decay to all fact confidences.

        Called periodically to forget less-used facts.
        """
        self.store.execute(
            """
            UPDATE semantic_facts
            SET confidence = confidence * ?,
                updated_at = ?
            WHERE confidence > 0.1
            """,
            (decay_rate, datetime.utcnow().isoformat()),
        )

    def prune_low_confidence(self, threshold: float = 0.1) -> int:
        """Remove facts below confidence threshold."""
        result = self.store.execute(
            "SELECT COUNT(*) as count FROM semantic_facts WHERE confidence < ?",
            (threshold,),
        )
        count = result[0]["count"] if result else 0

        self.store.delete("semantic_facts", "confidence < ?", (threshold,))
        return count

    def extract_facts_from_episode(
        self,
        episode_id: str,
        action_summary: str,
        reward: float,
        metrics: dict[str, float],
    ) -> list[SemanticFact]:
        """
        Extract semantic facts from a successful episode.

        Called after high-reward episodes to learn patterns.
        """
        facts = []

        # Only extract from successful episodes
        if reward < 0.7:
            return facts

        # Extract pattern from action summary
        if action_summary:
            fact = self.add_fact(
                fact_type=FactType.PATTERN,
                content=action_summary,
                confidence=min(0.9, reward),
                source_episodes=[episode_id],
                metadata={"reward": reward, "metrics": metrics},
            )
            facts.append(fact)

        return facts

    def format_for_context(self, max_facts: int = 10) -> str:
        """Format facts for context injection."""
        facts = self.get_facts(min_confidence=0.5, limit=max_facts)

        if not facts:
            return ""

        lines = ["<learned_facts>"]
        for fact in facts:
            lines.append(
                f"<fact type=\"{fact.fact_type.value}\" confidence=\"{fact.confidence:.2f}\">"
            )
            lines.append(f"  {fact.content}")
            lines.append("</fact>")
        lines.append("</learned_facts>")

        return "\n".join(lines)
