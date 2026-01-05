"""
Reference implementation of Strassen's algorithm for 4x4 matrices.

This applies Strassen's 2x2 algorithm recursively:
- Level 1: Split 4x4 into four 2x2 blocks, use 7 multiplications of 2x2 matrices
- Level 2: Each 2x2 multiplication uses 7 scalar multiplications

Total: 7 * 7 = 49 scalar multiplications (vs 64 for standard)
"""


def strassen_2x2(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """
    Strassen's algorithm for 2x2 matrices.
    Uses 7 multiplications instead of 8.
    """
    a11, a12 = A[0][0], A[0][1]
    a21, a22 = A[1][0], A[1][1]
    b11, b12 = B[0][0], B[0][1]
    b21, b22 = B[1][0], B[1][1]

    # 7 multiplications
    m1 = (a11 + a22) * (b11 + b22)
    m2 = (a21 + a22) * b11
    m3 = a11 * (b12 - b22)
    m4 = a22 * (b21 - b11)
    m5 = (a11 + a12) * b22
    m6 = (a21 - a11) * (b11 + b12)
    m7 = (a12 - a22) * (b21 + b22)

    # Combine using additions only
    c11 = m1 + m4 - m5 + m7
    c12 = m3 + m5
    c21 = m2 + m4
    c22 = m1 - m2 + m3 + m6

    return [[c11, c12], [c21, c22]]


def add_2x2(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """Add two 2x2 matrices."""
    return [
        [A[0][0] + B[0][0], A[0][1] + B[0][1]],
        [A[1][0] + B[1][0], A[1][1] + B[1][1]]
    ]


def sub_2x2(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """Subtract two 2x2 matrices."""
    return [
        [A[0][0] - B[0][0], A[0][1] - B[0][1]],
        [A[1][0] - B[1][0], A[1][1] - B[1][1]]
    ]


def matmul_4x4(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """
    Strassen's algorithm for 4x4 matrices (recursive application).

    Split into 2x2 blocks and apply Strassen at both levels.
    Total multiplications: 7 * 7 = 49
    """
    # Split A into 2x2 blocks
    A11 = [[A[0][0], A[0][1]], [A[1][0], A[1][1]]]
    A12 = [[A[0][2], A[0][3]], [A[1][2], A[1][3]]]
    A21 = [[A[2][0], A[2][1]], [A[3][0], A[3][1]]]
    A22 = [[A[2][2], A[2][3]], [A[3][2], A[3][3]]]

    # Split B into 2x2 blocks
    B11 = [[B[0][0], B[0][1]], [B[1][0], B[1][1]]]
    B12 = [[B[0][2], B[0][3]], [B[1][2], B[1][3]]]
    B21 = [[B[2][0], B[2][1]], [B[3][0], B[3][1]]]
    B22 = [[B[2][2], B[2][3]], [B[3][2], B[3][3]]]

    # Strassen's 7 products at block level (each is a 2x2 Strassen multiplication)
    M1 = strassen_2x2(add_2x2(A11, A22), add_2x2(B11, B22))
    M2 = strassen_2x2(add_2x2(A21, A22), B11)
    M3 = strassen_2x2(A11, sub_2x2(B12, B22))
    M4 = strassen_2x2(A22, sub_2x2(B21, B11))
    M5 = strassen_2x2(add_2x2(A11, A12), B22)
    M6 = strassen_2x2(sub_2x2(A21, A11), add_2x2(B11, B12))
    M7 = strassen_2x2(sub_2x2(A12, A22), add_2x2(B21, B22))

    # Combine results
    C11 = add_2x2(sub_2x2(add_2x2(M1, M4), M5), M7)
    C12 = add_2x2(M3, M5)
    C21 = add_2x2(M2, M4)
    C22 = add_2x2(sub_2x2(add_2x2(M1, M3), M2), M6)

    # Assemble 4x4 result
    return [
        [C11[0][0], C11[0][1], C12[0][0], C12[0][1]],
        [C11[1][0], C11[1][1], C12[1][0], C12[1][1]],
        [C21[0][0], C21[0][1], C22[0][0], C22[0][1]],
        [C21[1][0], C21[1][1], C22[1][0], C22[1][1]]
    ]


if __name__ == "__main__":
    # Test
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

    C = matmul_4x4(A, B)
    print("Result:")
    for row in C:
        print(row)

    # Expected result
    expected = [
        [250, 260, 270, 280],
        [618, 644, 670, 696],
        [986, 1028, 1070, 1112],
        [1354, 1412, 1470, 1528]
    ]
    print("\nExpected:")
    for row in expected:
        print(row)

    print("\nCorrect:", C == expected)
