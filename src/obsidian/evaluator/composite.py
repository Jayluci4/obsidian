"""Composite evaluator that orchestrates multiple metric collectors."""

import concurrent.futures
from dataclasses import dataclass, field
from typing import Callable

from .base import EvalResult, compute_composite_reward
from .pytest_eval import PytestEvaluator, format_pytest_failures
from .coverage_eval import CoverageEvaluator, format_coverage_details
from .ruff_eval import RuffEvaluator, format_ruff_issues
from .pyright_eval import PyrightEvaluator, format_pyright_diagnostics


@dataclass
class CompositeResult:
    """Result from composite evaluation."""

    reward: float  # Weighted composite reward 0-1
    results: list[EvalResult]  # Individual evaluator results
    all_passed: bool  # All evaluators passed
    failed_evaluators: list[str]  # Names of evaluators that failed
    execution_time_ms: float
    weights: dict[str, float] = field(default_factory=dict)

    @property
    def metrics(self) -> dict[str, float]:
        """Return dict of evaluator scores."""
        return {r.name: r.score for r in self.results}


class CompositeEvaluator:
    """
    Orchestrates multiple evaluators and computes composite reward.

    Runs evaluators in parallel for efficiency.
    """

    def __init__(
        self,
        pytest_config: dict | None = None,
        coverage_config: dict | None = None,
        ruff_config: dict | None = None,
        pyright_config: dict | None = None,
        weights: dict[str, float] | None = None,
        max_workers: int = 4,
    ):
        self.max_workers = max_workers
        self.evaluators = []
        self.weights = weights or {}

        # Initialize enabled evaluators
        pytest_cfg = pytest_config or {}
        if pytest_cfg.get("enabled", True):
            self.evaluators.append(
                PytestEvaluator(
                    timeout=pytest_cfg.get("timeout", 120),
                    args=pytest_cfg.get("args", ["--tb=short", "-q"]),
                )
            )
            if "weight" in pytest_cfg:
                self.weights["pytest"] = pytest_cfg["weight"]

        coverage_cfg = coverage_config or {}
        if coverage_cfg.get("enabled", True):
            self.evaluators.append(
                CoverageEvaluator(
                    timeout=coverage_cfg.get("timeout", 180),
                    source=coverage_cfg.get("source", "src"),
                    threshold=coverage_cfg.get("threshold", 70),
                )
            )
            if "weight" in coverage_cfg:
                self.weights["coverage"] = coverage_cfg["weight"]

        ruff_cfg = ruff_config or {}
        if ruff_cfg.get("enabled", False):
            self.evaluators.append(
                RuffEvaluator(
                    timeout=ruff_cfg.get("timeout", 30),
                    max_errors=ruff_cfg.get("max_errors", 100),
                    source=ruff_cfg.get("source", "src"),
                )
            )
            if "weight" in ruff_cfg:
                self.weights["ruff"] = ruff_cfg["weight"]

        pyright_cfg = pyright_config or {}
        if pyright_cfg.get("enabled", False):
            self.evaluators.append(
                PyrightEvaluator(
                    timeout=pyright_cfg.get("timeout", 60),
                    max_errors=pyright_cfg.get("max_errors", 50),
                    source=pyright_cfg.get("source", "src"),
                )
            )
            if "weight" in pyright_cfg:
                self.weights["pyright"] = pyright_cfg["weight"]

    @classmethod
    def from_config(cls, config) -> "CompositeEvaluator":
        """Create from ObsidianConfig object."""
        weights = {
            "pytest": config.pytest.weight,
            "coverage": config.coverage.weight,
            "ruff": config.ruff.weight,
            "pyright": config.pyright.weight,
        }

        return cls(
            pytest_config={
                "enabled": config.pytest.enabled,
                "timeout": config.pytest.timeout,
                "args": config.pytest.args,
                "weight": config.pytest.weight,
            },
            coverage_config={
                "enabled": config.coverage.enabled,
                "timeout": config.coverage.timeout,
                "source": config.coverage.source,
                "threshold": config.coverage.threshold,
                "weight": config.coverage.weight,
            },
            ruff_config={
                "enabled": config.ruff.enabled,
                "timeout": config.ruff.timeout,
                "max_errors": config.ruff.max_errors,
                "weight": config.ruff.weight,
            },
            pyright_config={
                "enabled": config.pyright.enabled,
                "timeout": config.pyright.timeout,
                "weight": config.pyright.weight,
            },
            weights=weights,
        )

    def evaluate(self, project_path: str) -> CompositeResult:
        """
        Run all evaluators and compute composite reward.

        Runs evaluators in parallel using ThreadPoolExecutor.
        """
        import time

        start_time = time.perf_counter()
        results = []

        if not self.evaluators:
            return CompositeResult(
                reward=1.0,
                results=[],
                all_passed=True,
                failed_evaluators=[],
                execution_time_ms=0,
                weights={},
            )

        # Run evaluators in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_evaluator = {
                executor.submit(evaluator.collect, project_path): evaluator
                for evaluator in self.evaluators
            }

            for future in concurrent.futures.as_completed(future_to_evaluator):
                evaluator = future_to_evaluator[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # Create error result for failed evaluator
                    results.append(
                        EvalResult(
                            name=evaluator.name,
                            score=0.0,
                            passed=False,
                            error=str(e),
                        )
                    )

        execution_time = (time.perf_counter() - start_time) * 1000

        # Compute composite reward
        reward = compute_composite_reward(results, self.weights)

        # Determine which evaluators failed
        failed = [r.name for r in results if r.failed]
        all_passed = len(failed) == 0

        return CompositeResult(
            reward=reward,
            results=results,
            all_passed=all_passed,
            failed_evaluators=failed,
            execution_time_ms=execution_time,
            weights=self.weights,
        )


def format_composite_feedback(
    result: CompositeResult,
    max_failures: int = 5,
) -> str:
    """Format composite evaluation result for feedback message."""
    lines = []

    for eval_result in result.results:
        status = "PASS" if eval_result.passed else "FAIL"
        skipped = eval_result.details.get("skipped", False) if eval_result.details else False

        if skipped:
            lines.append(f"  {eval_result.name}: SKIPPED (not installed)")
        else:
            lines.append(f"  {eval_result.name}: {eval_result.score:.1%} [{status}]")

            # Add details for failed evaluators
            if not eval_result.passed and eval_result.details:
                if eval_result.name == "pytest":
                    detail_text = format_pytest_failures(eval_result.details, max_failures)
                elif eval_result.name == "coverage":
                    detail_text = format_coverage_details(eval_result.details)
                elif eval_result.name == "ruff":
                    detail_text = format_ruff_issues(eval_result.details, max_failures)
                elif eval_result.name == "pyright":
                    detail_text = format_pyright_diagnostics(eval_result.details, max_failures)
                else:
                    detail_text = ""

                if detail_text:
                    # Indent the details
                    for line in detail_text.split("\n"):
                        lines.append(f"    {line}")

    return "\n".join(lines)
