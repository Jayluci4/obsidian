"""
Known Sorting Algorithms.

Contains detection patterns for common sorting algorithms.
"""

from obsidian.research.known_algorithms import (
    KnownAlgorithm,
    SignatureMatcher,
    KeywordMatcher,
)


# Quicksort Detection
QUICKSORT = KnownAlgorithm(
    name="quicksort",
    description="Quicksort with pivot partitioning",
    patterns=[
        SignatureMatcher(
            patterns=[
                r"pivot",
                r"partition",
                r"quicksort|quick_sort",
                r"if.*<.*pivot.*elif.*>.*pivot",
                r"left.*right.*pivot",
            ],
            threshold=0.4,
        ),
        KeywordMatcher(
            keywords=["quicksort", "quick_sort", "pivot", "partition"],
            threshold=0.5,
        ),
    ],
    penalty=0.8,
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.5,
)


# Mergesort Detection
MERGESORT = KnownAlgorithm(
    name="mergesort",
    description="Merge sort with divide and conquer",
    patterns=[
        SignatureMatcher(
            patterns=[
                r"merge.*sort|mergesort",
                r"def\s+merge\s*\(",
                r"mid\s*=.*len.*//\s*2",
                r"left.*=.*\[:.*mid\]",
                r"right.*=.*\[mid:\]",
            ],
            threshold=0.4,
        ),
        KeywordMatcher(
            keywords=["mergesort", "merge_sort", "merge", "divide"],
            threshold=0.5,
        ),
    ],
    penalty=0.8,
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.5,
)


# Heapsort Detection
HEAPSORT = KnownAlgorithm(
    name="heapsort",
    description="Heap sort using heap data structure",
    patterns=[
        SignatureMatcher(
            patterns=[
                r"heapsort|heap_sort",
                r"heapify",
                r"sift.*down|siftdown",
                r"build.*heap",
            ],
            threshold=0.4,
        ),
        KeywordMatcher(
            keywords=["heapsort", "heap_sort", "heapify", "heap"],
            threshold=0.5,
        ),
    ],
    penalty=0.8,
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.5,
)


# Insertion Sort Detection
INSERTION_SORT = KnownAlgorithm(
    name="insertion_sort",
    description="Insertion sort with shifting elements",
    patterns=[
        SignatureMatcher(
            patterns=[
                r"insertion.*sort",
                r"for.*i.*range.*1.*len",
                r"while.*j.*>=.*0.*and",
                r"key\s*=.*\[i\]",
            ],
            threshold=0.5,
        ),
        KeywordMatcher(
            keywords=["insertion", "insert", "key", "shift"],
            threshold=0.5,
        ),
    ],
    penalty=0.6,
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.4,
)


# Bubble Sort Detection
BUBBLE_SORT = KnownAlgorithm(
    name="bubble_sort",
    description="Bubble sort with adjacent swaps",
    patterns=[
        SignatureMatcher(
            patterns=[
                r"bubble.*sort",
                r"for.*i.*range.*len.*for.*j.*range",
                r"if.*\[j\].*>.*\[j\s*\+\s*1\]",
                r"swap|swapped",
            ],
            threshold=0.4,
        ),
        KeywordMatcher(
            keywords=["bubble", "swap", "adjacent"],
            threshold=0.4,
        ),
    ],
    penalty=0.5,  # Lower penalty since it's suboptimal anyway
    severity="hard",
    allow_variations=True,
    variation_penalty_factor=0.3,
)


# List of all sorting algorithms
SORTING_ALGORITHMS = [
    QUICKSORT,
    MERGESORT,
    HEAPSORT,
    INSERTION_SORT,
    BUBBLE_SORT,
]
