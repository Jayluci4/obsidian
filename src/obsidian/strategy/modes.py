"""Strategy mode definitions for the learning loop."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StrategyMode(Enum):
    """Available strategy modes for the learning loop."""

    EXPLOIT = "exploit"  # Refine working approach
    EXPLORE = "explore"  # Try different approach
    AUTONOMOUS = "autonomous"  # Let model decide

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return self.value.upper()


@dataclass
class ModeRecommendation:
    """Recommendation for which strategy mode to use."""

    mode: StrategyMode
    confidence: float  # 0-1 confidence in recommendation
    reason: str  # Explanation for the recommendation
    evidence: dict[str, Any]  # Supporting data


# Mode characteristics
MODE_DESCRIPTIONS = {
    StrategyMode.EXPLOIT: (
        "Refine and improve the current approach. "
        "Focus on incremental improvements to what's working."
    ),
    StrategyMode.EXPLORE: (
        "Try a different approach. "
        "The current strategy isn't making progress."
    ),
    StrategyMode.AUTONOMOUS: (
        "Analyze the situation and decide autonomously. "
        "Consider both refinement and exploration."
    ),
}


# Mode-specific prompts
MODE_PROMPTS = {
    StrategyMode.EXPLOIT: (
        "Build on the highest-reward attempt. "
        "Make incremental improvements to what worked. "
        "Don't make large changes."
    ),
    StrategyMode.EXPLORE: (
        "Try a fundamentally different approach. "
        "Don't keep repeating what isn't working. "
        "Consider alternative strategies."
    ),
    StrategyMode.AUTONOMOUS: (
        "Analyze the reward history and decide whether to: "
        "(1) refine a working approach, or "
        "(2) try something new."
    ),
}


def get_mode_description(mode: StrategyMode) -> str:
    """Get description for a strategy mode."""
    return MODE_DESCRIPTIONS.get(mode, "Unknown mode")


def get_mode_prompt(mode: StrategyMode) -> str:
    """Get prompt guidance for a strategy mode."""
    return MODE_PROMPTS.get(mode, "")
