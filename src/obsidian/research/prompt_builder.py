"""
Evolutionary Prompt Builder for Research Mode.

Builds prompts for Claude that include:
- Problem specification
- Current best solutions from archive
- Evolutionary operation instructions
- Evaluation feedback from previous attempts
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from obsidian.research.archive import Solution, SolutionArchive
    from obsidian.research.evolution import OperationContext, OperationType
    from obsidian.research.problem import ProblemSpec
    from obsidian.research.universal_evaluator import EvaluationResult


class ResearchPromptBuilder:
    """
    Builds prompts for evolutionary search.

    The prompt structure:
    1. Problem specification (what to solve)
    2. Solution archive (top solutions for reference)
    3. Operation instruction (mutate/crossover/explore/exploit)
    4. Evaluation history (what's been tried)
    5. Output format specification
    """

    def __init__(self, problem: "ProblemSpec"):
        self.problem = problem

    def build_system_prompt(self) -> str:
        """Build system prompt with problem specification."""
        known_algo_warning = self._format_known_algorithm_warning()

        return f"""You are an algorithm researcher working on: {self.problem.name}

PROBLEM DESCRIPTION:
{self.problem.description}
{known_algo_warning}
SOLUTION REQUIREMENTS:
- Write the solution to: {self.problem.solution_file}
- The solution must pass correctness tests
- The solution will be benchmarked for performance
- Novel approaches are valued (different from existing solutions)

{self._format_interface()}

EVALUATION CRITERIA:
- Correctness ({self.problem.weights.correctness:.0%}): Must pass all tests
- Benchmark ({self.problem.weights.benchmark:.0%}): {self.problem.benchmark.direction} the score
- Novelty ({self.problem.weights.novelty:.0%}): Different from existing solutions
- Known Algorithm Penalty: SEVERE penalty for implementing known algorithms

OUTPUT FORMAT:
When you generate a solution, write the complete code to {self.problem.solution_file}.
Do not explain or discuss - just write the code.
"""

    def _format_known_algorithm_warning(self) -> str:
        """Format warning about known algorithms."""
        config = self.problem.novelty.known_algorithms
        if not config.enabled:
            return ""

        # Check for dynamic definitions first (preferred)
        if config.definitions:
            algo_lines = []
            for defn in config.definitions:
                penalty_pct = int(defn.penalty * 100)
                algo_lines.append(f"  - {defn.name}: {defn.description} ({penalty_pct}% penalty)")
            algo_list = "\n".join(algo_lines)
        elif config.algorithms:
            # Legacy fallback
            algo_list = "\n".join(f"  - {algo}" for algo in config.algorithms)
        else:
            return ""

        return f"""
KNOWN ALGORITHM WARNING:
The following algorithms are KNOWN and will receive SEVERE SCORE PENALTIES:
{algo_list}

DO NOT implement these algorithms or close variations of them.
Think fundamentally differently. Start from first principles.
The goal is to discover NEW algorithms, not re-implement existing ones.

Your solution MUST be genuinely novel to score well.
"""

    def _format_interface(self) -> str:
        """Format solution interface if provided."""
        if not self.problem.solution_interface:
            return ""

        return f"""SOLUTION INTERFACE:
```python
{self.problem.solution_interface}
```
"""

    def build_iteration_prompt(
        self,
        operation: "OperationContext",
        archive: "SolutionArchive",
        iteration: int,
        last_evaluation: "EvaluationResult | None" = None,
    ) -> str:
        """
        Build prompt for a single iteration.

        Args:
            operation: The evolutionary operation to perform
            archive: Current solution archive
            iteration: Current iteration number
            last_evaluation: Result of last evaluation (if any)

        Returns:
            Complete prompt for Claude
        """
        sections = []

        # 1. Archive summary
        sections.append(self._format_archive_summary(archive))

        # 2. Top solutions for reference
        sections.append(self._format_top_solutions(archive, operation))

        # 3. Operation instruction
        sections.append(self._format_operation(operation))

        # 4. Last evaluation feedback
        if last_evaluation:
            sections.append(self._format_evaluation(last_evaluation))

        # 5. Iteration info
        sections.append(f"ITERATION: {iteration} / {self.problem.loop.max_iterations}")

        # 6. Action instruction
        sections.append(self._format_action_instruction(operation))

        return "\n\n".join(sections)

    def _format_archive_summary(self, archive: "SolutionArchive") -> str:
        """Format archive statistics."""
        stats = archive.get_stats()

        if stats["total_solutions"] == 0:
            return """ARCHIVE STATUS:
No solutions discovered yet. You are starting fresh.
"""

        return f"""ARCHIVE STATUS:
- Total solutions: {stats['total_solutions']}
- Niches explored: {stats['total_niches']}
- Best score: {stats['best_score']:.4f}
- Average score: {stats['avg_score']:.4f}
- Archive coverage: {stats.get('coverage', 0):.1%}
"""

    def _format_top_solutions(
        self,
        archive: "SolutionArchive",
        operation: "OperationContext",
    ) -> str:
        """Format top solutions for reference."""
        # For operations with parent solutions, show those
        if operation.parent_solutions:
            return self._format_parent_solutions(operation)

        # Otherwise show top solutions from archive
        top_solutions = archive.get_top_k(3)

        if not top_solutions:
            return "TOP SOLUTIONS:\nNone yet."

        sections = ["TOP SOLUTIONS:"]

        for i, sol in enumerate(top_solutions, 1):
            niche_str = ", ".join(f"{k}={v}" for k, v in sol.niche_values.items())
            sections.append(f"""
--- Solution {i} (score: {sol.score:.4f}, niche: {niche_str}) ---
```python
{self._truncate_code(sol.code)}
```
""")

        return "\n".join(sections)

    def _format_parent_solutions(self, operation: "OperationContext") -> str:
        """Format parent solutions for mutation/crossover."""
        from obsidian.research.evolution import OperationType

        sections = []

        if operation.operation_type == OperationType.MUTATE:
            parent = operation.parent_solutions[0]
            niche_str = ", ".join(f"{k}={v}" for k, v in parent.niche_values.items())
            sections.append(f"""PARENT SOLUTION (score: {parent.score:.4f}, niche: {niche_str}):
```python
{parent.code}
```
""")

        elif operation.operation_type == OperationType.CROSSOVER:
            num_parents = len(operation.parent_solutions)
            if num_parents >= 3:
                # Multi-parent crossover with role descriptions
                sections.append("PARENT SOLUTIONS FOR MULTI-PARENT CROSSOVER:")
                role_hints = [
                    "Core algorithm provider",
                    "Optimization source",
                    "Edge-case/validation source",
                ]
                for i, parent in enumerate(operation.parent_solutions):
                    niche_str = ", ".join(f"{k}={v}" for k, v in parent.niche_values.items())
                    role = role_hints[i] if i < len(role_hints) else f"Parent {i + 1}"
                    label = chr(ord('A') + i)  # A, B, C, ...
                    sections.append(f"""
--- Solution {label}: {role} (score: {parent.score:.4f}, niche: {niche_str}) ---
```python
{parent.code}
```
""")
            else:
                # Standard 2-parent crossover
                sections.append("PARENT SOLUTIONS FOR CROSSOVER:")
                for i, parent in enumerate(operation.parent_solutions, 1):
                    niche_str = ", ".join(f"{k}={v}" for k, v in parent.niche_values.items())
                    sections.append(f"""
--- Parent {i} (score: {parent.score:.4f}, niche: {niche_str}) ---
```python
{parent.code}
```
""")

        elif operation.operation_type == OperationType.EXPLOIT:
            best = operation.parent_solutions[0]
            niche_str = ", ".join(f"{k}={v}" for k, v in best.niche_values.items())
            sections.append(f"""BEST SOLUTION TO OPTIMIZE (score: {best.score:.4f}, niche: {niche_str}):
```python
{best.code}
```
""")

        elif operation.operation_type == OperationType.EXPLORE:
            if operation.parent_solutions:
                sections.append("EXISTING SOLUTIONS (for reference - try something DIFFERENT):")
                for i, sol in enumerate(operation.parent_solutions[:3], 1):
                    sections.append(f"""
--- Existing {i} (approach: {sol.niche_values.get('approach', 'unknown')}) ---
{self._summarize_solution(sol)}
""")

        return "\n".join(sections)

    def _format_operation(self, operation: "OperationContext") -> str:
        """Format operation instruction."""
        from obsidian.research.evolution import OperationType

        op_type = operation.operation_type

        if op_type == OperationType.MUTATE:
            return f"""OPERATION: MUTATION
{operation.mutation_instructions}

Modify the parent solution while preserving its core approach.
Make targeted improvements without complete rewrites.
"""

        elif op_type == OperationType.CROSSOVER:
            num_parents = len(operation.parent_solutions) if operation.parent_solutions else 2
            if num_parents >= 3:
                return f"""OPERATION: MULTI-PARENT CROSSOVER
{operation.crossover_instructions}

You have {num_parents} parent solutions:
- Solution A: Use as the foundation / core algorithm
- Solution B: Extract optimizations and performance improvements
- Solution C: Borrow edge-case handling and validation logic

Create a hybrid that synthesizes the best ideas from all parents.
"""
            return f"""OPERATION: CROSSOVER
{operation.crossover_instructions}

Combine the best aspects of both parent solutions.
Create a hybrid that leverages the strengths of each.
"""

        elif op_type == OperationType.EXPLORE:
            target_info = ""
            if operation.target_niche:
                niche_str = ", ".join(f"{k}={v}" for k, v in operation.target_niche.items())
                target_info = f"\nTarget niche: {niche_str}"

            return f"""OPERATION: EXPLORATION
{operation.exploration_instructions}{target_info}

Try a fundamentally different approach.
Don't just modify existing solutions - think differently.
"""

        elif op_type == OperationType.EXPLOIT:
            return f"""OPERATION: EXPLOITATION
{operation.exploitation_instructions}

This is our best solution. Make it even better.
Focus on optimization without changing the core algorithm.
"""

        return "OPERATION: Generate a new solution."

    def _format_evaluation(self, evaluation: "EvaluationResult") -> str:
        """Format last evaluation result."""
        if not evaluation.passed:
            error_msg = ""
            if evaluation.correctness and evaluation.correctness.error:
                error_msg = f"\nError: {evaluation.correctness.error[:500]}"
            return f"""LAST EVALUATION: FAILED (correctness){error_msg}

The solution did not pass correctness tests. Fix the issues.
"""

        benchmark_info = ""
        if evaluation.benchmark:
            benchmark_info = f"""
Benchmark:
- Raw score: {evaluation.benchmark.raw_score}
- Normalized: {evaluation.benchmark.normalized_score:.4f}
- Direction: {evaluation.benchmark.direction}
"""

        novelty_info = ""
        if evaluation.novelty:
            novelty_info = f"\nNovelty score: {evaluation.novelty.score:.4f}"

        known_algo_info = ""
        if evaluation.known_algorithm and evaluation.known_algorithm.is_known:
            known_algo_info = f"""

KNOWN ALGORITHM DETECTED: {evaluation.known_algorithm.algorithm_name}
Confidence: {evaluation.known_algorithm.confidence:.0%}
Penalty Applied: {evaluation.known_algorithm.penalty_applied:.0%}
Your score was SEVERELY reduced. Try a COMPLETELY different approach."""

        return f"""LAST EVALUATION: PASSED
- Composite score: {evaluation.score:.4f}
- Correctness: {evaluation.correctness.score:.4f}{benchmark_info}{novelty_info}{known_algo_info}
"""

    def _format_action_instruction(self, operation: "OperationContext") -> str:
        """Format final action instruction."""
        return f"""ACTION REQUIRED:
Write a complete solution to {self.problem.solution_file}

Do not explain your approach. Just write the code.
The solution will be automatically evaluated.
"""

    def _truncate_code(self, code: str, max_lines: int = 50) -> str:
        """Truncate long code for display."""
        lines = code.split("\n")
        if len(lines) <= max_lines:
            return code

        half = max_lines // 2
        return "\n".join(lines[:half] + ["... (truncated) ..."] + lines[-half:])

    def _summarize_solution(self, solution: "Solution") -> str:
        """Create brief summary of a solution."""
        lines = solution.code.split("\n")

        # Get first docstring or comment
        summary_lines = []
        for line in lines[:10]:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("#"):
                summary_lines.append(stripped)
            elif stripped.startswith("class ") or stripped.startswith("def "):
                summary_lines.append(stripped)
                break

        if summary_lines:
            return "\n".join(summary_lines)

        return f"({len(lines)} lines of code)"

    def build_feedback_prompt(
        self,
        evaluation: "EvaluationResult",
        archive: "SolutionArchive",
    ) -> str:
        """
        Build feedback prompt after evaluation.

        Used in the stop hook to provide feedback to Claude.
        """
        stats = archive.get_stats()

        if not evaluation.passed:
            return f"""EVALUATION RESULT: FAILED

Your solution did not pass correctness tests.

{self._format_correctness_error(evaluation)}

Please fix the issues and try again.
"""

        # Check for known algorithm detection
        known_algo_warning = ""
        if evaluation.known_algorithm and evaluation.known_algorithm.is_known:
            known_algo_warning = f"""
KNOWN ALGORITHM DETECTED: {evaluation.known_algorithm.algorithm_name}
Confidence: {evaluation.known_algorithm.confidence:.0%}
Penalty Applied: {evaluation.known_algorithm.penalty_applied:.0%}

Your solution implements a KNOWN algorithm. This received a SEVERE score penalty.
You MUST try a fundamentally different approach. Do not just rename variables or
restructure the same algorithm. Think from first principles.
"""

        # Determine if this was a good solution
        is_best = evaluation.score >= stats.get("best_score", 0)
        is_good = evaluation.score >= stats.get("avg_score", 0)

        status = "NEW BEST" if is_best else ("GOOD" if is_good else "BELOW AVERAGE")

        # Override status if known algorithm was detected
        if evaluation.known_algorithm and evaluation.known_algorithm.is_known:
            status = "PENALIZED - KNOWN ALGORITHM"

        return f"""EVALUATION RESULT: {status}

Score: {evaluation.score:.4f}
- Correctness: {evaluation.correctness.score:.4f}
- Benchmark: {evaluation.benchmark.normalized_score:.4f} (raw: {evaluation.benchmark.raw_score})
- Novelty: {evaluation.novelty.score:.4f}
{known_algo_warning}
Archive Status:
- Best score: {stats['best_score']:.4f}
- Average: {stats['avg_score']:.4f}
- Solutions: {stats['total_solutions']}

{self._format_improvement_guidance(evaluation, is_best, is_good)}
"""

    def _format_correctness_error(self, evaluation: "EvaluationResult") -> str:
        """Format correctness error details."""
        if not evaluation.correctness:
            return "Unknown error."

        sections = []

        if evaluation.correctness.error:
            sections.append(f"Error:\n{evaluation.correctness.error[:1000]}")

        if evaluation.correctness.output:
            sections.append(f"Output:\n{evaluation.correctness.output[:1000]}")

        return "\n\n".join(sections) if sections else "No details available."

    def _format_improvement_guidance(
        self,
        evaluation: "EvaluationResult",
        is_best: bool,
        is_good: bool,
    ) -> str:
        """Format guidance for next iteration."""
        if is_best:
            return """This is now our best solution.
Consider: Can you push it even further? Or try a different approach to find something even better?
"""

        if is_good:
            return """Good progress. The solution is above average.
Consider: What made this work? Can you combine this with other good ideas?
"""

        return """This solution underperformed.
Consider: What went wrong? Try a different approach or fix the bottlenecks.
"""
