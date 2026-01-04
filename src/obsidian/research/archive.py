"""
Solution Archive with Quality-Diversity (MAP-Elites).

Implements the solution archive that stores discovered algorithms:
- Quality-Diversity: Keep best solution in each niche
- MAP-Elites: Multi-dimensional archive of phenotypic elites
- Persistence: SQLite-backed storage for long-running experiments
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from obsidian.research.problem import ArchiveConfig, NicheDefinition


@dataclass
class Solution:
    """A solution stored in the archive."""

    id: str
    code: str
    score: float
    niche_key: str  # Tuple of niche values as string
    niche_values: dict[str, str]
    iteration: int
    timestamp: float
    parent_ids: list[str] = field(default_factory=list)
    operation: str = ""  # mutate, crossover, explore, exploit
    evaluation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "code": self.code,
            "score": self.score,
            "niche_key": self.niche_key,
            "niche_values": self.niche_values,
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "parent_ids": self.parent_ids,
            "operation": self.operation,
            "evaluation": self.evaluation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Solution":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            code=data["code"],
            score=data["score"],
            niche_key=data["niche_key"],
            niche_values=data.get("niche_values", {}),
            iteration=data.get("iteration", 0),
            timestamp=data.get("timestamp", 0.0),
            parent_ids=data.get("parent_ids", []),
            operation=data.get("operation", ""),
            evaluation=data.get("evaluation", {}),
        )


@dataclass
class Niche:
    """A niche in the MAP-Elites archive."""

    key: str
    values: dict[str, str]
    solutions: list[Solution] = field(default_factory=list)
    best_score: float = 0.0
    best_solution_id: str | None = None

    def add_solution(self, solution: Solution, max_per_niche: int = 5) -> bool:
        """
        Add solution to niche if it improves the archive.

        Returns:
            True if solution was added
        """
        # Check if this solution is better than existing ones
        if solution.score > self.best_score:
            self.best_score = solution.score
            self.best_solution_id = solution.id

        # Add to niche
        self.solutions.append(solution)

        # Prune if over capacity
        if len(self.solutions) > max_per_niche:
            # Keep top solutions by score
            self.solutions.sort(key=lambda s: s.score, reverse=True)
            self.solutions = self.solutions[:max_per_niche]
            return solution in self.solutions

        return True

    def get_best(self) -> Solution | None:
        """Get best solution in niche."""
        if not self.solutions:
            return None
        return max(self.solutions, key=lambda s: s.score)


class SolutionArchive:
    """
    Quality-Diversity archive using MAP-Elites.

    The archive maintains a grid of niches, where each niche
    represents a different region of the behavioral/phenotypic space.
    Each niche keeps the best solutions found in that region.
    """

    def __init__(
        self,
        config: ArchiveConfig,
        db_path: Path | None = None,
    ):
        self.config = config
        self.db_path = db_path

        # In-memory storage
        self.niches: dict[str, Niche] = {}
        self.all_solutions: dict[str, Solution] = {}

        # Stats
        self.total_added = 0
        self.total_rejected = 0

        # Initialize database if path provided
        if db_path:
            self._init_database()
            self._load_from_database()

    def _init_database(self) -> None:
        """Initialize SQLite database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS solutions (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    score REAL NOT NULL,
                    niche_key TEXT NOT NULL,
                    niche_values TEXT,
                    iteration INTEGER,
                    timestamp REAL,
                    parent_ids TEXT,
                    operation TEXT,
                    evaluation TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_niche_key
                ON solutions(niche_key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_score
                ON solutions(score DESC)
            """)
            conn.commit()

    def _load_from_database(self) -> None:
        """Load solutions from database."""
        if not self.db_path or not self.db_path.exists():
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, code, score, niche_key, niche_values,
                       iteration, timestamp, parent_ids, operation, evaluation
                FROM solutions
            """)

            for row in cursor:
                solution = Solution(
                    id=row[0],
                    code=row[1],
                    score=row[2],
                    niche_key=row[3],
                    niche_values=json.loads(row[4]) if row[4] else {},
                    iteration=row[5] or 0,
                    timestamp=row[6] or 0.0,
                    parent_ids=json.loads(row[7]) if row[7] else [],
                    operation=row[8] or "",
                    evaluation=json.loads(row[9]) if row[9] else {},
                )
                self._add_to_memory(solution)

    def _save_to_database(self, solution: Solution) -> None:
        """Save solution to database."""
        if not self.db_path:
            return

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO solutions
                (id, code, score, niche_key, niche_values,
                 iteration, timestamp, parent_ids, operation, evaluation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    solution.id,
                    solution.code,
                    solution.score,
                    solution.niche_key,
                    json.dumps(solution.niche_values),
                    solution.iteration,
                    solution.timestamp,
                    json.dumps(solution.parent_ids),
                    solution.operation,
                    json.dumps(solution.evaluation),
                ),
            )
            conn.commit()

    def _add_to_memory(self, solution: Solution) -> bool:
        """Add solution to in-memory structures."""
        # Get or create niche
        if solution.niche_key not in self.niches:
            self.niches[solution.niche_key] = Niche(
                key=solution.niche_key,
                values=solution.niche_values,
            )

        niche = self.niches[solution.niche_key]

        # Add to niche
        added = niche.add_solution(
            solution,
            max_per_niche=self.config.max_solutions_per_niche,
        )

        if added:
            self.all_solutions[solution.id] = solution

        return added

    def add(
        self,
        code: str,
        score: float,
        niche_values: dict[str, str],
        iteration: int = 0,
        parent_ids: list[str] | None = None,
        operation: str = "",
        evaluation: dict[str, Any] | None = None,
    ) -> Solution | None:
        """
        Add a solution to the archive.

        Args:
            code: Solution source code
            score: Evaluation score
            niche_values: Dict of niche dimension -> value
            iteration: Iteration when created
            parent_ids: IDs of parent solutions (for lineage)
            operation: Operation used to create (mutate, crossover, etc.)
            evaluation: Full evaluation results

        Returns:
            Solution if added, None if rejected
        """
        # Generate niche key from values
        niche_key = self._compute_niche_key(niche_values)

        # Generate solution ID
        solution_id = f"sol_{iteration}_{int(time.time() * 1000) % 100000}"

        solution = Solution(
            id=solution_id,
            code=code,
            score=score,
            niche_key=niche_key,
            niche_values=niche_values,
            iteration=iteration,
            timestamp=time.time(),
            parent_ids=parent_ids or [],
            operation=operation,
            evaluation=evaluation or {},
        )

        # Add to memory
        added = self._add_to_memory(solution)

        if added:
            self.total_added += 1
            self._save_to_database(solution)
            return solution
        else:
            self.total_rejected += 1
            return None

    def _compute_niche_key(self, niche_values: dict[str, str]) -> str:
        """Compute niche key from values."""
        # Sort by niche name for consistency
        sorted_items = sorted(niche_values.items())
        return "|".join(f"{k}:{v}" for k, v in sorted_items)

    def get_solution(self, solution_id: str) -> Solution | None:
        """Get solution by ID."""
        return self.all_solutions.get(solution_id)

    def get_best_in_niche(self, niche_key: str) -> Solution | None:
        """Get best solution in a niche."""
        niche = self.niches.get(niche_key)
        if niche:
            return niche.get_best()
        return None

    def get_all_solutions(self) -> list[Solution]:
        """Get all solutions in archive."""
        return list(self.all_solutions.values())

    def get_top_k(self, k: int = 10) -> list[Solution]:
        """Get top K solutions by score."""
        solutions = list(self.all_solutions.values())
        solutions.sort(key=lambda s: s.score, reverse=True)
        return solutions[:k]

    def get_diverse_sample(self, n: int = 5) -> list[Solution]:
        """Get diverse sample from different niches."""
        samples = []
        niches = list(self.niches.values())

        # Round-robin from niches
        niche_idx = 0
        while len(samples) < n and niches:
            niche = niches[niche_idx % len(niches)]
            best = niche.get_best()
            if best and best not in samples:
                samples.append(best)
            niche_idx += 1

            # Avoid infinite loop
            if niche_idx >= len(niches) * 2:
                break

        return samples

    def get_parents_for_crossover(self) -> tuple[Solution, Solution] | None:
        """Select two parents for crossover operation."""
        if len(self.all_solutions) < 2:
            return None

        solutions = list(self.all_solutions.values())

        # Tournament selection
        tournament_size = min(3, len(solutions))

        import random

        # Select first parent
        tournament1 = random.sample(solutions, tournament_size)
        parent1 = max(tournament1, key=lambda s: s.score)

        # Select second parent (different niche preferred)
        other_solutions = [s for s in solutions if s.niche_key != parent1.niche_key]
        if not other_solutions:
            other_solutions = [s for s in solutions if s.id != parent1.id]

        if not other_solutions:
            return None

        tournament2 = random.sample(
            other_solutions,
            min(tournament_size, len(other_solutions)),
        )
        parent2 = max(tournament2, key=lambda s: s.score)

        return (parent1, parent2)

    def get_parent_for_mutation(self) -> Solution | None:
        """Select parent for mutation operation."""
        if not self.all_solutions:
            return None

        solutions = list(self.all_solutions.values())

        import random

        # Tournament selection
        tournament_size = min(3, len(solutions))
        tournament = random.sample(solutions, tournament_size)

        return max(tournament, key=lambda s: s.score)

    def get_best_for_exploitation(self) -> Solution | None:
        """Get best solution for exploitation."""
        if not self.all_solutions:
            return None

        return max(self.all_solutions.values(), key=lambda s: s.score)

    def get_underexplored_niche(self) -> dict[str, str] | None:
        """Find an underexplored niche for exploration."""
        if not self.config.niches:
            return None

        # Generate all possible niche combinations
        all_niche_keys = self._generate_all_niche_keys()

        # Find niches with no solutions
        empty_niches = [k for k in all_niche_keys if k not in self.niches]

        if empty_niches:
            import random

            key = random.choice(empty_niches)
            return self._parse_niche_key(key)

        # Find niches with fewest solutions
        min_count = min(len(n.solutions) for n in self.niches.values())
        underexplored = [k for k, n in self.niches.items() if len(n.solutions) == min_count]

        if underexplored:
            import random

            key = random.choice(underexplored)
            return self._parse_niche_key(key)

        return None

    def _generate_all_niche_keys(self) -> list[str]:
        """Generate all possible niche key combinations."""
        if not self.config.niches:
            return []

        # Get all values for each dimension
        dimension_values: list[list[tuple[str, str]]] = []

        for niche_def in self.config.niches:
            if niche_def.type == "categorical" and niche_def.values:
                dimension_values.append([(niche_def.name, v) for v in niche_def.values])
            elif niche_def.type == "continuous" and niche_def.bins:
                bin_names = [f"bin_{i}" for i in range(len(niche_def.bins))]
                dimension_values.append([(niche_def.name, b) for b in bin_names])

        if not dimension_values:
            return []

        # Generate cartesian product
        import itertools

        all_combinations = list(itertools.product(*dimension_values))

        # Convert to niche keys
        keys = []
        for combo in all_combinations:
            niche_values = dict(combo)
            keys.append(self._compute_niche_key(niche_values))

        return keys

    def _parse_niche_key(self, key: str) -> dict[str, str]:
        """Parse niche key back to values dict."""
        values = {}
        for part in key.split("|"):
            if ":" in part:
                k, v = part.split(":", 1)
                values[k] = v
        return values

    def get_stats(self) -> dict[str, Any]:
        """Get archive statistics."""
        if not self.all_solutions:
            return {
                "total_solutions": 0,
                "total_niches": 0,
                "best_score": 0.0,
                "avg_score": 0.0,
                "total_added": self.total_added,
                "total_rejected": self.total_rejected,
            }

        scores = [s.score for s in self.all_solutions.values()]

        return {
            "total_solutions": len(self.all_solutions),
            "total_niches": len(self.niches),
            "best_score": max(scores),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "total_added": self.total_added,
            "total_rejected": self.total_rejected,
            "coverage": len(self.niches) / max(1, len(self._generate_all_niche_keys())),
        }

    def __len__(self) -> int:
        """Return number of solutions."""
        return len(self.all_solutions)

    def __iter__(self) -> Iterator[Solution]:
        """Iterate over solutions."""
        return iter(self.all_solutions.values())

    def save_checkpoint(self, path: Path) -> None:
        """Save archive to checkpoint file."""
        data = {
            "config": {
                "type": self.config.type,
                "max_solutions_per_niche": self.config.max_solutions_per_niche,
                "max_total_solutions": self.config.max_total_solutions,
            },
            "solutions": [s.to_dict() for s in self.all_solutions.values()],
            "stats": self.get_stats(),
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_checkpoint(self, path: Path) -> None:
        """Load archive from checkpoint file."""
        if not path.exists():
            return

        with open(path) as f:
            data = json.load(f)

        for solution_data in data.get("solutions", []):
            solution = Solution.from_dict(solution_data)
            self._add_to_memory(solution)
