"""SQLite-backed memory store for persistent state."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class MemoryStore:
    """
    SQLite-backed persistent storage for Obsidian.

    Provides thread-safe access to episodes, session state,
    and learned patterns across sessions.
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection"):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self) -> None:
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._transaction() as cursor:
            # Schema version tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)

            # Check current version
            cursor.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current_version = row["version"] if row else 0

            if current_version < self.SCHEMA_VERSION:
                self._migrate_schema(cursor, current_version)

    def _migrate_schema(self, cursor: sqlite3.Cursor, from_version: int) -> None:
        """Apply schema migrations."""
        if from_version < 1:
            # Initial schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    action_summary TEXT,
                    reward REAL NOT NULL,
                    metrics TEXT NOT NULL,
                    failures TEXT,
                    strategy_used TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodes_session
                ON episodes(session_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodes_reward
                ON episodes(reward DESC)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_state (
                    session_id TEXT PRIMARY KEY,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    reward_history TEXT NOT NULL DEFAULT '[]',
                    best_reward REAL NOT NULL DEFAULT 0.0,
                    current_strategy TEXT,
                    started_at TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS baselines (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    timestamp TEXT NOT NULL,
                    reward REAL NOT NULL,
                    metrics TEXT NOT NULL,
                    attempt_number INTEGER,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS semantic_facts (
                    id TEXT PRIMARY KEY,
                    fact_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    source_episodes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_type
                ON semantic_facts(fact_type)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS procedural_strategies (
                    name TEXT PRIMARY KEY,
                    description TEXT,
                    total_reward_delta REAL NOT NULL DEFAULT 0.0,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Update schema version
            cursor.execute("DELETE FROM schema_version")
            cursor.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (self.SCHEMA_VERSION,),
            )

    def execute(
        self,
        query: str,
        params: tuple = (),
    ) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        with self._transaction() as cursor:
            cursor.execute(query, params)
            if cursor.description:
                return [dict(row) for row in cursor.fetchall()]
            return []

    def execute_one(
        self,
        query: str,
        params: tuple = (),
    ) -> dict[str, Any] | None:
        """Execute a query and return single result."""
        results = self.execute(query, params)
        return results[0] if results else None

    def insert(
        self,
        table: str,
        data: dict[str, Any],
    ) -> None:
        """Insert a row into a table."""
        columns = list(data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        column_str = ", ".join(columns)

        # Serialize JSON fields
        values = []
        for v in data.values():
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v))
            else:
                values.append(v)

        query = f"INSERT OR REPLACE INTO {table} ({column_str}) VALUES ({placeholders})"

        with self._transaction() as cursor:
            cursor.execute(query, tuple(values))

    def update(
        self,
        table: str,
        data: dict[str, Any],
        where: str,
        where_params: tuple = (),
    ) -> None:
        """Update rows in a table."""
        set_parts = []
        values = []

        for key, value in data.items():
            set_parts.append(f"{key} = ?")
            if isinstance(value, (dict, list)):
                values.append(json.dumps(value))
            else:
                values.append(value)

        set_clause = ", ".join(set_parts)
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"

        with self._transaction() as cursor:
            cursor.execute(query, tuple(values) + where_params)

    def delete(
        self,
        table: str,
        where: str,
        where_params: tuple = (),
    ) -> None:
        """Delete rows from a table."""
        query = f"DELETE FROM {table} WHERE {where}"

        with self._transaction() as cursor:
            cursor.execute(query, where_params)

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "connection"):
            self._local.connection.close()
            delattr(self._local, "connection")
