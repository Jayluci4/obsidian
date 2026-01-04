"""
Evolutionary Operations for Research Mode.

Implements the four main evolutionary operations:
- MUTATE: Modify an existing solution
- CROSSOVER: Combine two solutions
- EXPLORE: Try a new approach in an underexplored niche
- EXPLOIT: Refine the best solution further

These operations guide Claude's search through the solution space.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from obsidian.research.archive import Solution, SolutionArchive
    from obsidian.research.problem import EvolutionConfig, ProblemSpec


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
