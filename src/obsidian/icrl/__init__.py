"""ICRL (In-Context Reinforcement Learning) module for context building."""

from .context_builder import ICRLContextBuilder
from .prompt_templates import (
    EXPERIENCE_BUFFER_TEMPLATE,
    META_INSTRUCTION_TEMPLATE,
    format_attempt,
    format_experience_buffer,
    format_meta_instruction,
)
from .episode_filter import (
    EpisodeFilter,
    FilteredEpisode,
    filter_episodes_for_context,
)
from .context_budget import (
    ContextBudgetManager,
    BudgetResult,
    estimate_tokens,
    estimate_episode_tokens,
    compress_episode,
)

__all__ = [
    "ICRLContextBuilder",
    "EXPERIENCE_BUFFER_TEMPLATE",
    "META_INSTRUCTION_TEMPLATE",
    "format_attempt",
    "format_experience_buffer",
    "format_meta_instruction",
    # Episode filtering
    "EpisodeFilter",
    "FilteredEpisode",
    "filter_episodes_for_context",
    # Context budget
    "ContextBudgetManager",
    "BudgetResult",
    "estimate_tokens",
    "estimate_episode_tokens",
    "compress_episode",
]
