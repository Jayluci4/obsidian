"""
4x4 Matrix Multiplication Algorithm

Goal: Minimize the number of scalar multiplications.
- Standard algorithm: 64 multiplications
- Strassen recursive: 49 multiplications
- Target: <= 49, ideally < 49

Additions and subtractions are FREE - only multiplications count.
"""


def matmul_4x4(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """
    Multiply two 4x4 matrices A and B.

    Args:
        A: 4x4 matrix as list of lists
        B: 4x4 matrix as list of lists

    Returns:
        C: 4x4 matrix where C = A @ B
    """
    # Standard algorithm - 64 multiplications
    # This is the baseline to improve upon
    C = [[0.0] * 4 for _ in range(4)]

    for i in range(4):
        for j in range(4):
            for k in range(4):
                C[i][j] += A[i][k] * B[k][j]

    return C


# Multiplication counter for benchmarking
_mult_count = 0


def counted_mult(a: float, b: float) -> float:
    """Multiplication that counts operations."""
    global _mult_count
    _mult_count += 1
    return a * b


def reset_mult_count():
    """Reset the multiplication counter."""
    global _mult_count
    _mult_count = 0


def get_mult_count() -> int:
    """Get current multiplication count."""
    return _mult_count
