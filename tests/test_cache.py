"""Tests for the evaluation cache module."""

import tempfile
import time
from pathlib import Path

import pytest

from obsidian.evaluator import (
    EvalResult,
    EvaluationCache,
    CachedEvaluatorWrapper,
    CacheEntry,
    CacheStats,
    compute_file_hash,
    compute_directory_hash,
)


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_hash_file(self):
        """Test hashing a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('hello')")
            f.flush()
            path = Path(f.name)

        try:
            hash1 = compute_file_hash(path)
            assert hash1 != ""
            assert len(hash1) == 32  # MD5 hex length
        finally:
            path.unlink()

    def test_same_content_same_hash(self):
        """Test that same content produces same hash."""
        content = "def foo(): pass"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f1:
            f1.write(content)
            f1.flush()
            path1 = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f2:
            f2.write(content)
            f2.flush()
            path2 = Path(f2.name)

        try:
            assert compute_file_hash(path1) == compute_file_hash(path2)
        finally:
            path1.unlink()
            path2.unlink()

    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f1:
            f1.write("version = 1")
            f1.flush()
            path1 = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f2:
            f2.write("version = 2")
            f2.flush()
            path2 = Path(f2.name)

        try:
            assert compute_file_hash(path1) != compute_file_hash(path2)
        finally:
            path1.unlink()
            path2.unlink()

    def test_nonexistent_file(self):
        """Test hashing nonexistent file returns empty string."""
        result = compute_file_hash(Path("/nonexistent/file.py"))
        assert result == ""


class TestComputeDirectoryHash:
    """Tests for compute_directory_hash function."""

    def test_hash_directory(self):
        """Test hashing a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "test.py").write_text("code here")

            hash1 = compute_directory_hash(path)

            assert hash1 != ""
            assert len(hash1) == 32

    def test_excludes_pycache(self):
        """Test that __pycache__ is excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "test.py").write_text("code")

            hash1 = compute_directory_hash(path)

            # Add __pycache__
            pycache = path / "__pycache__"
            pycache.mkdir()
            (pycache / "test.cpython-311.pyc").write_bytes(b"compiled")

            hash2 = compute_directory_hash(path)

            assert hash1 == hash2

    def test_change_detection(self):
        """Test that file changes are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            test_file = path / "test.py"
            test_file.write_text("version = 1")

            hash1 = compute_directory_hash(path)

            # Modify file
            test_file.write_text("version = 2")

            hash2 = compute_directory_hash(path)

            assert hash1 != hash2

    def test_file_addition_detection(self):
        """Test that new files are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "a.py").write_text("a")

            hash1 = compute_directory_hash(path)

            # Add file
            (path / "b.py").write_text("b")

            hash2 = compute_directory_hash(path)

            assert hash1 != hash2


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=75, misses=25)
        assert stats.hit_rate == 0.75

    def test_hit_rate_zero_operations(self):
        """Test hit rate with no operations."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_creation(self):
        """Test creating CacheEntry."""
        entry = CacheEntry(
            evaluator_name="pytest",
            file_hash="abc123",
            result={"name": "pytest", "score": 0.9},
            timestamp=time.time(),
            project_path="/test",
        )

        assert entry.evaluator_name == "pytest"
        assert entry.file_hash == "abc123"


class TestEvaluationCache:
    """Tests for EvaluationCache."""

    def create_test_result(self, name="pytest", score=0.8):
        """Create a test EvalResult."""
        return EvalResult(
            name=name,
            score=score,
            passed=score >= 0.5,
            details={"test": True},
        )

    def test_cache_disabled(self):
        """Test that disabled cache always misses."""
        cache = EvaluationCache(enabled=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "test.py").write_text("code")

            result = cache.get("pytest", str(path))
            assert result is None

            stats = cache.get_stats()
            assert stats["misses"] == 1
            assert stats["enabled"] is False

    def test_cache_miss_then_hit(self):
        """Test cache miss followed by hit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            cache = EvaluationCache(cache_dir=cache_dir)

            # First access - miss
            result1 = cache.get("pytest", str(project_dir), source_dir=".")
            assert result1 is None

            # Store result
            test_result = self.create_test_result()
            cache.put("pytest", str(project_dir), test_result, source_dir=".")

            # Second access - hit
            result2 = cache.get("pytest", str(project_dir), source_dir=".")
            assert result2 is not None
            assert result2.name == "pytest"
            assert result2.score == 0.8

    def test_cache_invalidation_on_change(self):
        """Test that cache is invalidated when files change."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            test_file = project_dir / "test.py"
            test_file.write_text("version = 1")

            cache = EvaluationCache(cache_dir=cache_dir)

            # Store result
            test_result = self.create_test_result()
            cache.put("pytest", str(project_dir), test_result, source_dir=".")

            # Verify cache hit
            result = cache.get("pytest", str(project_dir), source_dir=".")
            assert result is not None

            # Change file
            test_file.write_text("version = 2")

            # Should now miss
            result = cache.get("pytest", str(project_dir), source_dir=".")
            assert result is None

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            # Very short TTL
            cache = EvaluationCache(cache_dir=cache_dir, ttl_seconds=1)

            # Store result
            test_result = self.create_test_result()
            cache.put("pytest", str(project_dir), test_result, source_dir=".")

            # Immediate access - hit
            result = cache.get("pytest", str(project_dir), source_dir=".")
            assert result is not None

            # Wait for expiration
            time.sleep(1.1)

            # Should now miss due to TTL
            result = cache.get("pytest", str(project_dir), source_dir=".")
            assert result is None

    def test_cache_persistence(self):
        """Test that cache persists to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            # Create cache and store result
            cache1 = EvaluationCache(cache_dir=cache_dir)
            test_result = self.create_test_result()
            cache1.put("pytest", str(project_dir), test_result, source_dir=".")

            # Create new cache instance (simulating restart)
            cache2 = EvaluationCache(cache_dir=cache_dir)

            # Should still hit
            result = cache2.get("pytest", str(project_dir), source_dir=".")
            assert result is not None
            assert result.score == 0.8

    def test_invalidate_specific_evaluator(self):
        """Test invalidating specific evaluator cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            cache = EvaluationCache(cache_dir=cache_dir)

            # Store results for two evaluators
            cache.put("pytest", str(project_dir), self.create_test_result("pytest"), ".")
            cache.put("coverage", str(project_dir), self.create_test_result("coverage"), ".")

            # Invalidate only pytest
            count = cache.invalidate("pytest")
            assert count == 1

            # Pytest should miss
            assert cache.get("pytest", str(project_dir), ".") is None

            # Coverage should still hit
            assert cache.get("coverage", str(project_dir), ".") is not None

    def test_invalidate_all(self):
        """Test invalidating all cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            cache = EvaluationCache(cache_dir=cache_dir)

            cache.put("pytest", str(project_dir), self.create_test_result("pytest"), ".")
            cache.put("coverage", str(project_dir), self.create_test_result("coverage"), ".")

            count = cache.invalidate()  # All
            assert count == 2

    def test_max_entries_eviction(self):
        """Test that old entries are evicted when at capacity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = EvaluationCache(max_entries=2)

            # Store 3 entries for same evaluator
            for i in range(3):
                cache._cache.setdefault("pytest", {})
                cache._cache["pytest"][f"hash_{i}"] = CacheEntry(
                    evaluator_name="pytest",
                    file_hash=f"hash_{i}",
                    result={"score": i},
                    timestamp=time.time() + i,
                    project_path="/test",
                )

            # Force eviction by putting new entry
            project_dir = Path(tmpdir)
            (project_dir / "test.py").write_text("code")
            cache.put("pytest", str(project_dir), self.create_test_result(), ".")

            stats = cache.get_stats()
            assert stats["total_entries"] <= 3  # May have evicted

    def test_clear(self):
        """Test clearing all cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            cache = EvaluationCache(cache_dir=cache_dir)
            cache.put("pytest", str(project_dir), self.create_test_result(), ".")

            cache.clear()

            stats = cache.get_stats()
            assert stats["total_entries"] == 0
            assert stats["hits"] == 0
            assert stats["misses"] == 0


class MockEvaluator:
    """Mock evaluator for testing CachedEvaluatorWrapper."""

    def __init__(self, name="mock"):
        self.name = name
        self.call_count = 0

    def collect(self, project_path: str) -> EvalResult:
        """Run mock evaluation."""
        self.call_count += 1
        return EvalResult(
            name=self.name,
            score=0.9,
            passed=True,
            details={"call_count": self.call_count},
        )


class TestCachedEvaluatorWrapper:
    """Tests for CachedEvaluatorWrapper."""

    def test_caches_result(self):
        """Test that wrapper caches results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            cache = EvaluationCache(cache_dir=cache_dir)
            evaluator = MockEvaluator()
            wrapper = CachedEvaluatorWrapper(evaluator, cache, source_dir=".")

            # First call - runs evaluator
            result1 = wrapper.collect(str(project_dir))
            assert result1.score == 0.9
            assert evaluator.call_count == 1

            # Second call - uses cache
            result2 = wrapper.collect(str(project_dir))
            assert result2.score == 0.9
            assert evaluator.call_count == 1  # Not incremented

    def test_cache_indicates_source(self):
        """Test that cached results indicate they're from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / "test.py").write_text("code")

            cache = EvaluationCache(cache_dir=cache_dir)
            evaluator = MockEvaluator()
            wrapper = CachedEvaluatorWrapper(evaluator, cache, source_dir=".")

            # First call
            wrapper.collect(str(project_dir))

            # Second call - from cache
            result = wrapper.collect(str(project_dir))
            assert result.details.get("from_cache") is True

    def test_evaluates_on_change(self):
        """Test that evaluator runs when files change."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            test_file = project_dir / "test.py"
            test_file.write_text("version = 1")

            cache = EvaluationCache(cache_dir=cache_dir)
            evaluator = MockEvaluator()
            wrapper = CachedEvaluatorWrapper(evaluator, cache, source_dir=".")

            # First call
            wrapper.collect(str(project_dir))
            assert evaluator.call_count == 1

            # Change file
            test_file.write_text("version = 2")

            # Second call - should run evaluator again
            wrapper.collect(str(project_dir))
            assert evaluator.call_count == 2

    def test_name_property(self):
        """Test that name property delegates to evaluator."""
        evaluator = MockEvaluator(name="test_eval")
        wrapper = CachedEvaluatorWrapper(evaluator, EvaluationCache(enabled=False))

        assert wrapper.name == "test_eval"
