"""
Lineage Tracking for Solution Archive.

Tracks and analyzes solution lineages (family trees) to:
- Identify successful lineages that consistently improve
- Find stagnant lineages that should be abandoned
- Suggest cross-pollination between successful lineages
- Guide operation selection based on lineage patterns
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from obsidian.research.archive import Solution, SolutionArchive


@dataclass
class LineageNode:
    """A node in the lineage tree."""

    solution_id: str
    score: float
    iteration: int
    operation: str
    parent_ids: list[str]
    children_ids: list[str] = field(default_factory=list)
    depth: int = 0


@dataclass
class LineageStats:
    """Statistics for a lineage (rooted at a solution)."""

    root_id: str
    root_score: float
    best_score: float
    avg_score: float
    total_descendants: int
    max_depth: int
    total_improvement: float  # Sum of score improvements along lineage
    improvement_rate: float  # Avg improvement per generation
    is_active: bool  # Has recent descendants


class LineageTracker:
    """
    Tracks and analyzes solution lineages.

    Builds family trees from parent_ids and provides analytics
    for lineage-aware evolution operations.
    """

    def __init__(self, archive: "SolutionArchive"):
        self.archive = archive
        self._nodes: dict[str, LineageNode] = {}
        self._roots: list[str] = []
        self._build_tree()

    def _build_tree(self) -> None:
        """Build lineage tree from archive."""
        # Create nodes for all solutions
        for sol in self.archive.get_all_solutions():
            node = LineageNode(
                solution_id=sol.id,
                score=sol.score,
                iteration=sol.iteration,
                operation=sol.operation,
                parent_ids=sol.parent_ids,
            )
            self._nodes[sol.id] = node

        # Build parent-child relationships
        for sol_id, node in self._nodes.items():
            for parent_id in node.parent_ids:
                if parent_id in self._nodes:
                    self._nodes[parent_id].children_ids.append(sol_id)

        # Identify roots (solutions with no parents)
        self._roots = [
            sol_id
            for sol_id, node in self._nodes.items()
            if not node.parent_ids or all(p not in self._nodes for p in node.parent_ids)
        ]

        # Compute depths
        self._compute_depths()

    def _compute_depths(self) -> None:
        """Compute depth of each node from its root."""
        visited = set()

        def dfs(node_id: str, depth: int) -> None:
            if node_id in visited:
                return
            visited.add(node_id)

            node = self._nodes.get(node_id)
            if node:
                node.depth = depth
                for child_id in node.children_ids:
                    dfs(child_id, depth + 1)

        for root_id in self._roots:
            dfs(root_id, 0)

    def get_lineage_stats(self, root_id: str) -> LineageStats | None:
        """Get statistics for a lineage rooted at given solution."""
        if root_id not in self._nodes:
            return None

        root = self._nodes[root_id]
        descendants = self._get_descendants(root_id)

        if not descendants:
            return LineageStats(
                root_id=root_id,
                root_score=root.score,
                best_score=root.score,
                avg_score=root.score,
                total_descendants=0,
                max_depth=0,
                total_improvement=0.0,
                improvement_rate=0.0,
                is_active=False,
            )

        scores = [self._nodes[d].score for d in descendants]
        depths = [self._nodes[d].depth for d in descendants]
        max_depth = max(depths) - root.depth

        # Compute improvement along lineage
        total_improvement = 0.0
        for desc_id in descendants:
            desc = self._nodes[desc_id]
            if desc.parent_ids:
                parent_scores = [
                    self._nodes[p].score
                    for p in desc.parent_ids
                    if p in self._nodes
                ]
                if parent_scores:
                    avg_parent = sum(parent_scores) / len(parent_scores)
                    total_improvement += desc.score - avg_parent

        # Check if lineage is active (has recent solutions)
        max_iteration = max(self._nodes[d].iteration for d in descendants)
        all_iterations = [sol.iteration for sol in self.archive.get_all_solutions()]
        recent_threshold = max(all_iterations) - 10 if all_iterations else 0
        is_active = max_iteration >= recent_threshold

        return LineageStats(
            root_id=root_id,
            root_score=root.score,
            best_score=max(scores),
            avg_score=sum(scores) / len(scores),
            total_descendants=len(descendants),
            max_depth=max_depth,
            total_improvement=total_improvement,
            improvement_rate=total_improvement / max(1, len(descendants)),
            is_active=is_active,
        )

    def _get_descendants(self, node_id: str) -> list[str]:
        """Get all descendants of a node."""
        descendants = []
        visited = set()

        def dfs(nid: str) -> None:
            if nid in visited or nid not in self._nodes:
                return
            visited.add(nid)

            node = self._nodes[nid]
            for child_id in node.children_ids:
                descendants.append(child_id)
                dfs(child_id)

        dfs(node_id)
        return descendants

    def get_successful_lineages(
        self,
        min_improvement: float = 0.05,
        min_descendants: int = 2,
    ) -> list[LineageStats]:
        """
        Find lineages that consistently improve.

        Args:
            min_improvement: Minimum total improvement
            min_descendants: Minimum number of descendants

        Returns:
            List of successful lineage stats, sorted by improvement rate
        """
        successful = []

        for root_id in self._roots:
            stats = self.get_lineage_stats(root_id)
            if stats and stats.total_descendants >= min_descendants:
                if stats.total_improvement >= min_improvement:
                    successful.append(stats)

        return sorted(successful, key=lambda s: s.improvement_rate, reverse=True)

    def get_stagnant_lineages(
        self,
        max_improvement: float = 0.01,
        min_descendants: int = 3,
    ) -> list[LineageStats]:
        """
        Find lineages that stopped improving.

        Args:
            max_improvement: Maximum total improvement (below this = stagnant)
            min_descendants: Minimum descendants to be considered

        Returns:
            List of stagnant lineage stats
        """
        stagnant = []

        for root_id in self._roots:
            stats = self.get_lineage_stats(root_id)
            if stats and stats.total_descendants >= min_descendants:
                if stats.total_improvement <= max_improvement:
                    stagnant.append(stats)

        return stagnant

    def suggest_crossover_pairs(
        self,
        min_improvement_diff: float = 0.1,
    ) -> list[tuple[str, str]]:
        """
        Suggest pairs for cross-pollination between lineages.

        Pairs solutions from different successful lineages that
        might benefit from combination.

        Returns:
            List of (solution_id, solution_id) pairs
        """
        successful = self.get_successful_lineages()

        if len(successful) < 2:
            return []

        pairs = []

        # Pair best solutions from different successful lineages
        for i, lineage1 in enumerate(successful):
            for lineage2 in successful[i + 1 :]:
                # Get best solution from each lineage
                best1 = self._get_best_in_lineage(lineage1.root_id)
                best2 = self._get_best_in_lineage(lineage2.root_id)

                if best1 and best2:
                    pairs.append((best1, best2))

        return pairs[:10]  # Limit to 10 suggestions

    def _get_best_in_lineage(self, root_id: str) -> str | None:
        """Get ID of best solution in lineage."""
        descendants = [root_id] + self._get_descendants(root_id)
        if not descendants:
            return None

        best_id = max(
            descendants,
            key=lambda d: self._nodes[d].score if d in self._nodes else 0,
        )
        return best_id

    def get_lineage_path(self, solution_id: str) -> list[str]:
        """
        Get path from root to solution.

        Returns:
            List of solution IDs from root to target
        """
        if solution_id not in self._nodes:
            return []

        path = [solution_id]
        current = self._nodes[solution_id]

        while current.parent_ids:
            # Find parent that's in our nodes
            parent_id = None
            for pid in current.parent_ids:
                if pid in self._nodes:
                    parent_id = pid
                    break

            if not parent_id:
                break

            path.append(parent_id)
            current = self._nodes[parent_id]

        return list(reversed(path))

    def get_operation_effectiveness_by_lineage(self) -> dict[str, dict[str, float]]:
        """
        Analyze which operations are effective in which lineages.

        Returns:
            Dict of lineage_id -> {operation -> avg_improvement}
        """
        effectiveness: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for node_id, node in self._nodes.items():
            if not node.parent_ids or not node.operation:
                continue

            # Find root of this lineage
            root_id = self.get_lineage_path(node_id)[0] if node_id in self._nodes else None
            if not root_id:
                continue

            # Compute improvement from parent
            parent_scores = [
                self._nodes[p].score for p in node.parent_ids if p in self._nodes
            ]
            if parent_scores:
                avg_parent = sum(parent_scores) / len(parent_scores)
                improvement = node.score - avg_parent
                effectiveness[root_id][node.operation].append(improvement)

        # Compute averages
        result = {}
        for root_id, ops in effectiveness.items():
            result[root_id] = {
                op: sum(imps) / len(imps) if imps else 0.0 for op, imps in ops.items()
            }

        return result

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all lineages."""
        total_roots = len(self._roots)
        all_stats = [self.get_lineage_stats(r) for r in self._roots]
        valid_stats = [s for s in all_stats if s]

        successful = self.get_successful_lineages()
        stagnant = self.get_stagnant_lineages()

        return {
            "total_lineages": total_roots,
            "successful_lineages": len(successful),
            "stagnant_lineages": len(stagnant),
            "active_lineages": sum(1 for s in valid_stats if s.is_active),
            "avg_lineage_depth": (
                sum(s.max_depth for s in valid_stats) / len(valid_stats)
                if valid_stats
                else 0
            ),
            "avg_improvement_rate": (
                sum(s.improvement_rate for s in valid_stats) / len(valid_stats)
                if valid_stats
                else 0
            ),
            "best_lineage": (
                max(valid_stats, key=lambda s: s.improvement_rate).root_id
                if valid_stats
                else None
            ),
        }
