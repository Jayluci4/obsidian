#!/usr/bin/env python3
"""
Benchmark for 4x4 Matrix Multiplication

Counts the number of scalar multiplications in the algorithm.

Scoring:
- 64 multiplications (standard): 0.0 score
- 49 multiplications (Strassen): 0.8 score
- 47 multiplications (AlphaTensor mod 2 level): 0.95 score
- <47 multiplications: 1.0 score (breakthrough!)

Output format: {"score": float, "metrics": {"mult_count": int, ...}}
"""

import ast
import json
import sys
import traceback
from pathlib import Path
from typing import Any


def count_multiplications_ast(source_code: str, function_name: str = "matmul_4x4") -> int:
    """
    Count multiplication operations in a function using AST analysis.

    This counts:
    - Binary multiplication (*) operations
    - Augmented assignment (*=)

    It does NOT count:
    - List/string repetition (handled separately)
    - Method calls that might do multiplication
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return -1

    class MultCounter(ast.NodeVisitor):
        def __init__(self):
            self.count = 0
            self.in_target_function = False
            self.nested_calls = []

        def visit_FunctionDef(self, node):
            if node.name == function_name:
                self.in_target_function = True
                self.generic_visit(node)
                self.in_target_function = False
            else:
                # Track other functions that might be called
                self.generic_visit(node)

        def visit_BinOp(self, node):
            if self.in_target_function:
                if isinstance(node.op, ast.Mult):
                    # Check if this is likely scalar multiplication
                    # (not list repetition like [0] * 4)
                    if not self._is_list_repetition(node):
                        self.count += 1
            self.generic_visit(node)

        def visit_AugAssign(self, node):
            if self.in_target_function:
                if isinstance(node.op, ast.Mult):
                    self.count += 1
            self.generic_visit(node)

        def _is_list_repetition(self, node) -> bool:
            """Check if this is list repetition like [0] * 4."""
            # Left side is a list literal
            if isinstance(node.left, ast.List):
                return True
            # Right side is a list literal (rare but possible: 4 * [0])
            if isinstance(node.right, ast.List):
                return True
            # List comprehension on left
            if isinstance(node.left, ast.ListComp):
                return True
            return False

    counter = MultCounter()
    counter.visit(tree)
    return counter.count


def count_multiplications_dynamic(func, A, B) -> tuple[int, list[list[float]]]:
    """
    Count multiplications by running the function with instrumented floats.

    This is more accurate but requires the function to work with our wrapper.
    """

    class CountedFloat:
        """Float wrapper that counts multiplications."""
        _mult_count = 0

        def __init__(self, value):
            self.value = float(value)

        @classmethod
        def reset_count(cls):
            cls._mult_count = 0

        @classmethod
        def get_count(cls) -> int:
            return cls._mult_count

        def __mul__(self, other):
            CountedFloat._mult_count += 1
            if isinstance(other, CountedFloat):
                return CountedFloat(self.value * other.value)
            return CountedFloat(self.value * other)

        def __rmul__(self, other):
            CountedFloat._mult_count += 1
            if isinstance(other, CountedFloat):
                return CountedFloat(other.value * self.value)
            return CountedFloat(other * self.value)

        def __add__(self, other):
            if isinstance(other, CountedFloat):
                return CountedFloat(self.value + other.value)
            return CountedFloat(self.value + other)

        def __radd__(self, other):
            if isinstance(other, CountedFloat):
                return CountedFloat(other.value + self.value)
            return CountedFloat(other + self.value)

        def __sub__(self, other):
            if isinstance(other, CountedFloat):
                return CountedFloat(self.value - other.value)
            return CountedFloat(self.value - other)

        def __rsub__(self, other):
            if isinstance(other, CountedFloat):
                return CountedFloat(other.value - self.value)
            return CountedFloat(other - self.value)

        def __neg__(self):
            return CountedFloat(-self.value)

        def __float__(self):
            return self.value

        def __repr__(self):
            return f"CountedFloat({self.value})"

    # Convert input matrices to CountedFloat
    A_counted = [[CountedFloat(A[i][j]) for j in range(4)] for i in range(4)]
    B_counted = [[CountedFloat(B[i][j]) for j in range(4)] for i in range(4)]

    CountedFloat.reset_count()

    try:
        C_counted = func(A_counted, B_counted)

        # Extract result
        C = [[0.0] * 4 for _ in range(4)]
        for i in range(4):
            for j in range(4):
                if isinstance(C_counted[i][j], CountedFloat):
                    C[i][j] = C_counted[i][j].value
                else:
                    C[i][j] = float(C_counted[i][j])

        return CountedFloat.get_count(), C
    except Exception as e:
        # If instrumented version fails, return -1
        return -1, None


def verify_correctness(func, A, B) -> bool:
    """Verify that the function produces correct results."""
    # Reference implementation
    expected = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            for k in range(4):
                expected[i][j] += A[i][k] * B[k][j]

    try:
        result = func(A, B)

        # Check dimensions
        if len(result) != 4 or any(len(row) != 4 for row in result):
            return False

        # Check values
        for i in range(4):
            for j in range(4):
                if abs(result[i][j] - expected[i][j]) > 1e-6:
                    return False
        return True
    except Exception:
        return False


def compute_score(mult_count: int) -> float:
    """
    Compute score based on multiplication count.

    Scoring function:
    - 64 (standard): 0.0
    - 49 (Strassen): 0.8
    - 47 (AlphaTensor): 0.95
    - <47: 1.0

    Linear interpolation between these points.
    """
    if mult_count < 0:
        return 0.0

    if mult_count >= 64:
        return 0.0
    elif mult_count > 49:
        # Linear from 64->0.0 to 49->0.8
        return 0.8 * (64 - mult_count) / (64 - 49)
    elif mult_count > 47:
        # Linear from 49->0.8 to 47->0.95
        return 0.8 + 0.15 * (49 - mult_count) / (49 - 47)
    elif mult_count == 47:
        return 0.95
    else:
        # < 47 is a breakthrough!
        return 1.0


def main():
    # Load solution
    solution_path = Path(__file__).parent / "solution.py"
    if not solution_path.exists():
        print(json.dumps({"score": 0.0, "error": "solution.py not found"}))
        return

    try:
        source_code = solution_path.read_text()

        # Import the solution module
        import importlib.util
        spec = importlib.util.spec_from_file_location("solution", solution_path)
        solution = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(solution)

        matmul_func = solution.matmul_4x4

    except Exception as e:
        print(json.dumps({"score": 0.0, "error": f"Failed to load solution: {e}"}))
        return

    # Test matrices
    A = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
        [13, 14, 15, 16]
    ]
    B = [
        [17, 18, 19, 20],
        [21, 22, 23, 24],
        [25, 26, 27, 28],
        [29, 30, 31, 32]
    ]

    # Verify correctness first
    if not verify_correctness(matmul_func, A, B):
        print(json.dumps({
            "score": 0.0,
            "error": "Solution produces incorrect results",
            "metrics": {"correct": False}
        }))
        return

    # Count multiplications using AST analysis
    ast_count = count_multiplications_ast(source_code)

    # Count multiplications dynamically (more accurate)
    dynamic_count, _ = count_multiplications_dynamic(matmul_func, A, B)

    # Use dynamic count if available, otherwise AST count
    if dynamic_count > 0:
        mult_count = dynamic_count
        count_method = "dynamic"
    elif ast_count > 0:
        mult_count = ast_count
        count_method = "ast"
    else:
        # Fallback: assume standard algorithm
        mult_count = 64
        count_method = "fallback"

    # Compute score
    score = compute_score(mult_count)

    # Determine approach category
    if mult_count >= 64:
        approach = "standard"
    elif mult_count > 49:
        approach = "improved"
    elif mult_count == 49:
        approach = "strassen_level"
    elif mult_count > 47:
        approach = "near_alphatensor"
    elif mult_count == 47:
        approach = "alphatensor_level"
    else:
        approach = "breakthrough"

    result = {
        "score": score,
        "metrics": {
            "mult_count": mult_count,
            "count_method": count_method,
            "approach": approach,
            "correct": True,
            "target_49": mult_count <= 49,
            "target_47": mult_count <= 47,
            "improvement_vs_standard": 64 - mult_count,
            "improvement_vs_strassen": 49 - mult_count,
        }
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
