#!/usr/bin/env python3
"""
Run Obsidian research mode on bin packing problem.

This script simulates the research loop that normally runs during
Claude Code sessions, allowing us to test the full pipeline.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import json
import shutil
from obsidian.research.problem import load_problem
from obsidian.research.universal_evaluator import UniversalEvaluator
from obsidian.research.archive import SolutionArchive
from obsidian.research.evolution import create_evolution_controller
from obsidian.research.prompt_builder import ResearchPromptBuilder


def main():
    # Setup
    problem_dir = Path(__file__).parent
    state_dir = problem_dir / ".obsidian"
    state_dir.mkdir(exist_ok=True)

    # Load problem
    problem = load_problem(problem_dir / "problem.yaml")
    print(f"Problem: {problem.name}")
    print(f"Target score: {problem.benchmark.target_score}")
    print()

    # Create components
    archive = SolutionArchive(
        config=problem.archive,
        db_path=state_dir / "archive.db",
    )

    evaluator = UniversalEvaluator(problem, archive=archive)

    controller = create_evolution_controller(
        config=problem.evolution,
        state_dir=state_dir,
        prompt_sampling_enabled=problem.evolution.prompt_sampling.enabled,
        prompt_sampling_epsilon=problem.evolution.prompt_sampling.epsilon,
    )

    prompt_builder = ResearchPromptBuilder(problem)

    # Evaluate initial solution
    solution_path = problem_dir / problem.solution_file
    print("Evaluating initial solution...")
    result = evaluator.evaluate(solution_path)

    print(f"  Correctness: {result.correctness.passed}")
    print(f"  Benchmark: {result.benchmark.raw_score:.4f}")
    print(f"  Novelty: {result.novelty.score:.4f}")
    print(f"  Overall score: {result.score:.4f}")
    print()

    if result.passed:
        # Add to archive
        solution = archive.add(
            code=solution_path.read_text(),
            score=result.score,
            niche_values=result.niche_values or {},
            iteration=0,
            operation="initial",
        )
        if solution:
            print(f"Added to archive: {solution.id}")

    # Show archive stats
    stats = archive.get_stats()
    print(f"\nArchive: {stats['total_solutions']} solutions")
    print(f"Best score: {stats.get('best_score', 0):.4f}")

    # Select next operation
    op_context = controller.select_operation(archive, problem, iteration=1)
    print(f"\nNext operation: {op_context.operation_type.value}")

    # Build prompt for Claude
    prompt = prompt_builder.build_iteration_prompt(op_context, archive, iteration=1)
    print(f"\nPrompt preview (first 800 chars):")
    print("-" * 40)
    print(prompt[:800] + "...")
    print("-" * 40)

    # Show what Claude should do
    print("\nTo continue research:")
    print("1. Run: claude --cwd examples/bin_packing")
    print("2. Tell Claude to improve the priority function based on the feedback")
    print("3. The stop hook will evaluate and continue the loop")


if __name__ == "__main__":
    main()
