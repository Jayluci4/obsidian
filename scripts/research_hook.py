#!/usr/bin/env python3
"""
Obsidian Research Mode Hook.

This script runs as the Stop hook for research mode:
1. Evaluates the current solution (correctness, benchmark, novelty)
2. Adds successful solutions to the archive
3. Selects the next evolutionary operation
4. Injects feedback and instructions for the next iteration
5. Continues until target achieved or max iterations reached

Usage:
    Triggered by Claude Code Stop hook
    Input: JSON from stdin with session_id, cwd
    Output: JSON with decision (block/allow) and feedback
"""

import json
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from obsidian.logging import ObsidianLogger, setup_logging
from obsidian.research.archive import SolutionArchive
from obsidian.research.evolution import (
    AdaptiveEvolutionController,
    EvolutionController,
    OperationType,
    create_evolution_controller,
)
from obsidian.research.problem import load_problem, validate_problem
from obsidian.research.prompt_builder import ResearchPromptBuilder
from obsidian.research.prompt_sampler import PromptSampler
from obsidian.research.universal_evaluator import UniversalEvaluator


def load_research_state(state_dir: Path) -> dict:
    """Load research state from disk."""
    state_file = state_dir / "research_state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {"iteration": 0, "best_score": 0.0, "start_time": time.time()}


def save_research_state(state_dir: Path, state: dict) -> None:
    """Save research state to disk."""
    state_file = state_dir / "research_state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def main():
    """Main research hook logic."""
    # Read input from Claude Code
    input_data = json.load(sys.stdin)
    session_id = input_data.get("session_id", "research")
    cwd = Path(input_data.get("cwd", os.getcwd()))

    # Setup paths
    state_dir = cwd / ".obsidian"
    state_dir.mkdir(exist_ok=True)

    problem_file = cwd / "problem.yaml"
    if not problem_file.exists():
        # No problem file, allow stop
        print(json.dumps({"continue": False}))
        return

    # Setup logging
    logger = None
    obs_logger = None
    try:
        logger = setup_logging(
            state_dir=state_dir,
            level="INFO",
            log_file="research.log",
        )
        obs_logger = ObsidianLogger(logger)
        obs_logger.hook_start("research", session_id)
    except Exception as e:
        sys.stderr.write(f"Warning: Logging setup failed: {e}\n")

    try:
        # Load problem specification
        problem = load_problem(problem_file)
        errors = validate_problem(problem)
        if errors:
            sys.stderr.write(f"Problem validation errors: {errors}\n")
            print(json.dumps({"continue": False}))
            return

        # Load state
        state = load_research_state(state_dir)
        iteration = state.get("iteration", 0) + 1

        # Initialize components
        archive = SolutionArchive(
            config=problem.archive,
            db_path=state_dir / "archive.db",
        )

        evaluator = UniversalEvaluator(
            problem=problem,
            archive=archive,
            working_dir=cwd,
        )

        # Use factory to create correct controller type (adaptive or standard)
        evolution = create_evolution_controller(problem.evolution, state_dir)
        prompt_builder = ResearchPromptBuilder(problem)

        # Initialize prompt sampler if enabled
        prompt_sampler = None
        if problem.evolution.prompt_sampling.enabled:
            prompt_sampler = PromptSampler(
                db_path=state_dir / "prompt_stats.db",
                epsilon=problem.evolution.prompt_sampling.epsilon,
            )

        # Check if solution file exists
        solution_path = cwd / problem.solution_file
        if not solution_path.exists():
            # No solution yet, continue to let Claude create one
            operation = evolution.select_operation(archive, problem, iteration)
            feedback = prompt_builder.build_iteration_prompt(
                operation=operation,
                archive=archive,
                iteration=iteration,
            )

            state["iteration"] = iteration
            save_research_state(state_dir, state)

            result = {
                "decision": "block",
                "reason": f"RESEARCH MODE - Iteration {iteration}\n\n{feedback}",
            }
            print(json.dumps(result))
            sys.exit(2)

        # Evaluate the solution
        evaluation = evaluator.evaluate(solution_path, iteration)

        if obs_logger:
            obs_logger.evaluation(
                evaluator="research",
                passed=evaluation.passed,
                score=evaluation.score,
                duration_ms=evaluation.duration_ms,
            )

        # Record outcome for adaptive learning
        if isinstance(evolution, AdaptiveEvolutionController):
            prev_best = state.get("best_score", 0)
            evolution.record_outcome(
                score_before=prev_best,
                score_after=evaluation.score,
            )

        # Record prompt outcome for prompt sampler
        if prompt_sampler:
            # Reward is the improvement over previous best
            prev_best = state.get("best_score", 0)
            reward = max(0, evaluation.score - prev_best)
            prompt_sampler.record_outcome(reward)

        # Add to archive if passed
        if evaluation.passed:
            operation_ctx = evolution.select_operation(archive, problem, iteration - 1)
            solution_code = solution_path.read_text()

            archive.add(
                code=solution_code,
                score=evaluation.score,
                niche_values=evaluation.niche_values,
                iteration=iteration,
                parent_ids=[s.id for s in operation_ctx.parent_solutions],
                operation=operation_ctx.operation_type.value,
                evaluation=evaluation.to_dict(),
            )

            if obs_logger:
                obs_logger.episode_added(
                    attempt_number=iteration,
                    reward=evaluation.score,
                    metrics={"benchmark": evaluation.benchmark.raw_score if evaluation.benchmark else 0},
                )

        # Update best score
        if evaluation.score > state.get("best_score", 0):
            state["best_score"] = evaluation.score

        # Check termination conditions
        target = problem.benchmark.target_score
        if target and evaluation.score >= target:
            # Target achieved!
            print(json.dumps({
                "continue": False,
                "message": f"Target achieved! Score: {evaluation.score:.4f}",
            }))
            return

        if iteration >= problem.loop.max_iterations:
            # Max iterations reached
            print(json.dumps({
                "continue": False,
                "message": f"Max iterations ({problem.loop.max_iterations}) reached. Best: {state['best_score']:.4f}",
            }))
            return

        # Check early stopping
        if problem.loop.early_stop_threshold:
            if evaluation.score >= problem.loop.early_stop_threshold:
                print(json.dumps({
                    "continue": False,
                    "message": f"Early stop threshold reached. Score: {evaluation.score:.4f}",
                }))
                return

        # Select next operation
        operation = evolution.select_operation(archive, problem, iteration)

        # Build feedback prompt
        feedback = prompt_builder.build_iteration_prompt(
            operation=operation,
            archive=archive,
            iteration=iteration,
            last_evaluation=evaluation,
        )

        # Add evaluation summary
        eval_summary = prompt_builder.build_feedback_prompt(evaluation, archive)

        # Add adaptive learning stats if enabled
        adaptive_stats = ""
        if isinstance(evolution, AdaptiveEvolutionController):
            stats = evolution.get_operation_stats()
            best_op = evolution.operation_bandit.get_best_arm() if stats else None
            adaptive_stats = f"\nAdaptive Learning: Best operation = {best_op}, Stats = {stats}"

        # Save checkpoint periodically
        if iteration % problem.loop.checkpoint_every == 0:
            archive.save_checkpoint(state_dir / f"checkpoint_{iteration}.json")

        # Save state
        state["iteration"] = iteration
        save_research_state(state_dir, state)

        # Build full response
        full_feedback = f"""
{'='*60}
OBSIDIAN RESEARCH MODE - Iteration {iteration}
{'='*60}

{eval_summary}{adaptive_stats}

{'='*60}
NEXT TASK
{'='*60}

{feedback}
"""

        result = {
            "decision": "block",
            "reason": full_feedback,
        }
        print(json.dumps(result))
        sys.exit(2)

    except Exception as e:
        if obs_logger:
            obs_logger.error("research", str(e))
        sys.stderr.write(f"Research hook error: {e}\n")
        import traceback
        traceback.print_exc()
        print(json.dumps({"continue": False}))
        sys.exit(1)


if __name__ == "__main__":
    main()
