#!/usr/bin/env python3
"""
Benchmark: Adaptive vs Baseline Evolution

Compares AlphaEvolve-style adaptive operation selection against
random baseline to measure if learning actually helps.

Usage:
    python scripts/benchmark_adaptive.py --iterations 50 --runs 5
    python scripts/benchmark_adaptive.py --problem examples/matmul_test/problem.yaml
    python scripts/benchmark_adaptive.py --plot  # Generate visualization

Output:
    - benchmark_results.json: Raw data
    - benchmark_summary.txt: Human-readable summary
    - benchmark_plot.png: Learning curves (if --plot)
"""

import argparse
import json
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Add src to path
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from obsidian.research.archive import ArchiveConfig, SolutionArchive
from obsidian.research.evolution import (
    AdaptiveEvolutionController,
    EvolutionController,
    OperationType,
    create_evolution_controller,
)
from obsidian.research.problem import (
    AdaptiveSelectionConfig,
    EvolutionConfig,
    NicheDefinition,
    ParentSelectionConfig,
    ProblemSpec,
    PromptSamplingConfig,
    load_problem,
)


@dataclass
class IterationLog:
    """Log for a single iteration."""
    iteration: int
    operation: str
    score: float
    improvement: float
    archive_size: int
    best_score: float
    timestamp: float


@dataclass
class RunLog:
    """Log for a complete run."""
    mode: str  # "adaptive" or "baseline"
    run_id: int
    iterations: list[IterationLog] = field(default_factory=list)
    final_best: float = 0.0
    final_archive_size: int = 0
    total_time: float = 0.0
    operation_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "run_id": self.run_id,
            "iterations": [asdict(it) for it in self.iterations],
            "final_best": self.final_best,
            "final_archive_size": self.final_archive_size,
            "total_time": self.total_time,
            "operation_counts": self.operation_counts,
        }


@dataclass
class BenchmarkResults:
    """Complete benchmark results."""
    adaptive_runs: list[RunLog] = field(default_factory=list)
    baseline_runs: list[RunLog] = field(default_factory=list)
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "adaptive_runs": [r.to_dict() for r in self.adaptive_runs],
            "baseline_runs": [r.to_dict() for r in self.baseline_runs],
            "config": self.config,
        }


class SolutionSimulator:
    """
    Simulates solution generation and scoring.

    Models the discovery process with:
    - Diminishing returns (harder to improve as score increases)
    - Operation-specific characteristics
    - Randomness to simulate real-world variance
    """

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)

        # Track what we've "discovered"
        self.discovered_approaches: set[str] = set()
        self.iteration_count = 0

    def simulate_score(
        self,
        operation: OperationType,
        current_best: float,
        archive_size: int,
        parent_scores: list[float] = None,
    ) -> tuple[float, dict[str, str]]:
        """
        Simulate a solution score based on operation type.

        Returns:
            (score, niche_values)
        """
        self.iteration_count += 1

        # Base improvement potential (diminishes as we get better)
        headroom = 1.0 - current_best

        # Operation-specific behavior
        if operation == OperationType.EXPLORE:
            # High variance, can find new approaches
            if random.random() < 0.3:  # 30% chance of breakthrough
                improvement = random.uniform(0.05, 0.15) * headroom
            else:
                improvement = random.uniform(-0.05, 0.05) * headroom
            approach = random.choice(["algebraic", "recursive", "hybrid", "numeric", "other"])

        elif operation == OperationType.EXPLOIT:
            # Low variance, small improvements on best
            improvement = random.uniform(0.0, 0.03) * headroom
            approach = "algebraic"  # Stick with what works

        elif operation == OperationType.MUTATE:
            # Medium variance
            if parent_scores:
                base = max(parent_scores)
            else:
                base = current_best * 0.9
            improvement = random.uniform(-0.02, 0.08) * headroom
            approach = random.choice(["algebraic", "hybrid", "numeric"])

        elif operation == OperationType.CROSSOVER:
            # Can combine good features
            if parent_scores and len(parent_scores) >= 2:
                base = (max(parent_scores) + sum(parent_scores) / len(parent_scores)) / 2
                improvement = random.uniform(0.0, 0.1) * headroom
            else:
                improvement = random.uniform(-0.02, 0.05) * headroom
            approach = random.choice(["hybrid", "algebraic"])
        else:
            improvement = random.uniform(-0.05, 0.05) * headroom
            approach = "other"

        # Compute final score
        score = max(0.0, min(1.0, current_best + improvement))

        # Determine multiplication count niche
        if score > 0.85:
            mult_count = "lt_7"
        elif score > 0.5:
            mult_count = "eq_7"
        else:
            mult_count = "gt_7"

        niche_values = {"approach": approach, "mult_count": mult_count}

        return score, niche_values


def create_adaptive_config() -> EvolutionConfig:
    """Create config with adaptive features enabled."""
    return EvolutionConfig(
        adaptive=AdaptiveSelectionConfig(
            enabled=True,
            algorithm="ucb1",
            exploration_factor=1.0,
        ),
        parent_config=ParentSelectionConfig(
            method="fitness_diversity",
            diversity_weight=0.3,
        ),
        crossover_parents=3,
        prompt_sampling=PromptSamplingConfig(
            enabled=True,
            epsilon=0.15,
        ),
    )


def create_baseline_config() -> EvolutionConfig:
    """Create config with adaptive features disabled (random selection)."""
    return EvolutionConfig(
        adaptive=AdaptiveSelectionConfig(enabled=False),
        parent_config=ParentSelectionConfig(method="tournament"),
        crossover_parents=2,
        prompt_sampling=PromptSamplingConfig(enabled=False),
    )


def run_single_benchmark(
    mode: str,
    run_id: int,
    num_iterations: int,
    problem: ProblemSpec,
    state_dir: Path,
    seed: int = None,
) -> RunLog:
    """Run a single benchmark (adaptive or baseline)."""

    # Create config based on mode
    if mode == "adaptive":
        config = create_adaptive_config()
    else:
        config = create_baseline_config()

    # Initialize components
    archive = SolutionArchive(
        config=ArchiveConfig(
            niches=problem.archive.niches,
            max_total_solutions=100,
        ),
    )

    run_state_dir = state_dir / f"{mode}_{run_id}"
    run_state_dir.mkdir(parents=True, exist_ok=True)

    evolution = create_evolution_controller(config, run_state_dir)
    simulator = SolutionSimulator(seed=seed)

    # Run log
    log = RunLog(mode=mode, run_id=run_id)
    operation_counts = {op.value: 0 for op in OperationType}

    best_score = 0.0
    start_time = time.time()

    for iteration in range(num_iterations):
        # Select operation
        op_context = evolution.select_operation(archive, problem, iteration)
        operation = op_context.operation_type
        operation_counts[operation.value] += 1

        # Get parent scores
        parent_scores = [p.score for p in op_context.parent_solutions]

        # Simulate solution
        score, niche_values = simulator.simulate_score(
            operation=operation,
            current_best=best_score,
            archive_size=len(archive),
            parent_scores=parent_scores,
        )

        improvement = score - best_score

        # Record outcome for adaptive learning
        if isinstance(evolution, AdaptiveEvolutionController):
            evolution.record_outcome(
                score_before=best_score,
                score_after=score,
            )

        # Add to archive if it passes (score > 0.3)
        if score > 0.3:
            archive.add(
                code=f"def solution_{iteration}(): pass",
                score=score,
                niche_values=niche_values,
                iteration=iteration,
                parent_ids=[p.id for p in op_context.parent_solutions],
                operation=operation.value,
            )

        # Update best
        if score > best_score:
            best_score = score

        # Log iteration
        log.iterations.append(IterationLog(
            iteration=iteration,
            operation=operation.value,
            score=score,
            improvement=improvement,
            archive_size=len(archive),
            best_score=best_score,
            timestamp=time.time() - start_time,
        ))

    # Finalize log
    log.final_best = best_score
    log.final_archive_size = len(archive)
    log.total_time = time.time() - start_time
    log.operation_counts = operation_counts

    return log


def run_benchmark(
    num_iterations: int = 50,
    num_runs: int = 5,
    problem_path: Path = None,
    output_dir: Path = None,
    seed: int = 42,
) -> BenchmarkResults:
    """Run complete benchmark comparing adaptive vs baseline."""

    # Load or create problem
    if problem_path and problem_path.exists():
        problem = load_problem(problem_path)
    else:
        problem = ProblemSpec(
            name="Benchmark Problem",
            description="Simulated benchmark",
            archive=ArchiveConfig(
                niches=[
                    NicheDefinition(name="approach", values=["algebraic", "recursive", "hybrid", "numeric", "other"]),
                    NicheDefinition(name="mult_count", values=["lt_7", "eq_7", "gt_7"]),
                ],
            ),
        )

    # Setup output
    if output_dir is None:
        output_dir = Path(".obsidian/benchmark")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = BenchmarkResults(
        config={
            "num_iterations": num_iterations,
            "num_runs": num_runs,
            "seed": seed,
            "problem": problem.name,
        }
    )

    print(f"Running benchmark: {num_runs} runs x {num_iterations} iterations")
    print("=" * 60)

    # Run adaptive
    print("\n[ADAPTIVE MODE]")
    for run_id in range(num_runs):
        run_seed = seed + run_id if seed else None
        log = run_single_benchmark(
            mode="adaptive",
            run_id=run_id,
            num_iterations=num_iterations,
            problem=problem,
            state_dir=output_dir,
            seed=run_seed,
        )
        results.adaptive_runs.append(log)
        print(f"  Run {run_id + 1}: best={log.final_best:.4f}, archive={log.final_archive_size}, time={log.total_time:.2f}s")

    # Run baseline
    print("\n[BASELINE MODE]")
    for run_id in range(num_runs):
        run_seed = seed + run_id if seed else None
        log = run_single_benchmark(
            mode="baseline",
            run_id=run_id,
            num_iterations=num_iterations,
            problem=problem,
            state_dir=output_dir,
            seed=run_seed,
        )
        results.baseline_runs.append(log)
        print(f"  Run {run_id + 1}: best={log.final_best:.4f}, archive={log.final_archive_size}, time={log.total_time:.2f}s")

    return results


def compute_statistics(runs: list[RunLog]) -> dict[str, float]:
    """Compute statistics across runs."""
    if not runs:
        return {}

    final_bests = [r.final_best for r in runs]
    archive_sizes = [r.final_archive_size for r in runs]

    # Compute mean scores at each iteration
    num_iterations = len(runs[0].iterations)
    mean_curve = []
    for i in range(num_iterations):
        scores = [r.iterations[i].best_score for r in runs]
        mean_curve.append(sum(scores) / len(scores))

    # Area under curve (proxy for learning speed)
    auc = sum(mean_curve) / len(mean_curve)

    # Operation distribution
    total_ops = sum(sum(r.operation_counts.values()) for r in runs)
    op_dist = {}
    for op in OperationType:
        count = sum(r.operation_counts.get(op.value, 0) for r in runs)
        op_dist[op.value] = count / total_ops if total_ops > 0 else 0

    return {
        "mean_final_best": sum(final_bests) / len(final_bests),
        "std_final_best": (sum((x - sum(final_bests)/len(final_bests))**2 for x in final_bests) / len(final_bests)) ** 0.5,
        "min_final_best": min(final_bests),
        "max_final_best": max(final_bests),
        "mean_archive_size": sum(archive_sizes) / len(archive_sizes),
        "auc": auc,
        "mean_curve": mean_curve,
        "operation_distribution": op_dist,
    }


def print_summary(results: BenchmarkResults) -> str:
    """Generate human-readable summary."""

    adaptive_stats = compute_statistics(results.adaptive_runs)
    baseline_stats = compute_statistics(results.baseline_runs)

    lines = []
    lines.append("=" * 60)
    lines.append("BENCHMARK RESULTS: Adaptive vs Baseline")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Configuration:")
    lines.append(f"  Iterations per run: {results.config.get('num_iterations', 'N/A')}")
    lines.append(f"  Number of runs: {results.config.get('num_runs', 'N/A')}")
    lines.append(f"  Random seed: {results.config.get('seed', 'N/A')}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("FINAL SCORES")
    lines.append("-" * 60)
    lines.append(f"                    ADAPTIVE        BASELINE        DELTA")
    lines.append(f"  Mean best:        {adaptive_stats['mean_final_best']:.4f}          {baseline_stats['mean_final_best']:.4f}          {adaptive_stats['mean_final_best'] - baseline_stats['mean_final_best']:+.4f}")
    lines.append(f"  Std dev:          {adaptive_stats['std_final_best']:.4f}          {baseline_stats['std_final_best']:.4f}")
    lines.append(f"  Min:              {adaptive_stats['min_final_best']:.4f}          {baseline_stats['min_final_best']:.4f}")
    lines.append(f"  Max:              {adaptive_stats['max_final_best']:.4f}          {baseline_stats['max_final_best']:.4f}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("LEARNING SPEED (Area Under Curve)")
    lines.append("-" * 60)
    auc_delta = adaptive_stats['auc'] - baseline_stats['auc']
    auc_pct = (auc_delta / baseline_stats['auc'] * 100) if baseline_stats['auc'] > 0 else 0
    lines.append(f"  Adaptive AUC:     {adaptive_stats['auc']:.4f}")
    lines.append(f"  Baseline AUC:     {baseline_stats['auc']:.4f}")
    lines.append(f"  Delta:            {auc_delta:+.4f} ({auc_pct:+.1f}%)")
    lines.append("")

    lines.append("-" * 60)
    lines.append("OPERATION DISTRIBUTION")
    lines.append("-" * 60)
    lines.append(f"                    ADAPTIVE        BASELINE")
    for op in OperationType:
        a_pct = adaptive_stats['operation_distribution'].get(op.value, 0) * 100
        b_pct = baseline_stats['operation_distribution'].get(op.value, 0) * 100
        lines.append(f"  {op.value:12s}    {a_pct:5.1f}%           {b_pct:5.1f}%")
    lines.append("")

    lines.append("-" * 60)
    lines.append("ARCHIVE DIVERSITY")
    lines.append("-" * 60)
    lines.append(f"  Adaptive mean:    {adaptive_stats['mean_archive_size']:.1f} solutions")
    lines.append(f"  Baseline mean:    {baseline_stats['mean_archive_size']:.1f} solutions")
    lines.append("")

    # Verdict
    lines.append("=" * 60)
    lines.append("VERDICT")
    lines.append("=" * 60)

    score_delta = adaptive_stats['mean_final_best'] - baseline_stats['mean_final_best']
    if score_delta > 0.02:
        verdict = f"ADAPTIVE WINS (+{score_delta:.4f} score)"
    elif score_delta < -0.02:
        verdict = f"BASELINE WINS ({score_delta:.4f} score)"
    else:
        verdict = f"NO SIGNIFICANT DIFFERENCE (delta={score_delta:.4f})"

    lines.append(f"  {verdict}")
    lines.append("")

    if auc_delta > 0:
        lines.append(f"  Adaptive learned {auc_pct:.1f}% faster (higher AUC)")
    else:
        lines.append(f"  Baseline learned {-auc_pct:.1f}% faster (higher AUC)")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def generate_plot(results: BenchmarkResults, output_path: Path) -> None:
    """Generate learning curve plot."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Skipping plot generation.")
        print("Install with: pip install matplotlib")
        return

    adaptive_stats = compute_statistics(results.adaptive_runs)
    baseline_stats = compute_statistics(results.baseline_runs)

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # 1. Learning curves
    ax1 = axes[0, 0]
    iterations = list(range(len(adaptive_stats['mean_curve'])))
    ax1.plot(iterations, adaptive_stats['mean_curve'], 'b-', label='Adaptive', linewidth=2)
    ax1.plot(iterations, baseline_stats['mean_curve'], 'r--', label='Baseline', linewidth=2)
    ax1.set_xlabel('Iteration')
    ax1.set_ylabel('Best Score')
    ax1.set_title('Learning Curves (Mean across runs)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 2. Final score distribution
    ax2 = axes[0, 1]
    adaptive_finals = [r.final_best for r in results.adaptive_runs]
    baseline_finals = [r.final_best for r in results.baseline_runs]
    ax2.boxplot([adaptive_finals, baseline_finals], labels=['Adaptive', 'Baseline'])
    ax2.set_ylabel('Final Best Score')
    ax2.set_title('Final Score Distribution')
    ax2.grid(True, alpha=0.3)

    # 3. Operation distribution (adaptive)
    ax3 = axes[1, 0]
    ops = list(adaptive_stats['operation_distribution'].keys())
    adaptive_pcts = [adaptive_stats['operation_distribution'][op] * 100 for op in ops]
    baseline_pcts = [baseline_stats['operation_distribution'][op] * 100 for op in ops]
    x = range(len(ops))
    width = 0.35
    ax3.bar([i - width/2 for i in x], adaptive_pcts, width, label='Adaptive', color='blue', alpha=0.7)
    ax3.bar([i + width/2 for i in x], baseline_pcts, width, label='Baseline', color='red', alpha=0.7)
    ax3.set_xticks(x)
    ax3.set_xticklabels(ops, rotation=45)
    ax3.set_ylabel('Percentage')
    ax3.set_title('Operation Distribution')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 4. Individual run trajectories
    ax4 = axes[1, 1]
    for run in results.adaptive_runs:
        scores = [it.best_score for it in run.iterations]
        ax4.plot(scores, 'b-', alpha=0.3)
    for run in results.baseline_runs:
        scores = [it.best_score for it in run.iterations]
        ax4.plot(scores, 'r--', alpha=0.3)
    ax4.plot([], [], 'b-', label='Adaptive runs')
    ax4.plot([], [], 'r--', label='Baseline runs')
    ax4.set_xlabel('Iteration')
    ax4.set_ylabel('Best Score')
    ax4.set_title('Individual Run Trajectories')
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    print(f"Plot saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark adaptive vs baseline evolution"
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=50,
        help="Number of iterations per run (default: 50)"
    )
    parser.add_argument(
        "--runs", "-r",
        type=int,
        default=5,
        help="Number of runs per mode (default: 5)"
    )
    parser.add_argument(
        "--problem", "-p",
        type=Path,
        default=None,
        help="Path to problem.yaml (optional)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path(".obsidian/benchmark"),
        help="Output directory (default: .obsidian/benchmark)"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)"
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate visualization plot"
    )

    args = parser.parse_args()

    # Run benchmark
    results = run_benchmark(
        num_iterations=args.iterations,
        num_runs=args.runs,
        problem_path=args.problem,
        output_dir=args.output,
        seed=args.seed,
    )

    # Generate summary
    summary = print_summary(results)
    print("\n" + summary)

    # Save results
    results_path = args.output / "benchmark_results.json"
    with open(results_path, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    print(f"\nResults saved to: {results_path}")

    summary_path = args.output / "benchmark_summary.txt"
    with open(summary_path, "w") as f:
        f.write(summary)
    print(f"Summary saved to: {summary_path}")

    # Generate plot
    if args.plot:
        plot_path = args.output / "benchmark_plot.png"
        generate_plot(results, plot_path)


if __name__ == "__main__":
    main()
