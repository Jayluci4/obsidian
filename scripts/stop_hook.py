#!/usr/bin/env python3
"""
Obsidian Stop Hook: Main learning loop controller.

This hook runs after Claude finishes a response. It:
1. Checks circuit breaker state (prevents runaway loops)
2. Runs evaluators (pytest, coverage, ruff, pyright) to measure code quality
3. Analyzes response for completion/stuck patterns
4. Computes composite reward and tracks delta from baseline
5. Determines strategy mode (EXPLOIT/EXPLORE/AUTONOMOUS)
6. Decides whether to continue (exit code 2) or stop (exit code 0)
7. Injects ICRL feedback for the next iteration
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add src to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from obsidian.config import get_state_dir, load_config
from obsidian.errors import (
    EvaluatorError,
    GracefulDegradation,
    HookError,
    safe_execute,
)
from obsidian.evaluator import (
    CompositeEvaluator,
    DeltaTracker,
    ResponseAnalyzer,
    format_composite_feedback,
    format_delta_feedback,
)
from obsidian.logging import setup_logging, ObsidianLogger
from obsidian.state import StateManager
from obsidian.strategy import (
    CircuitBreaker,
    CircuitState,
    StrategyController,
    StrategyMode,
)


def get_git_diff_count(project_path: Path) -> int:
    """Count files changed via git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            files = [f for f in result.stdout.strip().split("\n") if f]
            return len(files)
    except Exception:
        pass
    return 0


def hash_failures(failures: list[str]) -> str:
    """Create hash of failures for circuit breaker."""
    if not failures:
        return ""
    content = "\n".join(sorted(set(f.lower().strip() for f in failures)))
    return hashlib.md5(content.encode()).hexdigest()[:16]


def format_feedback(
    composite_result,
    delta_result,
    state_manager,
    config,
    strategy_mode: StrategyMode,
    circuit_status: dict,
    is_stuck: bool = False,
) -> str:
    """Format feedback message for Claude's next iteration."""
    state = state_manager.load()

    lines = [
        "=" * 60,
        "OBSIDIAN LEARNING FEEDBACK",
        "=" * 60,
        "",
        f"Attempt: {state.attempt_count}",
        f"Current Reward: {composite_result.reward:.3f}",
        f"Best Reward: {state.best_reward:.3f}",
        f"Target: {config.success_threshold:.2f}",
        f"Strategy Mode: {strategy_mode.value.upper()}",
        "",
    ]

    # Add circuit breaker status if not normal
    if config.feedback.show_circuit_status and circuit_status.get("state") != "CLOSED":
        lines.extend([
            f"Circuit Breaker: {circuit_status.get('state')}",
            f"  Loops since progress: {circuit_status.get('consecutive_no_progress', 0)}",
            "",
        ])

    lines.append("Metrics:")

    # Add formatted metric details
    metrics_text = format_composite_feedback(
        composite_result, config.feedback.max_failures_shown
    )
    lines.append(metrics_text)

    # Add delta information
    if delta_result and config.feedback.include_coverage_delta:
        lines.extend(["", format_delta_feedback(delta_result)])

    # Add reward history trend
    if len(state.reward_history) > 1:
        recent = state.reward_history[-5:]
        if len(recent) >= 2:
            trend = recent[-1] - recent[-2]
            trend_str = f"+{trend:.3f}" if trend >= 0 else f"{trend:.3f}"
            lines.extend(["", f"Trend: {trend_str}"])

    # Add strategy-specific guidance
    if config.feedback.show_strategy_mode:
        lines.extend(["", "-" * 60])

        if strategy_mode == StrategyMode.EXPLOIT:
            lines.extend([
                "MODE: EXPLOIT - Refine current approach",
                "- Build on what's working",
                "- Make incremental improvements",
                "- Focus on the lowest-scoring metrics",
            ])
        elif strategy_mode == StrategyMode.EXPLORE:
            lines.extend([
                "MODE: EXPLORE - Try a different approach",
                "- Current strategy isn't making progress",
                "- Consider alternative solutions",
                "- Don't repeat the same patterns",
            ])
            if is_stuck:
                lines.append("- WARNING: Loop appears stuck - significant change needed")
        else:
            lines.extend([
                "MODE: AUTONOMOUS - Decide based on context",
                "- Analyze what's working and what isn't",
                "- Choose whether to refine or explore",
            ])

    lines.extend([
        "",
        "=" * 60,
    ])

    return "\n".join(lines)


def main():
    """Main hook handler."""
    start_time = time.time()

    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # No input or invalid JSON - allow stop
        print(json.dumps({"continue": True}))
        sys.exit(0)

    session_id = input_data.get("session_id", "default")
    cwd = input_data.get("cwd", os.getcwd())
    # Claude's response text (if provided by hook)
    transcript = input_data.get("transcript", "")

    project_path = Path(cwd)

    # Load configuration
    config = load_config(project_path)

    # Get state directory
    state_dir = get_state_dir(project_path, config)

    # Setup logging
    logger = None
    obs_logger = None
    if config.logging.enabled:
        try:
            logger = setup_logging(
                state_dir=state_dir,
                level=config.logging.level,
                log_file=config.logging.file,
                max_size_mb=config.logging.max_size_mb,
                backup_count=config.logging.backup_count,
                json_format=config.logging.json_format,
            )
            obs_logger = ObsidianLogger(logger)
            obs_logger.hook_start("stop", session_id)
        except Exception as e:
            # Continue without logging if setup fails
            sys.stderr.write(f"Warning: Logging setup failed: {e}\n")

    # Graceful degradation helper
    degradation = GracefulDegradation(obs_logger)

    # Initialize components
    state_manager = StateManager(state_dir, session_id)
    circuit_breaker = CircuitBreaker(state_dir)
    response_analyzer = ResponseAnalyzer()

    state = state_manager.load()

    # === CIRCUIT BREAKER CHECK ===
    should_halt, halt_reason = circuit_breaker.should_halt()
    if should_halt:
        if obs_logger and config.logging.log_circuit_breaker:
            obs_logger.circuit_breaker(
                state="OPEN",
                action="halting",
                loop_number=state.attempt_count,
                reason=halt_reason,
            )

        result_msg = (
            f"Circuit breaker OPEN: {halt_reason}. "
            f"Run with --reset-circuit to continue."
        )
        print(json.dumps({"continue": False, "stopReason": result_msg}))
        sys.exit(0)

    # === MAX ATTEMPTS CHECK ===
    if state.attempt_count >= config.max_attempts:
        if obs_logger:
            obs_logger.state_change(
                component="stop_hook",
                old_state="running",
                new_state="stopped",
                reason=f"Max attempts ({config.max_attempts}) reached",
            )

        result_msg = (
            f"Max attempts ({config.max_attempts}) reached. "
            f"Best reward: {state.best_reward:.3f}"
        )
        print(json.dumps({"continue": False, "stopReason": result_msg}))
        sys.exit(0)

    # === RESPONSE ANALYSIS ===
    response_analysis = None
    if transcript and config.response_analysis.enabled:
        response_analysis = safe_execute(
            lambda: response_analyzer.analyze(
                transcript,
                files_changed=get_git_diff_count(project_path),
            ),
            fallback=None,
            error_handler=lambda e: obs_logger.error("response_analyzer", str(e), e)
            if obs_logger
            else None,
        )

        # Check for explicit completion signals
        if response_analysis and response_analysis.exit_signal and response_analysis.has_completion_signal:
            # Claude thinks it's done - verify with evaluators before accepting
            pass  # Continue to evaluation

    # === RUN EVALUATORS ===
    eval_start = time.time()
    try:
        evaluator = CompositeEvaluator.from_config(config)
        composite_result = evaluator.evaluate(str(project_path))

        if obs_logger and config.logging.log_evaluations:
            eval_duration = (time.time() - eval_start) * 1000
            obs_logger.evaluation(
                evaluator="composite",
                passed=composite_result.all_passed,
                score=composite_result.reward,
                duration_ms=eval_duration,
                details={"metrics": composite_result.metrics},
            )
    except Exception as e:
        if obs_logger:
            obs_logger.error("evaluator", f"Evaluation failed: {e}", e)

        if config.error_handling.continue_on_evaluator_failure:
            # Create fallback result
            from obsidian.evaluator.composite import CompositeResult, EvaluatorResult
            composite_result = CompositeResult(
                reward=config.error_handling.fallback_reward,
                metrics={},
                results=[],
                all_passed=False,
            )
        else:
            raise HookError("stop", f"Evaluation failed: {e}", cause=e)

    # === DELTA TRACKING ===
    delta_tracker = DeltaTracker(state_dir)
    delta_result = safe_execute(
        lambda: delta_tracker.compute_delta(composite_result),
        fallback=None,
        error_handler=lambda e: obs_logger.error("delta_tracker", str(e), e)
        if obs_logger
        else None,
    )

    # Determine if there's progress
    has_progress = False
    reward_delta = 0.0

    if delta_result:
        reward_delta = delta_result.delta
        has_progress = delta_result.is_improvement
    else:
        # First attempt - any result is progress
        has_progress = True

    # Also check git changes
    files_changed = get_git_diff_count(project_path)
    if files_changed > 0:
        has_progress = True

    # Update baseline if significant improvement
    if delta_tracker.should_update_baseline(composite_result):
        delta_tracker.save_baseline(composite_result, state.attempt_count + 1)

    # === EXTRACT FAILURES ===
    failures = []
    for result in composite_result.results:
        if not result.passed and result.details:
            for failure in result.details.get("failures", [])[:5]:
                failures.append(f"[{result.name}] {failure.get('test', 'unknown')}")
            for failure in result.details.get("failure_details", [])[:5]:
                failures.append(f"[{result.name}] {failure.get('test', 'unknown')}")
            for issue in result.details.get("issues", [])[:3]:
                failures.append(f"[{result.name}] {issue.get('file', '')}:{issue.get('line', '')}")
            for diag in result.details.get("diagnostics", [])[:3]:
                failures.append(f"[{result.name}] {diag.get('file', '')}:{diag.get('line', '')}")

    error_hash = hash_failures(failures)

    # === UPDATE CIRCUIT BREAKER ===
    circuit_state, circuit_reason = circuit_breaker.record_result(
        loop_number=state.attempt_count + 1,
        has_progress=has_progress,
        has_errors=len(failures) > 0,
        error_hash=error_hash,
        reward_delta=reward_delta,
    )

    if obs_logger and config.logging.log_circuit_breaker:
        obs_logger.circuit_breaker(
            state=circuit_state.value,
            action="recorded",
            loop_number=state.attempt_count + 1,
            reason=circuit_reason,
        )

    # Check if circuit just opened
    if circuit_state == CircuitState.OPEN:
        result_msg = (
            f"Circuit breaker opened: {circuit_reason}. "
            f"Best reward: {state.best_reward:.3f}"
        )
        print(json.dumps({"continue": False, "stopReason": result_msg}))
        sys.exit(0)

    # === STORE EPISODE ===
    action_summary = ""
    if response_analysis and response_analysis.work_summary:
        action_summary = response_analysis.work_summary

    state_manager.add_episode(
        reward=composite_result.reward,
        metrics=composite_result.metrics,
        action_summary=action_summary,
        failures=failures[:10],
    )

    if obs_logger:
        obs_logger.episode_added(
            attempt_number=state.attempt_count + 1,
            reward=composite_result.reward,
            metrics=composite_result.metrics,
        )

    # Reload state after adding episode
    state = state_manager.load()

    # === STRATEGY MODE SELECTION ===
    strategy_mode = StrategyMode.AUTONOMOUS
    is_stuck = False

    try:
        strategy_controller = StrategyController(state_dir, session_id)
        mode_recommendation = strategy_controller.recommend_mode()
        strategy_mode = mode_recommendation.mode
        is_stuck = strategy_controller.analyze_stuck().is_stuck

        if obs_logger and config.logging.log_strategy_changes:
            obs_logger.strategy_change(
                old_mode="AUTONOMOUS",
                new_mode=strategy_mode.value,
                reward_trend=mode_recommendation.trend if hasattr(mode_recommendation, 'trend') else 0.0,
                is_stuck=is_stuck,
            )

        strategy_controller.close()
    except Exception as e:
        # Fallback to autonomous if strategy fails
        if obs_logger:
            obs_logger.warning("strategy", f"Strategy analysis failed: {e}, using AUTONOMOUS")
        strategy_mode = StrategyMode.AUTONOMOUS
        is_stuck = False

    # === CHECK TERMINATION CONDITIONS ===

    # 1. Target achieved
    if composite_result.reward >= config.success_threshold:
        if obs_logger:
            obs_logger.hook_end(
                hook_name="stop",
                duration_ms=(time.time() - start_time) * 1000,
                result="target_achieved",
            )

        result_msg = f"Target achieved! Reward: {composite_result.reward:.3f}"
        print(json.dumps({"continue": False, "stopReason": result_msg}))
        sys.exit(0)

    # 2. All evaluators pass
    if composite_result.all_passed:
        if obs_logger:
            obs_logger.hook_end(
                hook_name="stop",
                duration_ms=(time.time() - start_time) * 1000,
                result="all_passed",
            )

        result_msg = f"All checks pass. Reward: {composite_result.reward:.3f}"
        print(json.dumps({"continue": False, "stopReason": result_msg}))
        sys.exit(0)

    # 3. Response analysis suggests completion AND high reward
    if (
        response_analysis
        and response_analysis.exit_signal
        and response_analysis.has_completion_signal
        and composite_result.reward >= 0.85
    ):
        if obs_logger:
            obs_logger.hook_end(
                hook_name="stop",
                duration_ms=(time.time() - start_time) * 1000,
                result="completion_signal",
            )

        result_msg = f"Completion signal detected. Reward: {composite_result.reward:.3f}"
        print(json.dumps({"continue": False, "stopReason": result_msg}))
        sys.exit(0)

    # === CONTINUE - BUILD FEEDBACK ===
    circuit_status = circuit_breaker.get_status()

    feedback = format_feedback(
        composite_result=composite_result,
        delta_result=delta_result,
        state_manager=state_manager,
        config=config,
        strategy_mode=strategy_mode,
        circuit_status=circuit_status,
        is_stuck=is_stuck,
    )

    if obs_logger:
        obs_logger.hook_end(
            hook_name="stop",
            duration_ms=(time.time() - start_time) * 1000,
            result="continue",
        )

    # Exit code 2 = block stop and inject feedback
    output = {"decision": "block", "reason": feedback}

    print(json.dumps(output))
    sys.exit(2)


if __name__ == "__main__":
    main()
