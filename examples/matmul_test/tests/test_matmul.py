"""Tests for 2x2 matrix multiplication."""

import pytest
import sys
sys.path.insert(0, "..")

from solution import matmul_2x2


def test_identity_matrix():
    """Multiplying by identity should return the same matrix."""
    A = [[1, 2], [3, 4]]
    I = [[1, 0], [0, 1]]

    result = matmul_2x2(A, I)
    assert result == [[1, 2], [3, 4]]

    result = matmul_2x2(I, A)
    assert result == [[1, 2], [3, 4]]


def test_zero_matrix():
    """Multiplying by zero matrix should return zero matrix."""
    A = [[1, 2], [3, 4]]
    Z = [[0, 0], [0, 0]]

    result = matmul_2x2(A, Z)
    assert result == [[0, 0], [0, 0]]


def test_simple_multiplication():
    """Test basic matrix multiplication."""
    A = [[1, 2], [3, 4]]
    B = [[5, 6], [7, 8]]

    # Expected: [[1*5+2*7, 1*6+2*8], [3*5+4*7, 3*6+4*8]]
    #         = [[19, 22], [43, 50]]
    result = matmul_2x2(A, B)
    assert result == [[19, 22], [43, 50]]


def test_negative_numbers():
    """Test with negative numbers."""
    A = [[-1, 2], [3, -4]]
    B = [[5, -6], [-7, 8]]

    # Expected: [[-1*5+2*(-7), -1*(-6)+2*8], [3*5+(-4)*(-7), 3*(-6)+(-4)*8]]
    #         = [[-19, 22], [43, -50]]
    result = matmul_2x2(A, B)
    assert result == [[-19, 22], [43, -50]]


def test_floating_point():
    """Test with floating point numbers."""
    A = [[1.5, 2.5], [3.5, 4.5]]
    B = [[0.5, 1.5], [2.5, 3.5]]

    result = matmul_2x2(A, B)

    # Allow small floating point errors
    assert abs(result[0][0] - 7.0) < 1e-9
    assert abs(result[0][1] - 11.0) < 1e-9
    assert abs(result[1][0] - 13.0) < 1e-9
    assert abs(result[1][1] - 21.0) < 1e-9


def test_associativity():
    """Test that (AB)C = A(BC)."""
    A = [[1, 2], [3, 4]]
    B = [[5, 6], [7, 8]]
    C = [[9, 10], [11, 12]]

    # (AB)C
    AB = matmul_2x2(A, B)
    ABC_left = matmul_2x2(AB, C)

    # A(BC)
    BC = matmul_2x2(B, C)
    ABC_right = matmul_2x2(A, BC)

    assert ABC_left == ABC_right


def test_non_commutativity():
    """Test that AB != BA in general."""
    A = [[1, 2], [3, 4]]
    B = [[5, 6], [7, 8]]

    AB = matmul_2x2(A, B)
    BA = matmul_2x2(B, A)

    # These should be different
    assert AB != BA
