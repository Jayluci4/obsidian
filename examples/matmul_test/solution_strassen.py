"""
Strassen's algorithm for 2x2 matrix multiplication.
Uses 7 multiplications instead of 8.
"""


def matmul_2x2(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """
    Multiply two 2x2 matrices using Strassen's algorithm.
    """
    a00, a01 = A[0][0], A[0][1]
    a10, a11 = A[1][0], A[1][1]
    b00, b01 = B[0][0], B[0][1]
    b10, b11 = B[1][0], B[1][1]

    # Strassen's 7 products
    m1 = (a00 + a11) * (b00 + b11)
    m2 = (a10 + a11) * b00
    m3 = a00 * (b01 - b11)
    m4 = a11 * (b10 - b00)
    m5 = (a00 + a01) * b11
    m6 = (a10 - a00) * (b00 + b01)
    m7 = (a01 - a11) * (b10 + b11)

    # Combine to get result
    c00 = m1 + m4 - m5 + m7
    c01 = m3 + m5
    c10 = m2 + m4
    c11 = m1 - m2 + m3 + m6

    return [[c00, c01], [c10, c11]]
