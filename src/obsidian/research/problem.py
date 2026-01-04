"""
Problem Specification System.

Defines the structure for research problems including:
- Problem description and constraints
- Solution interface/template
- Evaluation criteria (correctness, benchmark, novelty)
- Archive configuration (niches, quality-diversity)
- Evolution parameters
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CorrectnessConfig:
    """Configuration for correctness checking."""

    type: str = "pytest"  # pytest, reference, script, formal
    command: str = "pytest tests/ -x"
    timeout: int = 300
    pass_threshold: float = 1.0
    reference_impl: str | None = None  # For type="reference"


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark evaluation."""

    command: str = "python benchmark.py {solution}"
    output_parser: str = "json"  # json, grep, regex
    output_pattern: str | None = None  # For grep/regex parsers
    timeout: int = 3600
    direction: str = "maximize"  # maximize or minimize
    baseline_score: float | None = None  # For normalization
    target_score: float | None = None  # Success threshold


@dataclass
class NoveltyConfig:
    """Configuration for novelty computation."""

    type: str = "embedding"  # embedding, ast_diff, code_diff, behavioral
    k_nearest: int = 5  # Number of neighbors for novelty score
    weight: float = 0.2
    embedding_model: str = "code"  # For embedding type


@dataclass
class EvaluatorWeights:
    """Weights for composite score."""

    correctness: float = 0.2
    benchmark: float = 0.6
    novelty: float = 0.2

    def __post_init__(self):
        total = self.correctness + self.benchmark + self.novelty
        if abs(total - 1.0) > 0.01:
            # Normalize weights
            self.correctness /= total
            self.benchmark /= total
            self.novelty /= total


@dataclass
class NicheDefinition:
    """Definition of a niche dimension for MAP-Elites."""

    name: str
    type: str = "categorical"  # categorical, continuous
    values: list[str] | None = None  # For categorical
    bins: list[float] | None = None  # For continuous (bin edges)
    extractor: str | None = None  # Command or pattern to extract niche value


@dataclass
class ArchiveConfig:
    """Configuration for solution archive."""

    type: str = "map_elites"  # map_elites, pareto, simple
    niches: list[NicheDefinition] = field(default_factory=list)
    max_solutions_per_niche: int = 5
    max_total_solutions: int = 1000
    prune_strategy: str = "oldest"  # oldest, lowest_score, random


@dataclass
class EvolutionConfig:
    """Configuration for evolutionary operations."""

    # Operation probabilities (should sum to 1.0)
    mutate_prob: float = 0.4
    crossover_prob: float = 0.2
    explore_prob: float = 0.3
    exploit_prob: float = 0.1

    # Selection parameters
    parent_selection: str = "tournament"  # tournament, roulette, rank
    tournament_size: int = 3

    # Mutation parameters
    mutation_strength: str = "medium"  # light, medium, heavy


@dataclass
class LoopConfig:
    """Configuration for the research loop."""

    max_iterations: int = 10000
    checkpoint_every: int = 100
    log_every: int = 10

    # Early stopping
    early_stop_threshold: float | None = None
    early_stop_patience: int = 1000

    # Human-in-the-loop
    human_gate_enabled: bool = False
    human_gate_every: int = 500

    # Timeouts
    iteration_timeout: int = 7200  # 2 hours per iteration
    total_timeout: int | None = None  # No limit by default


@dataclass
class ProblemSpec:
    """Complete problem specification."""

    # Problem identity
    name: str
    description: str
    version: str = "1.0"

    # Solution specification
    solution_file: str = "solution.py"
    solution_template: str | None = None
    solution_interface: str | None = None

    # Evaluation
    correctness: CorrectnessConfig = field(default_factory=CorrectnessConfig)
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    novelty: NoveltyConfig = field(default_factory=NoveltyConfig)
    weights: EvaluatorWeights = field(default_factory=EvaluatorWeights)

    # Archive
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)

    # Evolution
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)

    # Loop
    loop: LoopConfig = field(default_factory=LoopConfig)

    # Metadata
    tags: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    @property
    def solution_path(self) -> Path:
        """Get solution file path."""
        return Path(self.solution_file)


def _parse_correctness(data: dict[str, Any]) -> CorrectnessConfig:
    """Parse correctness configuration."""
    if not data:
        return CorrectnessConfig()
    return CorrectnessConfig(
        type=data.get("type", "pytest"),
        command=data.get("command", "pytest tests/ -x"),
        timeout=data.get("timeout", 300),
        pass_threshold=data.get("pass_threshold", 1.0),
        reference_impl=data.get("reference_impl"),
    )


def _parse_benchmark(data: dict[str, Any]) -> BenchmarkConfig:
    """Parse benchmark configuration."""
    if not data:
        return BenchmarkConfig()
    return BenchmarkConfig(
        command=data.get("command", "python benchmark.py {solution}"),
        output_parser=data.get("output_parser", "json"),
        output_pattern=data.get("output_pattern"),
        timeout=data.get("timeout", 3600),
        direction=data.get("direction", "maximize"),
        baseline_score=data.get("baseline_score"),
        target_score=data.get("target_score"),
    )


def _parse_novelty(data: dict[str, Any]) -> NoveltyConfig:
    """Parse novelty configuration."""
    if not data:
        return NoveltyConfig()
    return NoveltyConfig(
        type=data.get("type", "embedding"),
        k_nearest=data.get("k_nearest", 5),
        weight=data.get("weight", 0.2),
        embedding_model=data.get("embedding_model", "code"),
    )


def _parse_weights(data: dict[str, Any]) -> EvaluatorWeights:
    """Parse evaluator weights."""
    if not data:
        return EvaluatorWeights()
    return EvaluatorWeights(
        correctness=data.get("correctness", 0.2),
        benchmark=data.get("benchmark", 0.6),
        novelty=data.get("novelty", 0.2),
    )


def _parse_niches(data: list[dict[str, Any]]) -> list[NicheDefinition]:
    """Parse niche definitions."""
    niches = []
    for niche_data in data:
        niches.append(
            NicheDefinition(
                name=niche_data["name"],
                type=niche_data.get("type", "categorical"),
                values=niche_data.get("values"),
                bins=niche_data.get("bins"),
                extractor=niche_data.get("extractor"),
            )
        )
    return niches


def _parse_archive(data: dict[str, Any]) -> ArchiveConfig:
    """Parse archive configuration."""
    if not data:
        return ArchiveConfig()
    return ArchiveConfig(
        type=data.get("type", "map_elites"),
        niches=_parse_niches(data.get("niches", [])),
        max_solutions_per_niche=data.get("max_solutions_per_niche", 5),
        max_total_solutions=data.get("max_total_solutions", 1000),
        prune_strategy=data.get("prune_strategy", "oldest"),
    )


def _parse_evolution(data: dict[str, Any]) -> EvolutionConfig:
    """Parse evolution configuration."""
    if not data:
        return EvolutionConfig()

    ops = data.get("operations", {})
    return EvolutionConfig(
        mutate_prob=ops.get("mutate", 0.4),
        crossover_prob=ops.get("crossover", 0.2),
        explore_prob=ops.get("explore", 0.3),
        exploit_prob=ops.get("exploit", 0.1),
        parent_selection=data.get("selection", {}).get("parent_selection", "tournament"),
        tournament_size=data.get("selection", {}).get("tournament_size", 3),
        mutation_strength=data.get("mutation_strength", "medium"),
    )


def _parse_loop(data: dict[str, Any]) -> LoopConfig:
    """Parse loop configuration."""
    if not data:
        return LoopConfig()

    early_stop = data.get("early_stop", {})
    human_gate = data.get("human_gate", {})

    return LoopConfig(
        max_iterations=data.get("max_iterations", 10000),
        checkpoint_every=data.get("checkpoint_every", 100),
        log_every=data.get("log_every", 10),
        early_stop_threshold=early_stop.get("threshold"),
        early_stop_patience=early_stop.get("patience", 1000),
        human_gate_enabled=human_gate.get("enabled", False),
        human_gate_every=human_gate.get("every", 500),
        iteration_timeout=data.get("iteration_timeout", 7200),
        total_timeout=data.get("total_timeout"),
    )


def load_problem(path: str | Path) -> ProblemSpec:
    """
    Load problem specification from YAML file.

    Args:
        path: Path to problem.yaml file

    Returns:
        Parsed ProblemSpec
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Problem file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    problem_data = data.get("problem", data)
    evaluator_data = data.get("evaluator", {})

    return ProblemSpec(
        # Problem identity
        name=problem_data.get("name", path.stem),
        description=problem_data.get("description", ""),
        version=problem_data.get("version", "1.0"),
        # Solution specification
        solution_file=problem_data.get("solution_file", "solution.py"),
        solution_template=problem_data.get("solution_template"),
        solution_interface=problem_data.get("solution_interface"),
        # Evaluation
        correctness=_parse_correctness(evaluator_data.get("correctness", {})),
        benchmark=_parse_benchmark(evaluator_data.get("benchmark", {})),
        novelty=_parse_novelty(evaluator_data.get("novelty", {})),
        weights=_parse_weights(evaluator_data.get("weights", {})),
        # Archive
        archive=_parse_archive(data.get("archive", {})),
        # Evolution
        evolution=_parse_evolution(data.get("evolution", {})),
        # Loop
        loop=_parse_loop(data.get("loop", {})),
        # Metadata
        tags=problem_data.get("tags", []),
        references=problem_data.get("references", []),
    )


def validate_problem(spec: ProblemSpec) -> list[str]:
    """
    Validate problem specification.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check required fields
    if not spec.name:
        errors.append("Problem name is required")

    if not spec.description:
        errors.append("Problem description is required")

    # Check weights sum to 1.0
    total_weight = spec.weights.correctness + spec.weights.benchmark + spec.weights.novelty
    if abs(total_weight - 1.0) > 0.01:
        errors.append(f"Weights must sum to 1.0, got {total_weight}")

    # Check evolution probabilities
    total_prob = (
        spec.evolution.mutate_prob
        + spec.evolution.crossover_prob
        + spec.evolution.explore_prob
        + spec.evolution.exploit_prob
    )
    if abs(total_prob - 1.0) > 0.01:
        errors.append(f"Evolution probabilities must sum to 1.0, got {total_prob}")

    # Check niche definitions
    for niche in spec.archive.niches:
        if niche.type == "categorical" and not niche.values:
            errors.append(f"Niche '{niche.name}' is categorical but has no values")
        if niche.type == "continuous" and not niche.bins:
            errors.append(f"Niche '{niche.name}' is continuous but has no bins")

    return errors
