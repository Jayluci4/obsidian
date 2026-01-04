"""Prompt templates for ICRL context injection."""

from typing import Any


# Template for wrapping the experience buffer
EXPERIENCE_BUFFER_TEMPLATE = """<experience_buffer>
{attempts}
</experience_buffer>"""


# Template for meta-instructions based on strategy mode
META_INSTRUCTION_TEMPLATE = """<meta_instruction>
Mode: {mode}
{instruction}
</meta_instruction>"""


# Mode-specific instructions
MODE_INSTRUCTIONS = {
    "EXPLOIT": (
        "Build on the highest-reward attempt shown above.\n"
        "Refine and improve what worked."
    ),
    "EXPLORE": (
        "Try a different approach than previous attempts.\n"
        "The current strategy appears stuck."
    ),
    "AUTONOMOUS": (
        "Analyze the pattern of rewards and decide whether to:\n"
        "- Refine a working approach (exploit)\n"
        "- Try something new (explore)"
    ),
}


def format_attempt(
    attempt_number: int,
    reward: float,
    action_summary: str,
    metrics: dict[str, float],
    failures: list[str] | None = None,
    is_best: bool = False,
) -> str:
    """
    Format a single attempt for the experience buffer.

    Args:
        attempt_number: The attempt sequence number
        reward: Composite reward for this attempt
        action_summary: Description of what was done
        metrics: Individual metric scores
        failures: List of failure messages
        is_best: Whether this is the best attempt so far

    Returns:
        Formatted attempt string
    """
    lines = []

    # Opening tag with attributes
    attrs = f'id="{attempt_number}" reward="{reward:.3f}"'
    if is_best:
        attrs += ' best="true"'
    lines.append(f"<attempt {attrs}>")

    # Action summary
    if action_summary:
        lines.append(f"Action: {action_summary}")

    # Metrics breakdown
    metrics_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(metrics.items()))
    lines.append(f"Metrics: {metrics_str}")

    # Failures (if any)
    if failures:
        lines.append("Issues:")
        for failure in failures[:3]:  # Limit to 3 failures
            lines.append(f"  - {failure}")

    lines.append("</attempt>")

    return "\n".join(lines)


def format_experience_buffer(
    attempts: list[dict[str, Any]],
    best_attempt_id: int | None = None,
) -> str:
    """
    Format multiple attempts into an experience buffer.

    Args:
        attempts: List of attempt dicts with keys:
            - attempt_number: int
            - reward: float
            - action_summary: str
            - metrics: dict[str, float]
            - failures: list[str] (optional)
        best_attempt_id: The attempt number of the best attempt

    Returns:
        Formatted experience buffer string
    """
    if not attempts:
        return ""

    formatted_attempts = []
    for attempt in attempts:
        is_best = attempt.get("attempt_number") == best_attempt_id
        formatted = format_attempt(
            attempt_number=attempt.get("attempt_number", 0),
            reward=attempt.get("reward", 0.0),
            action_summary=attempt.get("action_summary", ""),
            metrics=attempt.get("metrics", {}),
            failures=attempt.get("failures"),
            is_best=is_best,
        )
        formatted_attempts.append(formatted)

    attempts_str = "\n".join(formatted_attempts)
    return EXPERIENCE_BUFFER_TEMPLATE.format(attempts=attempts_str)


def format_meta_instruction(
    mode: str,
    custom_instruction: str | None = None,
    best_attempt: dict[str, Any] | None = None,
    trend: float | None = None,
    is_stuck: bool = False,
) -> str:
    """
    Format meta-instruction based on current strategy mode.

    Args:
        mode: Strategy mode ("EXPLOIT", "EXPLORE", or "AUTONOMOUS")
        custom_instruction: Optional custom instruction to append
        best_attempt: The best attempt so far (for EXPLOIT mode)
        trend: Recent reward trend
        is_stuck: Whether the reward appears stuck

    Returns:
        Formatted meta-instruction string
    """
    mode = mode.upper()
    if mode not in MODE_INSTRUCTIONS:
        mode = "AUTONOMOUS"

    instruction_parts = [MODE_INSTRUCTIONS[mode]]

    # Add context-specific guidance
    if mode == "EXPLOIT" and best_attempt:
        attempt_num = best_attempt.get("attempt_number", "unknown")
        reward = best_attempt.get("reward", 0.0)
        instruction_parts.append(
            f"Best attempt was #{attempt_num} with reward {reward:.3f}."
        )

    if trend is not None:
        trend_str = f"+{trend:.3f}" if trend >= 0 else f"{trend:.3f}"
        instruction_parts.append(f"Recent trend: {trend_str}")

    if is_stuck:
        instruction_parts.append(
            "WARNING: Progress appears stuck. Consider a different strategy."
        )

    if custom_instruction:
        instruction_parts.append(custom_instruction)

    instruction = "\n".join(instruction_parts)
    return META_INSTRUCTION_TEMPLATE.format(mode=mode, instruction=instruction)


def format_full_context(
    attempts: list[dict[str, Any]],
    mode: str = "AUTONOMOUS",
    best_attempt: dict[str, Any] | None = None,
    trend: float | None = None,
    is_stuck: bool = False,
    custom_instruction: str | None = None,
) -> str:
    """
    Format complete ICRL context with experience buffer and meta-instruction.

    Args:
        attempts: List of attempts for the experience buffer
        mode: Strategy mode
        best_attempt: The best attempt so far
        trend: Recent reward trend
        is_stuck: Whether progress is stuck
        custom_instruction: Optional custom instruction

    Returns:
        Complete formatted context string
    """
    parts = []

    # Add experience buffer
    if attempts:
        best_id = best_attempt.get("attempt_number") if best_attempt else None
        buffer = format_experience_buffer(attempts, best_id)
        if buffer:
            parts.append(buffer)

    # Add meta-instruction
    meta = format_meta_instruction(
        mode=mode,
        custom_instruction=custom_instruction,
        best_attempt=best_attempt,
        trend=trend,
        is_stuck=is_stuck,
    )
    parts.append(meta)

    return "\n\n".join(parts)
