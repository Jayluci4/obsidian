"""
AST-Based Code Distance Computation.

Provides structural similarity metrics using Python's AST module.
More meaningful than line-based comparison for algorithm discovery.

Features:
- Weighted AST node histograms (important nodes weighted higher)
- Cosine distance for similarity
- Fallback to line-based for unparseable code
"""

import ast
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


# Node type weights - algorithmic structures weighted higher
DEFAULT_NODE_WEIGHTS = {
    # High weight: Algorithmic structures
    "FunctionDef": 3.0,
    "AsyncFunctionDef": 3.0,
    "ClassDef": 3.0,
    "For": 2.5,
    "AsyncFor": 2.5,
    "While": 2.5,
    "If": 2.0,
    "With": 2.0,
    "AsyncWith": 2.0,
    "Try": 2.0,
    "Match": 2.0,
    # Medium weight: Operations and calls
    "Call": 1.5,
    "BinOp": 1.5,
    "UnaryOp": 1.5,
    "Compare": 1.5,
    "BoolOp": 1.5,
    "Subscript": 1.5,
    "Slice": 1.5,
    # Lower weight: Basic structures
    "Assign": 1.0,
    "AugAssign": 1.0,
    "AnnAssign": 1.0,
    "Return": 1.0,
    "Yield": 1.2,
    "YieldFrom": 1.2,
    "Raise": 1.0,
    "Assert": 1.0,
    "Import": 0.5,
    "ImportFrom": 0.5,
    "Pass": 0.1,
    "Break": 0.8,
    "Continue": 0.8,
    # Expressions
    "Lambda": 1.5,
    "ListComp": 1.5,
    "SetComp": 1.5,
    "DictComp": 1.5,
    "GeneratorExp": 1.5,
    # Literals (lower weight)
    "Constant": 0.3,
    "Name": 0.5,
    "List": 0.5,
    "Tuple": 0.5,
    "Dict": 0.5,
    "Set": 0.5,
}


@dataclass
class ASTHistogram:
    """Histogram of AST node types."""

    counts: Counter = field(default_factory=Counter)
    weighted_counts: Counter = field(default_factory=Counter)
    total_nodes: int = 0
    total_weighted: float = 0.0

    def add_node(self, node_type: str, weight: float = 1.0) -> None:
        """Add a node to the histogram."""
        self.counts[node_type] += 1
        self.weighted_counts[node_type] += weight
        self.total_nodes += 1
        self.total_weighted += weight


def compute_ast_histogram(
    code: str,
    weights: dict[str, float] | None = None,
) -> ASTHistogram | None:
    """
    Compute AST node histogram from code.

    Args:
        code: Python source code
        weights: Custom node type weights (uses defaults if None)

    Returns:
        ASTHistogram or None if parsing fails
    """
    if weights is None:
        weights = DEFAULT_NODE_WEIGHTS

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    histogram = ASTHistogram()

    for node in ast.walk(tree):
        node_type = type(node).__name__
        weight = weights.get(node_type, 1.0)
        histogram.add_node(node_type, weight)

    return histogram


def compute_ast_distance(
    code1: str,
    code2: str,
    weights: dict[str, float] | None = None,
) -> float:
    """
    Compute structural distance between two code snippets.

    Uses weighted AST node histogram cosine distance.

    Args:
        code1: First code snippet
        code2: Second code snippet
        weights: Custom node type weights

    Returns:
        Distance in [0, 1] where 0 = identical, 1 = completely different
    """
    h1 = compute_ast_histogram(code1, weights)
    h2 = compute_ast_histogram(code2, weights)

    # Fallback to line-based if AST parsing fails
    if h1 is None or h2 is None:
        return _normalized_line_distance(code1, code2)

    return _histogram_cosine_distance(h1, h2)


def compute_weighted_ast_distance(
    code1: str,
    code2: str,
    weights: dict[str, float] | None = None,
) -> float:
    """
    Compute weighted structural distance.

    Similar to compute_ast_distance but uses weighted counts.
    """
    h1 = compute_ast_histogram(code1, weights)
    h2 = compute_ast_histogram(code2, weights)

    if h1 is None or h2 is None:
        return _normalized_line_distance(code1, code2)

    return _histogram_cosine_distance(h1, h2, use_weighted=True)


def _histogram_cosine_distance(
    h1: ASTHistogram,
    h2: ASTHistogram,
    use_weighted: bool = True,
) -> float:
    """
    Compute cosine distance between two histograms.

    Cosine distance = 1 - cosine_similarity
    where cosine_similarity = (A·B) / (|A| * |B|)
    """
    if use_weighted:
        counts1 = h1.weighted_counts
        counts2 = h2.weighted_counts
    else:
        counts1 = h1.counts
        counts2 = h2.counts

    # Get all node types
    all_types = set(counts1.keys()) | set(counts2.keys())

    if not all_types:
        return 0.0

    # Compute dot product and magnitudes
    dot_product = 0.0
    mag1_sq = 0.0
    mag2_sq = 0.0

    for node_type in all_types:
        v1 = counts1.get(node_type, 0)
        v2 = counts2.get(node_type, 0)

        dot_product += v1 * v2
        mag1_sq += v1 * v1
        mag2_sq += v2 * v2

    mag1 = mag1_sq**0.5
    mag2 = mag2_sq**0.5

    if mag1 == 0 or mag2 == 0:
        return 1.0

    cosine_similarity = dot_product / (mag1 * mag2)

    # Clamp to [0, 1] due to floating point errors
    cosine_similarity = max(0.0, min(1.0, cosine_similarity))

    return 1.0 - cosine_similarity


def _normalized_line_distance(code1: str, code2: str) -> float:
    """
    Fallback line-based Jaccard distance.

    Used when AST parsing fails.
    """
    lines1 = set(line.strip() for line in code1.split("\n") if line.strip())
    lines2 = set(line.strip() for line in code2.split("\n") if line.strip())

    if not lines1 and not lines2:
        return 0.0

    intersection = len(lines1 & lines2)
    union = len(lines1 | lines2)

    if union == 0:
        return 0.0

    return 1.0 - (intersection / union)


class ASTNoveltyComputer:
    """
    Computes novelty scores using AST-based distance.

    Used by UniversalEvaluator for novelty component.
    """

    def __init__(
        self,
        node_weights: dict[str, float] | None = None,
        k_nearest: int = 5,
    ):
        self.node_weights = node_weights or DEFAULT_NODE_WEIGHTS
        self.k_nearest = k_nearest

        # Cache histograms for archived solutions
        self._histogram_cache: dict[str, ASTHistogram] = {}

    def compute_novelty(
        self,
        code: str,
        archive_codes: list[str],
    ) -> float:
        """
        Compute novelty score for code against archive.

        Args:
            code: New solution code
            archive_codes: List of existing solution codes

        Returns:
            Novelty score in [0, 1] where 1 = maximally novel
        """
        if not archive_codes:
            return 1.0  # First solution is maximally novel

        # Compute distances to all archive solutions
        distances = []
        for archive_code in archive_codes:
            dist = compute_weighted_ast_distance(
                code,
                archive_code,
                self.node_weights,
            )
            distances.append(dist)

        # k-nearest neighbor novelty
        k = min(self.k_nearest, len(distances))
        nearest_distances = sorted(distances)[:k]

        # Average distance to k nearest neighbors
        novelty = sum(nearest_distances) / k

        return min(1.0, novelty)

    def get_histogram(self, code: str) -> ASTHistogram | None:
        """Get or compute histogram for code (with caching by hash)."""
        code_hash = hash(code)

        if code_hash not in self._histogram_cache:
            histogram = compute_ast_histogram(code, self.node_weights)
            if histogram:
                self._histogram_cache[code_hash] = histogram

        return self._histogram_cache.get(code_hash)

    def clear_cache(self) -> None:
        """Clear histogram cache."""
        self._histogram_cache.clear()

    def get_structural_summary(self, code: str) -> dict[str, Any]:
        """
        Get structural summary of code for analysis.

        Useful for understanding what makes solutions different.
        """
        histogram = self.get_histogram(code)

        if histogram is None:
            return {"error": "Could not parse code"}

        # Top node types by weighted count
        top_types = histogram.weighted_counts.most_common(10)

        # Structural metrics
        control_flow = sum(
            histogram.counts.get(t, 0) for t in ["If", "For", "While", "With", "Try"]
        )
        function_defs = sum(
            histogram.counts.get(t, 0) for t in ["FunctionDef", "AsyncFunctionDef", "Lambda"]
        )
        comprehensions = sum(
            histogram.counts.get(t, 0)
            for t in ["ListComp", "SetComp", "DictComp", "GeneratorExp"]
        )

        return {
            "total_nodes": histogram.total_nodes,
            "total_weighted": histogram.total_weighted,
            "top_node_types": dict(top_types),
            "control_flow_count": control_flow,
            "function_count": function_defs,
            "comprehension_count": comprehensions,
            "complexity_estimate": control_flow + function_defs * 2,
        }
