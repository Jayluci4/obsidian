"""Evaluator module for running code quality metrics."""

from .base import EvalResult, MetricCollector, compute_composite_reward
from .pytest_eval import PytestEvaluator, format_pytest_failures
from .coverage_eval import CoverageEvaluator, format_coverage_details
from .ruff_eval import RuffEvaluator, format_ruff_issues
from .pyright_eval import PyrightEvaluator, format_pyright_diagnostics
from .composite import CompositeEvaluator, CompositeResult, format_composite_feedback
from .delta import DeltaTracker, DeltaResult, Baseline, format_delta_feedback
from .response_analyzer import (
    ResponseAnalyzer,
    ResponseAnalysis,
    LoopType,
    analyze_response,
    detect_completion,
    is_test_only_output,
)
from .cache import (
    EvaluationCache,
    CachedEvaluatorWrapper,
    CacheEntry,
    CacheStats,
    compute_file_hash,
    compute_directory_hash,
)

__all__ = [
    # Base
    "EvalResult",
    "MetricCollector",
    "compute_composite_reward",
    # Pytest
    "PytestEvaluator",
    "format_pytest_failures",
    # Coverage
    "CoverageEvaluator",
    "format_coverage_details",
    # Ruff
    "RuffEvaluator",
    "format_ruff_issues",
    # Pyright
    "PyrightEvaluator",
    "format_pyright_diagnostics",
    # Composite
    "CompositeEvaluator",
    "CompositeResult",
    "format_composite_feedback",
    # Delta
    "DeltaTracker",
    "DeltaResult",
    "Baseline",
    "format_delta_feedback",
    # Response Analysis
    "ResponseAnalyzer",
    "ResponseAnalysis",
    "LoopType",
    "analyze_response",
    "detect_completion",
    "is_test_only_output",
    # Cache
    "EvaluationCache",
    "CachedEvaluatorWrapper",
    "CacheEntry",
    "CacheStats",
    "compute_file_hash",
    "compute_directory_hash",
]
