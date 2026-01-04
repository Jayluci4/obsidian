"""
Universal Evaluator for Research Mode.

Implements a domain-agnostic evaluation framework:
- Correctness: Does the solution work? (gate)
- Benchmark: How well does it perform? (objective)
- Novelty: How different from existing solutions? (diversity)

The evaluation is always domain-specific in implementation,
but follows a standard interface that makes the framework domain-agnostic.
"""

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from obsidian.research.archive import SolutionArchive
    from obsidian.research.problem import ProblemSpec


@dataclass
class CorrectnessResult:
    """Result of correctness evaluation."""

    passed: bool
    score: float  # 0.0 or 1.0 for binary, or partial for multi-test
    output: str = ""
    error: str = ""
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Result of benchmark evaluation."""

    raw_score: float
    normalized_score: float  # 0.0 to 1.0
    direction: str = "maximize"
    output: str = ""
    error: str = ""
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class NoveltyResult:
    """Result of novelty evaluation."""

    score: float  # 0.0 to 1.0
    nearest_neighbors: list[str] = field(default_factory=list)
    distances: list[float] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Complete evaluation result."""

    # Overall
    score: float  # Composite score 0.0 to 1.0
    passed: bool  # Whether correctness gate passed

    # Components
    correctness: CorrectnessResult | None = None
    benchmark: BenchmarkResult | None = None
    novelty: NoveltyResult | None = None

    # Metadata
    solution_hash: str = ""
    iteration: int = 0
    timestamp: float = 0.0
    duration_ms: int = 0

    # For archive
    niche_values: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "score": self.score,
            "passed": self.passed,
            "correctness": {
                "passed": self.correctness.passed if self.correctness else False,
                "score": self.correctness.score if self.correctness else 0.0,
                "duration_ms": self.correctness.duration_ms if self.correctness else 0,
            },
            "benchmark": {
                "raw_score": self.benchmark.raw_score if self.benchmark else 0.0,
                "normalized_score": self.benchmark.normalized_score if self.benchmark else 0.0,
                "duration_ms": self.benchmark.duration_ms if self.benchmark else 0,
            },
            "novelty": {
                "score": self.novelty.score if self.novelty else 0.0,
            },
            "solution_hash": self.solution_hash,
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "niche_values": self.niche_values,
        }


class UniversalEvaluator:
    """
    Domain-agnostic evaluator that runs user-defined checks.

    The evaluator follows a standard pattern:
    1. Correctness (gate) - must pass to continue
    2. Benchmark (objective) - primary optimization target
    3. Novelty (diversity) - encourages exploration

    The actual evaluation commands are defined in the problem specification,
    making this framework applicable to any domain.
    """

    def __init__(
        self,
        problem: "ProblemSpec",
        archive: "SolutionArchive | None" = None,
        working_dir: Path | None = None,
    ):
        self.problem = problem
        self.archive = archive
        self.working_dir = working_dir or Path.cwd()

        # Normalization state
        self._min_benchmark: float | None = problem.benchmark.baseline_score
        self._max_benchmark: float | None = problem.benchmark.target_score

    def evaluate(
        self,
        solution_path: Path,
        iteration: int = 0,
    ) -> EvaluationResult:
        """
        Evaluate a solution.

        Args:
            solution_path: Path to the solution file
            iteration: Current iteration number

        Returns:
            Complete evaluation result
        """
        start_time = time.time()
        solution_hash = self._compute_hash(solution_path)

        # 1. CORRECTNESS CHECK (gate)
        correctness = self._run_correctness(solution_path)

        if not correctness.passed:
            return EvaluationResult(
                score=0.0,
                passed=False,
                correctness=correctness,
                solution_hash=solution_hash,
                iteration=iteration,
                timestamp=start_time,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        # 2. BENCHMARK (objective)
        benchmark = self._run_benchmark(solution_path)

        # 3. NOVELTY (diversity)
        novelty = self._compute_novelty(solution_path)

        # 4. EXTRACT NICHE VALUES
        niche_values = self._extract_niche_values(solution_path)

        # 5. COMPOSITE SCORE
        score = (
            self.problem.weights.correctness * correctness.score
            + self.problem.weights.benchmark * benchmark.normalized_score
            + self.problem.weights.novelty * novelty.score
        )

        return EvaluationResult(
            score=score,
            passed=True,
            correctness=correctness,
            benchmark=benchmark,
            novelty=novelty,
            solution_hash=solution_hash,
            iteration=iteration,
            timestamp=start_time,
            duration_ms=int((time.time() - start_time) * 1000),
            niche_values=niche_values,
        )

    def _run_correctness(self, solution_path: Path) -> CorrectnessResult:
        """Run correctness check."""
        config = self.problem.correctness
        start_time = time.time()

        try:
            # Substitute solution path in command
            command = config.command.format(solution=solution_path)

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=config.timeout,
                cwd=self.working_dir,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if config.type == "pytest":
                return self._parse_pytest_result(result, duration_ms)
            elif config.type == "reference":
                return self._compare_with_reference(solution_path, result, duration_ms)
            else:
                # Generic: exit code 0 = pass
                return CorrectnessResult(
                    passed=(result.returncode == 0),
                    score=1.0 if result.returncode == 0 else 0.0,
                    output=result.stdout.decode("utf-8", errors="replace"),
                    error=result.stderr.decode("utf-8", errors="replace"),
                    duration_ms=duration_ms,
                )

        except subprocess.TimeoutExpired:
            return CorrectnessResult(
                passed=False,
                score=0.0,
                error=f"Timeout after {config.timeout}s",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            return CorrectnessResult(
                passed=False,
                score=0.0,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    def _parse_pytest_result(
        self,
        result: subprocess.CompletedProcess,
        duration_ms: int,
    ) -> CorrectnessResult:
        """Parse pytest output for detailed results."""
        output = result.stdout.decode("utf-8", errors="replace")
        error = result.stderr.decode("utf-8", errors="replace")

        # Try to parse test counts from pytest output
        # Format: "X passed, Y failed, Z errors"
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        error_match = re.search(r"(\d+) error", output)

        passed_count = int(passed_match.group(1)) if passed_match else 0
        failed_count = int(failed_match.group(1)) if failed_match else 0
        error_count = int(error_match.group(1)) if error_match else 0

        total = passed_count + failed_count + error_count
        score = passed_count / total if total > 0 else 0.0

        return CorrectnessResult(
            passed=(result.returncode == 0),
            score=score,
            output=output,
            error=error,
            duration_ms=duration_ms,
            details={
                "passed": passed_count,
                "failed": failed_count,
                "errors": error_count,
                "total": total,
            },
        )

    def _compare_with_reference(
        self,
        solution_path: Path,
        result: subprocess.CompletedProcess,
        duration_ms: int,
    ) -> CorrectnessResult:
        """Compare solution output with reference implementation."""
        # The command should output both solution and reference results
        # in a comparable format
        output = result.stdout.decode("utf-8", errors="replace")

        return CorrectnessResult(
            passed=(result.returncode == 0),
            score=1.0 if result.returncode == 0 else 0.0,
            output=output,
            duration_ms=duration_ms,
        )

    def _run_benchmark(self, solution_path: Path) -> BenchmarkResult:
        """Run benchmark evaluation."""
        config = self.problem.benchmark
        start_time = time.time()

        try:
            command = config.command.format(solution=solution_path)

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=config.timeout,
                cwd=self.working_dir,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            output = result.stdout.decode("utf-8", errors="replace")
            error = result.stderr.decode("utf-8", errors="replace")

            # Parse output based on parser type
            raw_score = self._parse_benchmark_output(output, config)

            # Update normalization bounds
            if self._min_benchmark is None or raw_score < self._min_benchmark:
                self._min_benchmark = raw_score
            if self._max_benchmark is None or raw_score > self._max_benchmark:
                self._max_benchmark = raw_score

            # Normalize score to 0-1
            normalized = self._normalize_score(raw_score, config.direction)

            return BenchmarkResult(
                raw_score=raw_score,
                normalized_score=normalized,
                direction=config.direction,
                output=output,
                error=error,
                duration_ms=duration_ms,
            )

        except subprocess.TimeoutExpired:
            return BenchmarkResult(
                raw_score=0.0,
                normalized_score=0.0,
                direction=config.direction,
                error=f"Timeout after {config.timeout}s",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            return BenchmarkResult(
                raw_score=0.0,
                normalized_score=0.0,
                direction=config.direction,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    def _parse_benchmark_output(self, output: str, config: Any) -> float:
        """Parse benchmark output to extract score."""
        if config.output_parser == "json":
            # Expect JSON with "score" field
            try:
                # Try to parse the entire output as JSON first
                data = json.loads(output.strip())
                return float(data.get("score", 0.0))
            except (json.JSONDecodeError, ValueError):
                pass

            # Try to find JSON object by matching braces
            try:
                start = output.find("{")
                if start >= 0:
                    depth = 0
                    for i, c in enumerate(output[start:], start):
                        if c == "{":
                            depth += 1
                        elif c == "}":
                            depth -= 1
                            if depth == 0:
                                json_str = output[start : i + 1]
                                data = json.loads(json_str)
                                return float(data.get("score", 0.0))
            except (json.JSONDecodeError, ValueError):
                pass
            return 0.0

        elif config.output_parser == "grep":
            # Use pattern to extract score
            if config.output_pattern:
                match = re.search(config.output_pattern, output)
                if match:
                    try:
                        return float(match.group(1))
                    except (ValueError, IndexError):
                        pass
            return 0.0

        elif config.output_parser == "last_line":
            # Last non-empty line is the score
            lines = [l.strip() for l in output.strip().split("\n") if l.strip()]
            if lines:
                try:
                    return float(lines[-1])
                except ValueError:
                    pass
            return 0.0

        else:
            # Try to find any float in output
            floats = re.findall(r"[-+]?\d*\.?\d+", output)
            if floats:
                try:
                    return float(floats[-1])
                except ValueError:
                    pass
            return 0.0

    def _normalize_score(self, raw_score: float, direction: str) -> float:
        """Normalize score to 0-1 range."""
        if self._min_benchmark is None or self._max_benchmark is None:
            return 0.5  # Unknown range

        if self._min_benchmark == self._max_benchmark:
            return 0.5  # No variation

        # Normalize to 0-1
        normalized = (raw_score - self._min_benchmark) / (
            self._max_benchmark - self._min_benchmark
        )

        # Clamp to 0-1
        normalized = max(0.0, min(1.0, normalized))

        # Flip if minimizing
        if direction == "minimize":
            normalized = 1.0 - normalized

        return normalized

    def _compute_novelty(self, solution_path: Path) -> NoveltyResult:
        """Compute novelty score based on distance from archive."""
        if self.archive is None or len(self.archive) == 0:
            return NoveltyResult(score=1.0)  # First solution is maximally novel

        config = self.problem.novelty

        # Get solution content
        solution_content = solution_path.read_text()

        # Compute distances to all archived solutions
        distances = []
        neighbor_ids = []

        for solution in self.archive.get_all_solutions():
            dist = self._compute_distance(
                solution_content,
                solution.code,
                config.type,
            )
            distances.append(dist)
            neighbor_ids.append(solution.id)

        # Sort by distance
        sorted_pairs = sorted(zip(distances, neighbor_ids))

        # Novelty = average distance to k-nearest neighbors
        k = min(config.k_nearest, len(distances))
        nearest_distances = [d for d, _ in sorted_pairs[:k]]
        nearest_ids = [id for _, id in sorted_pairs[:k]]

        novelty_score = sum(nearest_distances) / k if k > 0 else 1.0

        # Normalize novelty to 0-1 (assuming max distance is 1.0)
        novelty_score = min(1.0, novelty_score)

        return NoveltyResult(
            score=novelty_score,
            nearest_neighbors=nearest_ids,
            distances=nearest_distances,
        )

    def _compute_distance(
        self,
        code1: str,
        code2: str,
        method: str,
    ) -> float:
        """Compute distance between two code snippets."""
        if method == "code_diff":
            # Simple character-level Levenshtein-like distance
            # Normalized by max length
            return self._normalized_edit_distance(code1, code2)

        elif method == "ast_diff":
            # Would require AST parsing - simplified here
            return self._normalized_edit_distance(code1, code2)

        elif method == "embedding":
            # Would require embedding model - use hash distance as proxy
            hash1 = hashlib.md5(code1.encode()).hexdigest()
            hash2 = hashlib.md5(code2.encode()).hexdigest()
            # Count differing hex chars as distance
            diff = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
            return diff / len(hash1)

        else:
            return self._normalized_edit_distance(code1, code2)

    def _normalized_edit_distance(self, s1: str, s2: str) -> float:
        """Compute normalized edit distance (simplified)."""
        # Use line-based diff for efficiency
        lines1 = s1.split("\n")
        lines2 = s2.split("\n")

        # Count different lines
        set1 = set(lines1)
        set2 = set(lines2)

        # Jaccard distance
        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        similarity = intersection / union
        return 1.0 - similarity

    def _extract_niche_values(self, solution_path: Path) -> dict[str, str]:
        """Extract niche values from solution for MAP-Elites."""
        niche_values = {}
        solution_content = solution_path.read_text()

        for niche in self.problem.archive.niches:
            if niche.extractor:
                # Run extractor command
                try:
                    result = subprocess.run(
                        niche.extractor.format(solution=solution_path),
                        shell=True,
                        capture_output=True,
                        timeout=30,
                        cwd=self.working_dir,
                    )
                    value = result.stdout.decode().strip()
                    niche_values[niche.name] = value
                except Exception:
                    niche_values[niche.name] = "unknown"
            else:
                # Heuristic extraction based on niche name
                niche_values[niche.name] = self._heuristic_niche_value(
                    solution_content, niche
                )

        return niche_values

    def _heuristic_niche_value(self, code: str, niche: Any) -> str:
        """Heuristically extract niche value from code."""
        # Simple heuristics based on common patterns
        if niche.name == "complexity":
            lines = len(code.split("\n"))
            if niche.bins:
                for i, threshold in enumerate(niche.bins[1:], 1):
                    if lines < threshold:
                        return f"bin_{i-1}"
                return f"bin_{len(niche.bins)-1}"
            return str(lines)

        elif niche.name == "approach":
            # Try to detect approach from keywords
            code_lower = code.lower()
            if niche.values:
                for value in niche.values:
                    if value.lower() in code_lower:
                        return value
            return "unknown"

        return "unknown"

    def _compute_hash(self, solution_path: Path) -> str:
        """Compute hash of solution file."""
        content = solution_path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]

    def update_archive(self, archive: "SolutionArchive") -> None:
        """Update the archive reference."""
        self.archive = archive
