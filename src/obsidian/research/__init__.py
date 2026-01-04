"""
Obsidian Research Mode: Long-running algorithm discovery with quality-diversity.

This module implements AlphaEvolve-style evolutionary search for novel algorithms:
- Problem specification system (user-defined evaluation)
- Universal evaluator (correctness, benchmark, novelty)
- Solution archive with MAP-Elites quality-diversity
- Evolutionary operations (mutate, crossover, explore, exploit)
"""

from obsidian.research.problem import ProblemSpec, load_problem
from obsidian.research.universal_evaluator import UniversalEvaluator, EvaluationResult
from obsidian.research.archive import SolutionArchive, Solution, Niche
from obsidian.research.evolution import (
    EvolutionaryOperator,
    MutateOperation,
    CrossoverOperation,
    ExploreOperation,
    ExploitOperation,
)
from obsidian.research.prompt_builder import ResearchPromptBuilder

__all__ = [
    "ProblemSpec",
    "load_problem",
    "UniversalEvaluator",
    "EvaluationResult",
    "SolutionArchive",
    "Solution",
    "Niche",
    "EvolutionaryOperator",
    "MutateOperation",
    "CrossoverOperation",
    "ExploreOperation",
    "ExploitOperation",
    "ResearchPromptBuilder",
]
