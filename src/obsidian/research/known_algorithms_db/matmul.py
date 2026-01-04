"""
Known Matrix Multiplication Algorithms.

Contains detection patterns for:
- Naive (8 multiplications)
- Strassen (7 multiplications)
- Winograd (7 multiplications, variant of Strassen)
"""

from obsidian.research.known_algorithms import (
    KnownAlgorithm,
    SignatureMatcher,
    BehavioralMatcher,
    KeywordMatcher,
)


# Strassen's Algorithm Detection
STRASSEN = KnownAlgorithm(
    name="strassen",
    description="Strassen's algorithm using 7 multiplications instead of 8",
    patterns=[
        # Signature patterns for Strassen's 7 products (M1-M7)
        SignatureMatcher(
            patterns=[
                # M1 = (a00 + a11)(b00 + b11) - various forms
                r"\(\s*[aA]\[?0\]?\[?0\]?\s*\+\s*[aA]\[?1\]?\[?1\]?\s*\).*\(\s*[bB]\[?0\]?\[?0\]?\s*\+\s*[bB]\[?1\]?\[?1\]?\s*\)",
                r"[mM]1\s*=",
                # M2 = (a10 + a11) * b00
                r"\(\s*[aA]\[?1\]?\[?0\]?\s*\+\s*[aA]\[?1\]?\[?1\]?\s*\).*[bB]\[?0\]?\[?0\]?",
                # M3 = a00 * (b01 - b11)
                r"[aA]\[?0\]?\[?0\]?\s*\*?\s*\(\s*[bB]\[?0\]?\[?1\]?\s*-\s*[bB]\[?1\]?\[?1\]?\s*\)",
                # M4 = a11 * (b10 - b00)
                r"[aA]\[?1\]?\[?1\]?\s*\*?\s*\(\s*[bB]\[?1\]?\[?0\]?\s*-\s*[bB]\[?0\]?\[?0\]?\s*\)",
                # M5 = (a00 + a01) * b11
                r"\(\s*[aA]\[?0\]?\[?0\]?\s*\+\s*[aA]\[?0\]?\[?1\]?\s*\).*[bB]\[?1\]?\[?1\]?",
            ],
            threshold=0.5,  # At least 3 of 6 patterns
        ),
        # Behavioral: exactly 7 multiplications
        BehavioralMatcher(
            expected_behavior={
                "metrics.multiplications.count": 7,
            },
            tolerance=0,
        ),
        # Keyword detection
        KeywordMatcher(
            keywords=["strassen", "m1", "m2", "m3", "m4", "m5", "m6", "m7"],
            threshold=0.4,
        ),
    ],
    penalty=0.9,  # 90% penalty - severe
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.6,
)


# Winograd's Variant Detection
WINOGRAD = KnownAlgorithm(
    name="winograd",
    description="Winograd's variant of Strassen with fewer additions",
    patterns=[
        SignatureMatcher(
            patterns=[
                r"winograd",
                r"[sS]1\s*=.*[aA].*-.*[aA]",
                r"[sS]2\s*=.*[sS]1.*\+.*[aA]",
                r"[tT]1\s*=.*[bB].*-.*[bB]",
                r"[tT]2\s*=.*[bB].*-.*[tT]1",
            ],
            threshold=0.4,
        ),
        BehavioralMatcher(
            expected_behavior={
                "metrics.multiplications.count": 7,
            },
            tolerance=0,
        ),
        KeywordMatcher(
            keywords=["winograd", "s1", "s2", "s3", "s4", "t1", "t2", "t3", "t4"],
            threshold=0.3,
        ),
    ],
    penalty=0.85,
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.5,
)


# Naive Algorithm Detection
NAIVE = KnownAlgorithm(
    name="naive",
    description="Naive matrix multiplication using 8 multiplications",
    patterns=[
        # Direct multiplication patterns
        SignatureMatcher(
            patterns=[
                # c00 = a00*b00 + a01*b10
                r"[cC]\[?0\]?\[?0\]?\s*=\s*[aA]\[?0\]?\[?0\]?\s*\*\s*[bB]\[?0\]?\[?0\]?\s*\+\s*[aA]\[?0\]?\[?1\]?\s*\*\s*[bB]\[?1\]?\[?0\]?",
                # c01 = a00*b01 + a01*b11
                r"[cC]\[?0\]?\[?1\]?\s*=\s*[aA]\[?0\]?\[?0\]?\s*\*\s*[bB]\[?0\]?\[?1\]?\s*\+\s*[aA]\[?0\]?\[?1\]?\s*\*\s*[bB]\[?1\]?\[?1\]?",
                # c10 = a10*b00 + a11*b10
                r"[cC]\[?1\]?\[?0\]?\s*=\s*[aA]\[?1\]?\[?0\]?\s*\*\s*[bB]\[?0\]?\[?0\]?\s*\+\s*[aA]\[?1\]?\[?1\]?\s*\*\s*[bB]\[?1\]?\[?0\]?",
                # c11 = a10*b01 + a11*b11
                r"[cC]\[?1\]?\[?1\]?\s*=\s*[aA]\[?1\]?\[?0\]?\s*\*\s*[bB]\[?0\]?\[?1\]?\s*\+\s*[aA]\[?1\]?\[?1\]?\s*\*\s*[bB]\[?1\]?\[?1\]?",
            ],
            threshold=0.5,
        ),
        BehavioralMatcher(
            expected_behavior={
                "metrics.multiplications.count": 8,
            },
            tolerance=0,
        ),
    ],
    penalty=0.7,  # 70% penalty
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.4,
)


# List of all matrix multiplication algorithms
MATMUL_ALGORITHMS = [STRASSEN, WINOGRAD, NAIVE]
