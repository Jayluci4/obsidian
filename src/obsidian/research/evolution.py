"""
Evolutionary Operations for Research Mode.

Implements the four main evolutionary operations:
- MUTATE: Modify an existing solution
- CROSSOVER: Combine two solutions (2 or 3 parents)
- EXPLORE: Try a new approach in an underexplored niche
- EXPLOIT: Refine the best solution further

These operations guide Claude's search through the solution space.

AlphaEvolve-style enhancements:
- Adaptive operation selection using multi-armed bandits (UCB1, Thompson)
- Multi-parent crossover (3 parents)
- Strategic prompt sampling
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from obsidian.research.archive import Solution, SolutionArchive
    from obsidian.research.problem import EvolutionConfig, ProblemSpec

from obsidian.research.bandit import BanditAlgorithm, BanditConfig, MultiArmedBandit


class OperationType(Enum):
    """Types of evolutionary operations."""

    MUTATE = "mutate"
    CROSSOVER = "crossover"
    EXPLORE = "explore"
    EXPLOIT = "exploit"


@dataclass
class OperationContext:
    """Context for an evolutionary operation."""

    operation_type: OperationType
    parent_solutions: list["Solution"]
    target_niche: dict[str, str] | None = None
    mutation_instructions: str = ""
    crossover_instructions: str = ""
    exploration_instructions: str = ""
    exploitation_instructions: str = ""


class EvolutionaryOperator(ABC):
    """Base class for evolutionary operations."""

    @abstractmethod
    def get_context(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
    ) -> OperationContext:
        """Get operation context for prompt building."""
        pass

    @abstractmethod
    def get_instruction(self) -> str:
        """Get natural language instruction for Claude."""
        pass


class MutateOperation(EvolutionaryOperator):
    """
    Mutate an existing solution.

    Selects a parent solution and asks Claude to modify it
    in a specific way while preserving its core approach.
    """

    MUTATION_PROMPTS = {
        "light": [
            "Make a small improvement to the efficiency of this solution",
            "Fix any edge cases that might be missing",
            "Simplify the code without changing the approach",
            "Add better error handling",
        ],
        "medium": [
            "Optimize the core algorithm for better performance",
            "Refactor to improve the design while keeping the approach",
            "Enhance the solution with a complementary technique",
            "Generalize the solution to handle more cases",
        ],
        "heavy": [
            "Significantly restructure the implementation",
            "Replace a major component with a better alternative",
            "Combine multiple optimization strategies",
            "Rewrite with a focus on scalability",
        ],
    }

    def __init__(self, strength: str = "medium"):
        self.strength = strength

    def get_context(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
    ) -> OperationContext:
        """Select parent and mutation type."""
        parent = archive.get_parent_for_mutation()

        if parent is None:
            # No parent available, switch to explore
            return OperationContext(
                operation_type=OperationType.EXPLORE,
                parent_solutions=[],
                exploration_instructions="Start with a new approach since no solutions exist yet.",
            )

        # Select mutation prompt
        prompts = self.MUTATION_PROMPTS.get(self.strength, self.MUTATION_PROMPTS["medium"])
        mutation_instruction = random.choice(prompts)

        return OperationContext(
            operation_type=OperationType.MUTATE,
            parent_solutions=[parent],
            mutation_instructions=mutation_instruction,
        )

    def get_instruction(self) -> str:
        return f"Apply a {self.strength} mutation to improve an existing solution."


class CrossoverOperation(EvolutionaryOperator):
    """
    Combine two solutions.

    Selects two parent solutions from different niches
    and asks Claude to combine their best aspects.
    """

    CROSSOVER_PROMPTS = [
        "Combine the best aspects of both solutions into a hybrid approach",
        "Use the core algorithm from Solution A with the optimization from Solution B",
        "Merge the techniques: take the structure from one and the logic from the other",
        "Create a new solution that leverages the strengths of both parents",
        "Synthesize a solution that avoids the weaknesses of both approaches",
    ]

    def get_context(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
    ) -> OperationContext:
        """Select two parents for crossover."""
        parents = archive.get_parents_for_crossover()

        if parents is None:
            # Not enough solutions, switch to explore
            return OperationContext(
                operation_type=OperationType.EXPLORE,
                parent_solutions=[],
                exploration_instructions="Not enough solutions for crossover, try a new approach.",
            )

        crossover_instruction = random.choice(self.CROSSOVER_PROMPTS)

        return OperationContext(
            operation_type=OperationType.CROSSOVER,
            parent_solutions=list(parents),
            crossover_instructions=crossover_instruction,
        )

    def get_instruction(self) -> str:
        return "Combine ideas from two different solutions."


class MultiParentCrossoverOperation(EvolutionaryOperator):
    """
    Combine three solutions (AlphaEvolve-style multi-parent crossover).

    Selects three diverse parent solutions and asks Claude
    to combine their best aspects with role-based guidance.
    """

    MULTI_CROSSOVER_PROMPTS = [
        "Combine: core algorithm from Solution A, optimizations from Solution B, edge-case handling from Solution C",
        "Synthesize: A's approach + B's data structures + C's performance techniques",
        "Create hybrid: best algorithmic idea from A, best optimization from B, best validation from C",
        "Merge three approaches: take the foundation from A, enhance with B's technique, polish with C's refinements",
        "Build on all three: use A's structure as base, incorporate B's key insight, apply C's efficiency tricks",
    ]

    def get_context(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
    ) -> OperationContext:
        """Select three diverse parents for multi-parent crossover."""
        # Use fitness-diversity selection if available
        if hasattr(archive, "get_parents_for_multi_crossover"):
            parents = archive.get_parents_for_multi_crossover(n=3)
        else:
            # Fallback to getting diverse sample
            parents = archive.get_diverse_sample(3)

        if len(parents) < 3:
            # Not enough solutions, fall back to regular crossover or explore
            if len(parents) >= 2:
                return OperationContext(
                    operation_type=OperationType.CROSSOVER,
                    parent_solutions=parents[:2],
                    crossover_instructions="Combine the best aspects of both solutions.",
                )
            return OperationContext(
                operation_type=OperationType.EXPLORE,
                parent_solutions=[],
                exploration_instructions="Not enough solutions for crossover, try a new approach.",
            )

        crossover_instruction = random.choice(self.MULTI_CROSSOVER_PROMPTS)

        return OperationContext(
            operation_type=OperationType.CROSSOVER,
            parent_solutions=parents,
            crossover_instructions=crossover_instruction,
        )

    def get_instruction(self) -> str:
        return "Combine ideas from three different solutions."


class ExploreOperation(EvolutionaryOperator):
    """
    Explore a new approach.

    Targets underexplored niches or tries completely
    different algorithmic strategies.
    """

    EXPLORATION_PROMPTS = [
        "Try a completely different algorithmic approach",
        "Explore an unconventional solution that others might not consider",
        "Use a different paradigm (e.g., iterative vs recursive, greedy vs dynamic)",
        "Apply techniques from a different domain to this problem",
        "Start fresh with a focus on simplicity over sophistication",
        "Design a solution optimized for a different trade-off",
    ]

    def get_context(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
    ) -> OperationContext:
        """Find underexplored niche or suggest new approach."""
        # Try to find underexplored niche
        target_niche = archive.get_underexplored_niche()

        exploration_instruction = random.choice(self.EXPLORATION_PROMPTS)

        if target_niche:
            niche_desc = ", ".join(f"{k}={v}" for k, v in target_niche.items())
            exploration_instruction += f"\n\nTarget niche: {niche_desc}"

        # Include some existing solutions for context (what NOT to do)
        existing = archive.get_diverse_sample(3)

        return OperationContext(
            operation_type=OperationType.EXPLORE,
            parent_solutions=existing,  # For reference, not modification
            target_niche=target_niche,
            exploration_instructions=exploration_instruction,
        )

    def get_instruction(self) -> str:
        return "Explore a new approach different from existing solutions."


class ExploitOperation(EvolutionaryOperator):
    """
    Exploit the best solution.

    Takes the current best solution and applies
    focused optimization to squeeze out more performance.
    """

    EXPLOITATION_PROMPTS = [
        "This is our best solution. Optimize it further without changing the core approach.",
        "Fine-tune this solution: focus on micro-optimizations",
        "The approach is working. Make it more efficient.",
        "Polish this solution: improve constants, reduce overhead",
        "This solution is promising. Push it to its limits.",
    ]

    def get_context(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
    ) -> OperationContext:
        """Get best solution for exploitation."""
        best = archive.get_best_for_exploitation()

        if best is None:
            # No solutions, switch to explore
            return OperationContext(
                operation_type=OperationType.EXPLORE,
                parent_solutions=[],
                exploration_instructions="No solutions to exploit, start fresh.",
            )

        exploitation_instruction = random.choice(self.EXPLOITATION_PROMPTS)

        return OperationContext(
            operation_type=OperationType.EXPLOIT,
            parent_solutions=[best],
            exploitation_instructions=exploitation_instruction,
        )

    def get_instruction(self) -> str:
        return "Optimize the best solution further."


class EvolutionController:
    """
    Controller for evolutionary operations.

    Selects which operation to perform based on configuration
    and current archive state.
    """

    def __init__(self, config: "EvolutionConfig"):
        self.config = config

        # Initialize operators
        self.mutate_op = MutateOperation(strength=config.mutation_strength)
        self.crossover_op = CrossoverOperation()
        self.explore_op = ExploreOperation()
        self.exploit_op = ExploitOperation()

    def select_operation(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
        iteration: int = 0,
    ) -> OperationContext:
        """
        Select and configure an operation.

        Args:
            archive: Current solution archive
            problem: Problem specification
            iteration: Current iteration number

        Returns:
            Operation context with all needed information
        """
        # Early iterations: favor exploration
        if iteration < 10 or len(archive) < 3:
            return self.explore_op.get_context(archive, problem)

        # Select operation based on probabilities
        r = random.random()

        cumulative = 0.0

        cumulative += self.config.mutate_prob
        if r < cumulative:
            return self.mutate_op.get_context(archive, problem)

        cumulative += self.config.crossover_prob
        if r < cumulative:
            return self.crossover_op.get_context(archive, problem)

        cumulative += self.config.explore_prob
        if r < cumulative:
            return self.explore_op.get_context(archive, problem)

        # Exploit
        return self.exploit_op.get_context(archive, problem)

    def get_operation_name(self, op_type: OperationType) -> str:
        """Get human-readable operation name."""
        return {
            OperationType.MUTATE: "Mutation",
            OperationType.CROSSOVER: "Crossover",
            OperationType.EXPLORE: "Exploration",
            OperationType.EXPLOIT: "Exploitation",
        }.get(op_type, "Unknown")


class AdaptiveEvolutionController(EvolutionController):
    """
    Adaptive evolution controller using multi-armed bandits (AlphaEvolve-style).

    Instead of fixed operation probabilities, learns which operations
    work best based on historical performance using UCB1 or Thompson Sampling.
    """

    def __init__(
        self,
        config: "EvolutionConfig",
        state_dir: Path | None = None,
    ):
        super().__init__(config)

        self.state_dir = state_dir

        # Setup bandit for operation selection
        arms = [op.value for op in OperationType]

        bandit_config = BanditConfig(
            algorithm=BanditAlgorithm(config.adaptive.algorithm),
            exploration_factor=config.adaptive.exploration_factor,
            epsilon=config.adaptive.epsilon,
            min_trials_per_arm=config.adaptive.min_trials_per_arm,
        )

        db_path = state_dir / "operation_bandit.db" if state_dir else None
        self.operation_bandit = MultiArmedBandit(
            arms=arms,
            config=bandit_config,
            db_path=db_path,
            table_name="operation_stats",
        )

        # Multi-parent crossover operator
        self.multi_crossover_op = MultiParentCrossoverOperation()

        # Track last operation for reward attribution
        self._last_operation: OperationType | None = None
        self._last_score: float | None = None

    def select_operation(
        self,
        archive: "SolutionArchive",
        problem: "ProblemSpec",
        iteration: int = 0,
    ) -> OperationContext:
        """
        Select operation using adaptive bandit algorithm.

        Early iterations still favor exploration to build initial archive.
        After that, uses bandit to select based on learned performance.
        """
        # Early iterations: favor exploration to build archive
        if iteration < 10 or len(archive) < 3:
            self._last_operation = OperationType.EXPLORE
            return self.explore_op.get_context(archive, problem)

        # Use bandit to select operation
        selected_arm = self.operation_bandit.select()
        op_type = OperationType(selected_arm)
        self._last_operation = op_type

        # Get context from appropriate operator
        if op_type == OperationType.MUTATE:
            return self.mutate_op.get_context(archive, problem)
        elif op_type == OperationType.CROSSOVER:
            # Use multi-parent crossover if configured
            if self.config.crossover_parents >= 3:
                return self.multi_crossover_op.get_context(archive, problem)
            return self.crossover_op.get_context(archive, problem)
        elif op_type == OperationType.EXPLORE:
            return self.explore_op.get_context(archive, problem)
        else:  # EXPLOIT
            return self.exploit_op.get_context(archive, problem)

    def record_outcome(
        self,
        score_before: float | None,
        score_after: float,
        success: bool | None = None,
    ) -> None:
        """
        Record outcome of last operation for bandit learning.

        Args:
            score_before: Score before the operation (or None if first)
            score_after: Score after the operation
            success: Whether this was considered a success (if None, computed from improvement)
        """
        if self._last_operation is None:
            return

        # Compute improvement
        if score_before is not None:
            improvement = score_after - score_before
        else:
            improvement = score_after  # First solution, use absolute score

        # Update bandit
        self.operation_bandit.update(
            arm=self._last_operation.value,
            reward=improvement,
            success=success if success is not None else improvement > 0,
        )

        self._last_score = score_after

    def get_operation_stats(self) -> dict[str, Any]:
        """Get statistics about operation performance."""
        return self.operation_bandit.get_stats()

    def get_best_operation(self) -> str:
        """Get the operation with best average performance."""
        return self.operation_bandit.get_best_arm()


def create_evolution_controller(
    config: "EvolutionConfig",
    state_dir: Path | None = None,
) -> EvolutionController:
    """
    Factory function to create appropriate evolution controller.

    Returns AdaptiveEvolutionController if adaptive mode is enabled,
    otherwise returns standard EvolutionController.
    """
    if config.adaptive.enabled:
        return AdaptiveEvolutionController(config, state_dir)
    return EvolutionController(config)
