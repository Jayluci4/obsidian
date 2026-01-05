"""Evaluation caching system.

Caches evaluation results based on file hashes to avoid
redundant evaluations when code hasn't changed.
"""

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .base import EvalResult


@dataclass
class CacheEntry:
    """Cached evaluation result."""

    evaluator_name: str
    file_hash: str
    result: dict[str, Any]  # Serialized EvalResult
    timestamp: float
    project_path: str


@dataclass
class CacheStats:
    """Cache performance statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


def compute_file_hash(file_path: Path) -> str:
    """Compute MD5 hash of a file."""
    hasher = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, IOError):
        return ""


def compute_directory_hash(
    directory: Path,
    extensions: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> str:
    """
    Compute combined hash of all relevant files in directory.

    Args:
        directory: Directory to hash
        extensions: File extensions to include (e.g., [".py"])
        exclude_patterns: Patterns to exclude (e.g., ["__pycache__", ".git"])

    Returns:
        Combined hash string
    """
    extensions = extensions or [".py"]
    exclude_patterns = exclude_patterns or [
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        "*.pyc",
        "*.pyo",
        ".obsidian",
        "node_modules",
        ".venv",
        "venv",
    ]

    hasher = hashlib.md5()
    file_count = 0

    for root, dirs, files in os.walk(directory):
        # Filter directories
        dirs[:] = [
            d for d in sorted(dirs)
            if not any(p in d for p in exclude_patterns)
        ]

        for filename in sorted(files):
            # Check extension
            if extensions and not any(filename.endswith(ext) for ext in extensions):
                continue

            # Check exclusion patterns
            if any(p in filename for p in exclude_patterns):
                continue

            file_path = Path(root) / filename
            file_hash = compute_file_hash(file_path)

            if file_hash:
                # Include relative path and hash in combined hash
                rel_path = file_path.relative_to(directory)
                hasher.update(f"{rel_path}:{file_hash}".encode())
                file_count += 1

    # Include file count to detect additions/deletions
    hasher.update(f"count:{file_count}".encode())

    return hasher.hexdigest()


class EvaluationCache:
    """
    Cache for evaluation results.

    Uses file hashes to determine if code has changed.
    Persists cache to disk for session continuity.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_entries: int = 100,
        ttl_seconds: int = 3600,  # 1 hour default TTL
        enabled: bool = True,
    ):
        """
        Initialize evaluation cache.

        Args:
            cache_dir: Directory to store cache files
            max_entries: Maximum entries per evaluator
            ttl_seconds: Time-to-live for cache entries
            enabled: Whether caching is enabled
        """
        self.cache_dir = cache_dir
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled

        self._cache: dict[str, dict[str, CacheEntry]] = {}  # {evaluator: {hash: entry}}
        self._stats = CacheStats()

        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    def _cache_file(self) -> Path | None:
        """Get cache file path."""
        if self.cache_dir:
            return self.cache_dir / "eval_cache.json"
        return None

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = self._cache_file()
        if not cache_file or not cache_file.exists():
            return

        try:
            with open(cache_file) as f:
                data = json.load(f)

            for evaluator, entries in data.items():
                self._cache[evaluator] = {}
                for file_hash, entry_data in entries.items():
                    entry = CacheEntry(
                        evaluator_name=entry_data["evaluator_name"],
                        file_hash=entry_data["file_hash"],
                        result=entry_data["result"],
                        timestamp=entry_data["timestamp"],
                        project_path=entry_data["project_path"],
                    )
                    # Check TTL
                    if time.time() - entry.timestamp < self.ttl_seconds:
                        self._cache[evaluator][file_hash] = entry
        except (json.JSONDecodeError, KeyError, TypeError):
            # Invalid cache file, start fresh
            self._cache = {}

    def _save_cache(self) -> None:
        """Save cache to disk."""
        cache_file = self._cache_file()
        if not cache_file:
            return

        data = {}
        for evaluator, entries in self._cache.items():
            data[evaluator] = {}
            for file_hash, entry in entries.items():
                data[evaluator][file_hash] = {
                    "evaluator_name": entry.evaluator_name,
                    "file_hash": entry.file_hash,
                    "result": entry.result,
                    "timestamp": entry.timestamp,
                    "project_path": entry.project_path,
                }

        try:
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except (OSError, IOError):
            pass  # Silent fail for cache persistence

    def get(
        self,
        evaluator_name: str,
        project_path: str,
        source_dir: str = "src",
    ) -> EvalResult | None:
        """
        Get cached evaluation result if available.

        Args:
            evaluator_name: Name of the evaluator
            project_path: Path to project root
            source_dir: Source directory to hash

        Returns:
            Cached EvalResult or None if cache miss
        """
        if not self.enabled:
            self._stats.misses += 1
            return None

        # Compute current file hash
        source_path = Path(project_path) / source_dir
        if not source_path.exists():
            source_path = Path(project_path)

        current_hash = compute_directory_hash(source_path)

        # Check cache
        if evaluator_name in self._cache:
            if current_hash in self._cache[evaluator_name]:
                entry = self._cache[evaluator_name][current_hash]

                # Verify TTL
                if time.time() - entry.timestamp < self.ttl_seconds:
                    self._stats.hits += 1
                    return self._deserialize_result(entry.result)
                else:
                    # Entry expired
                    del self._cache[evaluator_name][current_hash]
                    self._stats.evictions += 1

        self._stats.misses += 1
        return None

    def put(
        self,
        evaluator_name: str,
        project_path: str,
        result: EvalResult,
        source_dir: str = "src",
    ) -> None:
        """
        Store evaluation result in cache.

        Args:
            evaluator_name: Name of the evaluator
            project_path: Path to project root
            result: Evaluation result to cache
            source_dir: Source directory that was evaluated
        """
        if not self.enabled:
            return

        # Compute file hash
        source_path = Path(project_path) / source_dir
        if not source_path.exists():
            source_path = Path(project_path)

        current_hash = compute_directory_hash(source_path)

        # Initialize evaluator cache if needed
        if evaluator_name not in self._cache:
            self._cache[evaluator_name] = {}

        # Evict oldest entries if at capacity
        while len(self._cache[evaluator_name]) >= self.max_entries:
            oldest_hash = min(
                self._cache[evaluator_name],
                key=lambda h: self._cache[evaluator_name][h].timestamp,
            )
            del self._cache[evaluator_name][oldest_hash]
            self._stats.evictions += 1

        # Store entry
        entry = CacheEntry(
            evaluator_name=evaluator_name,
            file_hash=current_hash,
            result=self._serialize_result(result),
            timestamp=time.time(),
            project_path=project_path,
        )
        self._cache[evaluator_name][current_hash] = entry

        # Persist to disk
        self._save_cache()

    def _serialize_result(self, result: EvalResult) -> dict[str, Any]:
        """Serialize EvalResult for storage."""
        return {
            "name": result.name,
            "score": result.score,
            "passed": result.passed,
            "error": result.error,
            "details": result.details,
        }

    def _deserialize_result(self, data: dict[str, Any]) -> EvalResult:
        """Deserialize EvalResult from storage."""
        return EvalResult(
            name=data["name"],
            score=data["score"],
            passed=data["passed"],
            error=data.get("error"),
            details=data.get("details"),
        )

    def invalidate(self, evaluator_name: str | None = None) -> int:
        """
        Invalidate cache entries.

        Args:
            evaluator_name: Specific evaluator to invalidate, or None for all

        Returns:
            Number of entries invalidated
        """
        count = 0

        if evaluator_name:
            if evaluator_name in self._cache:
                count = len(self._cache[evaluator_name])
                del self._cache[evaluator_name]
        else:
            for evaluator in list(self._cache.keys()):
                count += len(self._cache[evaluator])
            self._cache = {}

        self._save_cache()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_entries = sum(len(entries) for entries in self._cache.values())
        return {
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "evictions": self._stats.evictions,
            "hit_rate": self._stats.hit_rate,
            "total_entries": total_entries,
            "enabled": self.enabled,
        }

    def clear(self) -> None:
        """Clear all cache entries and stats."""
        self._cache = {}
        self._stats = CacheStats()
        self._save_cache()


class CachedEvaluatorWrapper:
    """
    Wrapper that adds caching to any evaluator.

    Usage:
        evaluator = PytestEvaluator()
        cached = CachedEvaluatorWrapper(evaluator, cache)
        result = cached.collect(project_path)
    """

    def __init__(
        self,
        evaluator,
        cache: EvaluationCache,
        source_dir: str = "src",
    ):
        """
        Initialize cached wrapper.

        Args:
            evaluator: The underlying evaluator
            cache: Evaluation cache instance
            source_dir: Source directory to track for changes
        """
        self.evaluator = evaluator
        self.cache = cache
        self.source_dir = source_dir

    @property
    def name(self) -> str:
        """Get evaluator name."""
        return self.evaluator.name

    def collect(self, project_path: str) -> EvalResult:
        """
        Run evaluation with caching.

        Returns cached result if available, otherwise runs
        the underlying evaluator and caches the result.
        """
        # Try cache first
        cached = self.cache.get(
            self.evaluator.name,
            project_path,
            self.source_dir,
        )

        if cached is not None:
            # Add cache indicator to details
            if cached.details:
                cached.details["from_cache"] = True
            return cached

        # Run actual evaluation
        result = self.evaluator.collect(project_path)

        # Cache the result
        self.cache.put(
            self.evaluator.name,
            project_path,
            result,
            self.source_dir,
        )

        return result
