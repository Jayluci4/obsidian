"""
4x4 Matrix Multiplication - Final Solution

RESULT: 49 scalar multiplications (Strassen's algorithm)

This matches the state of the art for real arithmetic 4x4 matrix multiplication.
AlphaTensor achieved 47 only for finite field (mod 2) arithmetic, not reals.

For real numbers, 49 remains the best known since Strassen (1969).
"""


def matmul_4x4(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """
    4x4 matrix multiplication using recursive Strassen.

    Complexity: 49 scalar multiplications (optimal known for reals)

    Method:
    - View 4x4 as 2x2 blocks of 2x2 matrices
    - Apply Strassen at block level (7 block products)
    - Each block product uses Strassen at scalar level (7 scalar mults)
    - Total: 7 * 7 = 49 multiplications
    """

    # Strassen's 2x2: computes C = A @ B using 7 multiplications
    def strassen_2x2(a11, a12, a21, a22, b11, b12, b21, b22):
        # 7 products (Strassen's formulas)
        p1 = (a11 + a22) * (b11 + b22)
        p2 = (a21 + a22) * b11
        p3 = a11 * (b12 - b22)
        p4 = a22 * (b21 - b11)
        p5 = (a11 + a12) * b22
        p6 = (a21 - a11) * (b11 + b12)
        p7 = (a12 - a22) * (b21 + b22)

        # Combine (additions only)
        c11 = p1 + p4 - p5 + p7
        c12 = p3 + p5
        c21 = p2 + p4
        c22 = p1 - p2 + p3 + p6

        return c11, c12, c21, c22

    # 2x2 block arithmetic helpers
    def block_add(X, Y):
        return (X[0]+Y[0], X[1]+Y[1], X[2]+Y[2], X[3]+Y[3])

    def block_sub(X, Y):
        return (X[0]-Y[0], X[1]-Y[1], X[2]-Y[2], X[3]-Y[3])

    # Extract 2x2 blocks (stored as tuples: top-left, top-right, bot-left, bot-right)
    A11 = (A[0][0], A[0][1], A[1][0], A[1][1])
    A12 = (A[0][2], A[0][3], A[1][2], A[1][3])
    A21 = (A[2][0], A[2][1], A[3][0], A[3][1])
    A22 = (A[2][2], A[2][3], A[3][2], A[3][3])

    B11 = (B[0][0], B[0][1], B[1][0], B[1][1])
    B12 = (B[0][2], B[0][3], B[1][2], B[1][3])
    B21 = (B[2][0], B[2][1], B[3][0], B[3][1])
    B22 = (B[2][2], B[2][3], B[3][2], B[3][3])

    # 7 block products using Strassen at block level
    # Each calls strassen_2x2 (7 scalar multiplications each)
    M1 = strassen_2x2(*block_add(A11, A22), *block_add(B11, B22))  # 7 mults
    M2 = strassen_2x2(*block_add(A21, A22), *B11)                  # 7 mults
    M3 = strassen_2x2(*A11, *block_sub(B12, B22))                  # 7 mults
    M4 = strassen_2x2(*A22, *block_sub(B21, B11))                  # 7 mults
    M5 = strassen_2x2(*block_add(A11, A12), *B22)                  # 7 mults
    M6 = strassen_2x2(*block_sub(A21, A11), *block_add(B11, B12))  # 7 mults
    M7 = strassen_2x2(*block_sub(A12, A22), *block_add(B21, B22))  # 7 mults
    # Total: 49 scalar multiplications

    # Combine blocks (additions only)
    C11 = block_add(block_sub(block_add(M1, M4), M5), M7)
    C12 = block_add(M3, M5)
    C21 = block_add(M2, M4)
    C22 = block_add(block_sub(block_add(M1, M3), M2), M6)

    # Assemble 4x4 result
    return [
        [C11[0], C11[1], C12[0], C12[1]],
        [C11[2], C11[3], C12[2], C12[3]],
        [C21[0], C21[1], C22[0], C22[1]],
        [C21[2], C21[3], C22[2], C22[3]]
    ]
