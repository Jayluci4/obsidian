#!/usr/bin/env python3
"""
Benchmark for 2x2 matrix multiplication.

Measures:
- Number of scalar multiplications used
- Correctness verification
- Execution time

Outputs JSON with score (lower is better - fewer multiplications).
"""

import ast
import json
import sys
import time
from pathlib import Path


class MultiplicationCounter(ast.NodeVisitor):
    """Count multiplication operations in AST."""

    def __init__(self):
        self.mult_count = 0
        self.add_count = 0
        self.sub_count = 0

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Mult):
            self.mult_count += 1
        elif isinstance(node.op, ast.Add):
            self.add_count += 1
        elif isinstance(node.op, ast.Sub):
            self.sub_count += 1
        self.generic_visit(node)


def count_operations(code: str) -> dict:
    """Count arithmetic operations in code."""
    try:
        tree = ast.parse(code)
        counter = MultiplicationCounter()
        counter.visit(tree)
        return {
            "multiplications": counter.mult_count,
            "additions": counter.add_count,
            "subtractions": counter.sub_count,
        }
    except SyntaxError:
        return {"multiplications": 999, "additions": 999, "subtractions": 999}


def verify_correctness(matmul_func) -> bool:
    """Verify the function produces correct results."""
    test_cases = [
        ([[1, 0], [0, 1]], [[5, 6], [7, 8]], [[5, 6], [7, 8]]),
        ([[1, 2], [3, 4]], [[5, 6], [7, 8]], [[19, 22], [43, 50]]),
        ([[0, 0], [0, 0]], [[1, 2], [3, 4]], [[0, 0], [0, 0]]),
    ]

    for A, B, expected in test_cases:
        try:
            result = matmul_func(A, B)
            if result != expected:
                return False
        except Exception:
            return False
    return True


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No solution file provided", "score": 999}))
        sys.exit(1)

    solution_path = Path(sys.argv[1])
    if not solution_path.exists():
        print(json.dumps({"error": f"File not found: {solution_path}", "score": 999}))
        sys.exit(1)

    # Read and analyze code
    code = solution_path.read_text()
    ops = count_operations(code)

    # Import and test the function
    import importlib.util
    spec = importlib.util.spec_from_file_location("solution", solution_path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
        matmul_func = getattr(module, "matmul_2x2", None)

        if matmul_func is None:
            print(json.dumps({
                "error": "Function matmul_2x2 not found",
                "score": 999
            }))
            sys.exit(1)

        # Verify correctness
        correct = verify_correctness(matmul_func)

        # Benchmark execution time
        A = [[1.5, 2.5], [3.5, 4.5]]
        B = [[5.5, 6.5], [7.5, 8.5]]

        start = time.perf_counter()
        for _ in range(10000):
            matmul_func(A, B)
        elapsed = time.perf_counter() - start

        # Score is multiplication count (lower is better)
        score = ops["multiplications"]

        result = {
            "score": score,
            "correct": correct,
            "metrics": {
                "multiplications": {"count": ops["multiplications"]},
                "additions": {"count": ops["additions"]},
                "subtractions": {"count": ops["subtractions"]},
            },
            "execution_time_ms": elapsed * 1000,
            "iterations": 10000,
        }

        print(json.dumps(result))

    except Exception as e:
        print(json.dumps({
            "error": str(e),
            "score": 999
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
