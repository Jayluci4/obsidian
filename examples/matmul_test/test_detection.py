#!/usr/bin/env python3
"""
Test that known algorithm detection works with dynamic definitions.
"""

import sys
sys.path.insert(0, "../../src")

from pathlib import Path
from obsidian.research.problem import load_problem
from obsidian.research.known_algorithms import create_detector_from_definitions


def main():
    # Load problem with dynamic definitions
    problem = load_problem("problem.yaml")

    print("=" * 60)
    print("Known Algorithm Detection Test")
    print("=" * 60)

    # Check definitions were loaded
    config = problem.novelty.known_algorithms
    print(f"\nLoaded {len(config.definitions)} algorithm definitions:")
    for defn in config.definitions:
        print(f"  - {defn.name}: {defn.description} (penalty: {defn.penalty:.0%})")

    # Create detector from dynamic definitions
    detector = create_detector_from_definitions(config.definitions)
    print(f"\nDetector has {len(detector.algorithms)} algorithms configured")

    # Test with Strassen code
    print("\n" + "-" * 60)
    print("Testing Strassen solution...")
    print("-" * 60)

    strassen_code = Path("solution_strassen.py").read_text()
    result = detector.detect(strassen_code, confidence_threshold=config.confidence_threshold)

    print(f"\nDetection result:")
    print(f"  is_known: {result.is_known}")
    print(f"  algorithm_name: {result.algorithm_name}")
    print(f"  confidence: {result.confidence:.2%}")
    print(f"  penalty: {result.penalty:.2%}")

    if result.matcher_scores:
        print(f"\nMatcher scores:")
        for matcher, score in result.matcher_scores.items():
            print(f"  {matcher}: {score:.2%}")

    # Test score penalty
    print("\n" + "-" * 60)
    print("Testing score penalty...")
    print("-" * 60)

    base_score = 0.85  # Good benchmark score
    penalized_score = detector.compute_penalized_score(
        base_score, result, penalty_mode="multiplicative"
    )

    print(f"\nBase score: {base_score:.2f}")
    print(f"Penalty applied: {result.penalty:.2%}")
    print(f"Final score: {penalized_score:.2f}")
    print(f"Score reduction: {(1 - penalized_score/base_score):.2%}")

    # Test with a naive solution
    print("\n" + "-" * 60)
    print("Testing naive solution...")
    print("-" * 60)

    naive_code = """
def matmul_2x2(A, B):
    a00, a01 = A[0][0], A[0][1]
    a10, a11 = A[1][0], A[1][1]
    b00, b01 = B[0][0], B[0][1]
    b10, b11 = B[1][0], B[1][1]

    c00 = a00 * b00 + a01 * b10
    c01 = a00 * b01 + a01 * b11
    c10 = a10 * b00 + a11 * b10
    c11 = a10 * b01 + a11 * b11

    return [[c00, c01], [c10, c11]]
"""
    naive_result = detector.detect(naive_code, confidence_threshold=config.confidence_threshold)
    print(f"\nNaive detection:")
    print(f"  is_known: {naive_result.is_known}")
    print(f"  algorithm_name: {naive_result.algorithm_name}")
    print(f"  confidence: {naive_result.confidence:.2%}")

    # Test with novel code (should NOT be detected)
    print("\n" + "-" * 60)
    print("Testing novel solution (should NOT be detected)...")
    print("-" * 60)

    novel_code = """
def matmul_2x2(A, B):
    # Some hypothetical novel approach using different structure
    x = A[0][0] + A[1][1]
    y = B[0][0] - B[1][0]
    z = A[0][1] * B[1][0]
    w = A[1][0] * B[0][1]

    # Fictional combination (won't produce correct result)
    return [[x * y + z, w - z], [z + w, x * y - w]]
"""
    novel_result = detector.detect(novel_code, confidence_threshold=config.confidence_threshold)
    print(f"\nNovel detection:")
    print(f"  is_known: {novel_result.is_known}")
    print(f"  confidence: {novel_result.confidence:.2%}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

    # Summary
    print("\nSummary:")
    print(f"  Strassen detected: {'YES' if result.is_known else 'NO'}")
    print(f"  Novel NOT detected: {'YES' if not novel_result.is_known else 'NO'}")

    if result.is_known and not novel_result.is_known:
        print("\n  Detection system working correctly!")
    else:
        print("\n  Detection needs tuning.")


if __name__ == "__main__":
    main()
