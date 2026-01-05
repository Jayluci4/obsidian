"""
Rigorous correctness tests for 4x4 matrix multiplication.

These tests ensure any discovered algorithm produces exactly correct results.
"""

import math
import random
import sys
from pathlib import Path

import pytest

# Add solution to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from solution import matmul_4x4


def numpy_matmul(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """Reference implementation using standard algorithm."""
    C = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            for k in range(4):
                C[i][j] += A[i][k] * B[k][j]
    return C


def matrices_equal(C1: list[list[float]], C2: list[list[float]], tol: float = 1e-9) -> bool:
    """Check if two matrices are equal within tolerance."""
    for i in range(4):
        for j in range(4):
            if abs(C1[i][j] - C2[i][j]) > tol:
                return False
    return True


def random_matrix(low: float = -10.0, high: float = 10.0) -> list[list[float]]:
    """Generate random 4x4 matrix."""
    return [[random.uniform(low, high) for _ in range(4)] for _ in range(4)]


def integer_matrix(low: int = -10, high: int = 10) -> list[list[float]]:
    """Generate random integer 4x4 matrix."""
    return [[float(random.randint(low, high)) for _ in range(4)] for _ in range(4)]


class TestBasicCorrectness:
    """Basic correctness tests."""

    def test_identity_left(self):
        """A @ I = A"""
        I = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        A = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]]
        C = matmul_4x4(A, I)
        assert matrices_equal(C, A)

    def test_identity_right(self):
        """I @ B = B"""
        I = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        B = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]]
        C = matmul_4x4(I, B)
        assert matrices_equal(C, B)

    def test_zero_matrix(self):
        """A @ 0 = 0"""
        A = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]]
        Z = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        C = matmul_4x4(A, Z)
        assert matrices_equal(C, Z)

    def test_simple_integers(self):
        """Simple integer multiplication."""
        A = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]]
        B = [[1, 0, 0, 0], [0, 2, 0, 0], [0, 0, 3, 0], [0, 0, 0, 4]]
        expected = numpy_matmul(A, B)
        C = matmul_4x4(A, B)
        assert matrices_equal(C, expected)

    def test_diagonal_matrices(self):
        """Diagonal matrix multiplication."""
        D1 = [[2, 0, 0, 0], [0, 3, 0, 0], [0, 0, 4, 0], [0, 0, 0, 5]]
        D2 = [[1, 0, 0, 0], [0, 2, 0, 0], [0, 0, 3, 0], [0, 0, 0, 4]]
        expected = [[2, 0, 0, 0], [0, 6, 0, 0], [0, 0, 12, 0], [0, 0, 0, 20]]
        C = matmul_4x4(D1, D2)
        assert matrices_equal(C, expected)


class TestRandomMatrices:
    """Random matrix tests for thorough verification."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set random seed for reproducibility."""
        random.seed(42)

    def test_random_float_matrices(self):
        """Test with random floating point matrices."""
        for _ in range(20):
            A = random_matrix()
            B = random_matrix()
            expected = numpy_matmul(A, B)
            C = matmul_4x4(A, B)
            assert matrices_equal(C, expected), f"Failed for A={A}, B={B}"

    def test_random_integer_matrices(self):
        """Test with random integer matrices."""
        for _ in range(20):
            A = integer_matrix()
            B = integer_matrix()
            expected = numpy_matmul(A, B)
            C = matmul_4x4(A, B)
            assert matrices_equal(C, expected, tol=1e-6)

    def test_large_values(self):
        """Test with large values."""
        for _ in range(10):
            A = random_matrix(-1000, 1000)
            B = random_matrix(-1000, 1000)
            expected = numpy_matmul(A, B)
            C = matmul_4x4(A, B)
            assert matrices_equal(C, expected, tol=1e-3)

    def test_small_values(self):
        """Test with small values (near zero)."""
        for _ in range(10):
            A = random_matrix(-0.001, 0.001)
            B = random_matrix(-0.001, 0.001)
            expected = numpy_matmul(A, B)
            C = matmul_4x4(A, B)
            assert matrices_equal(C, expected, tol=1e-15)


class TestEdgeCases:
    """Edge case tests."""

    def test_negative_values(self):
        """Test with all negative values."""
        A = [[-1, -2, -3, -4], [-5, -6, -7, -8], [-9, -10, -11, -12], [-13, -14, -15, -16]]
        B = [[-1, -1, -1, -1], [-1, -1, -1, -1], [-1, -1, -1, -1], [-1, -1, -1, -1]]
        expected = numpy_matmul(A, B)
        C = matmul_4x4(A, B)
        assert matrices_equal(C, expected)

    def test_mixed_signs(self):
        """Test with mixed positive and negative values."""
        A = [[1, -2, 3, -4], [-5, 6, -7, 8], [9, -10, 11, -12], [-13, 14, -15, 16]]
        B = [[-1, 2, -3, 4], [5, -6, 7, -8], [-9, 10, -11, 12], [13, -14, 15, -16]]
        expected = numpy_matmul(A, B)
        C = matmul_4x4(A, B)
        assert matrices_equal(C, expected)

    def test_sparse_matrix(self):
        """Test with sparse matrices (many zeros)."""
        A = [[1, 0, 0, 0], [0, 0, 2, 0], [0, 3, 0, 0], [0, 0, 0, 4]]
        B = [[0, 1, 0, 0], [2, 0, 0, 0], [0, 0, 3, 0], [0, 0, 0, 4]]
        expected = numpy_matmul(A, B)
        C = matmul_4x4(A, B)
        assert matrices_equal(C, expected)

    def test_ones_matrix(self):
        """Test with all ones."""
        A = [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]]
        B = [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]]
        expected = [[4, 4, 4, 4], [4, 4, 4, 4], [4, 4, 4, 4], [4, 4, 4, 4]]
        C = matmul_4x4(A, B)
        assert matrices_equal(C, expected)


class TestMathematicalProperties:
    """Tests for mathematical properties."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set random seed."""
        random.seed(123)

    def test_associativity(self):
        """Test (A @ B) @ C = A @ (B @ C)"""
        A = random_matrix()
        B = random_matrix()
        C = random_matrix()

        AB = matmul_4x4(A, B)
        AB_C = matmul_4x4(AB, C)

        BC = matmul_4x4(B, C)
        A_BC = matmul_4x4(A, BC)

        assert matrices_equal(AB_C, A_BC, tol=1e-6)

    def test_distributivity_left(self):
        """Test A @ (B + C) = A @ B + A @ C"""
        A = random_matrix()
        B = random_matrix()
        C = random_matrix()

        # B + C
        BC_sum = [[B[i][j] + C[i][j] for j in range(4)] for i in range(4)]

        # A @ (B + C)
        left = matmul_4x4(A, BC_sum)

        # A @ B + A @ C
        AB = matmul_4x4(A, B)
        AC = matmul_4x4(A, C)
        right = [[AB[i][j] + AC[i][j] for j in range(4)] for i in range(4)]

        assert matrices_equal(left, right, tol=1e-6)

    def test_scalar_multiplication(self):
        """Test (kA) @ B = k(A @ B) = A @ (kB)"""
        k = 3.5
        A = random_matrix()
        B = random_matrix()

        # kA
        kA = [[k * A[i][j] for j in range(4)] for i in range(4)]
        # kB
        kB = [[k * B[i][j] for j in range(4)] for i in range(4)]

        # (kA) @ B
        kA_B = matmul_4x4(kA, B)

        # A @ (kB)
        A_kB = matmul_4x4(A, kB)

        # k(A @ B)
        AB = matmul_4x4(A, B)
        k_AB = [[k * AB[i][j] for j in range(4)] for i in range(4)]

        assert matrices_equal(kA_B, k_AB, tol=1e-6)
        assert matrices_equal(A_kB, k_AB, tol=1e-6)


class TestSpecificKnownResults:
    """Tests with specific known results."""

    def test_textbook_example(self):
        """Standard textbook matrix multiplication example."""
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
        expected = [
            [250, 260, 270, 280],
            [618, 644, 670, 696],
            [986, 1028, 1070, 1112],
            [1354, 1412, 1470, 1528]
        ]
        C = matmul_4x4(A, B)
        assert matrices_equal(C, expected)

    def test_permutation_matrix(self):
        """Permutation matrix multiplication."""
        # Swap rows 0 and 3
        P = [[0, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0]]
        A = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]]
        expected = [[13, 14, 15, 16], [5, 6, 7, 8], [9, 10, 11, 12], [1, 2, 3, 4]]
        C = matmul_4x4(P, A)
        assert matrices_equal(C, expected)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
