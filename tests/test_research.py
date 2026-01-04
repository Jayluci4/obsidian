"""Tests for Obsidian Research Mode."""

import json
import tempfile
from pathlib import Path

import pytest

from obsidian.research.archive import Niche, Solution, SolutionArchive
from obsidian.research.evolution import (
    CrossoverOperation,
    EvolutionController,
    ExploreOperation,
    ExploitOperation,
    MutateOperation,
    OperationType,
)
from obsidian.research.problem import (
    ArchiveConfig,
    BenchmarkConfig,
    CorrectnessConfig,
    EvolutionConfig,
    EvaluatorWeights,
    LoopConfig,
    NicheDefinition,
    NoveltyConfig,
    ProblemSpec,
    load_problem,
    validate_problem,
)
from obsidian.research.prompt_builder import ResearchPromptBuilder
from obsidian.research.universal_evaluator import (
    BenchmarkResult,
    CorrectnessResult,
    EvaluationResult,
    NoveltyResult,
    UniversalEvaluator,
)


class TestProblemSpec:
    """Tests for problem specification."""

    def test_default_problem_spec(self):
        """Test default problem specification."""
        spec = ProblemSpec(name="Test", description="A test problem")
        assert spec.name == "Test"
        assert spec.description == "A test problem"
        assert spec.solution_file == "solution.py"

    def test_weights_normalization(self):
        """Test that weights are normalized."""
        weights = EvaluatorWeights(correctness=1.0, benchmark=1.0, novelty=1.0)
        total = weights.correctness + weights.benchmark + weights.novelty
        assert abs(total - 1.0) < 0.01

    def test_load_problem_from_yaml(self):
        """Test loading problem from YAML file."""
        yaml_content = """
problem:
  name: "Test Problem"
  description: "A test problem for unit tests"
  solution_file: "test_solution.py"

evaluator:
  correctness:
    type: "pytest"
    command: "pytest tests/ -x"
    timeout: 60

  benchmark:
    command: "python benchmark.py {solution}"
    direction: "maximize"

  weights:
    correctness: 0.3
    benchmark: 0.5
    novelty: 0.2

archive:
  type: "map_elites"
  niches:
    - name: "approach"
      type: "categorical"
      values: ["a", "b", "c"]

loop:
  max_iterations: 100
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            spec = load_problem(f.name)

            assert spec.name == "Test Problem"
            assert spec.solution_file == "test_solution.py"
            assert spec.correctness.type == "pytest"
            assert spec.benchmark.direction == "maximize"
            assert len(spec.archive.niches) == 1
            assert spec.loop.max_iterations == 100

    def test_validate_problem(self):
        """Test problem validation."""
        # Valid problem
        spec = ProblemSpec(name="Test", description="Test desc")
        errors = validate_problem(spec)
        assert len(errors) == 0

        # Invalid: no name
        spec_no_name = ProblemSpec(name="", description="Test")
        errors = validate_problem(spec_no_name)
        assert any("name" in e.lower() for e in errors)


class TestSolution:
    """Tests for Solution dataclass."""

    def test_solution_to_dict(self):
        """Test solution serialization."""
        sol = Solution(
            id="sol_1",
            code="print('hello')",
            score=0.85,
            niche_key="approach:a",
            niche_values={"approach": "a"},
            iteration=5,
            timestamp=1234567890.0,
        )

        data = sol.to_dict()
        assert data["id"] == "sol_1"
        assert data["score"] == 0.85
        assert data["niche_key"] == "approach:a"

    def test_solution_from_dict(self):
        """Test solution deserialization."""
        data = {
            "id": "sol_2",
            "code": "def foo(): pass",
            "score": 0.72,
            "niche_key": "approach:b",
            "niche_values": {"approach": "b"},
            "iteration": 10,
            "timestamp": 1234567890.0,
        }

        sol = Solution.from_dict(data)
        assert sol.id == "sol_2"
        assert sol.score == 0.72


class TestNiche:
    """Tests for Niche."""

    def test_add_solution_to_niche(self):
        """Test adding solutions to a niche."""
        niche = Niche(key="test", values={"a": "1"})

        sol1 = Solution(
            id="s1", code="", score=0.5, niche_key="test",
            niche_values={}, iteration=1, timestamp=0.0
        )
        sol2 = Solution(
            id="s2", code="", score=0.8, niche_key="test",
            niche_values={}, iteration=2, timestamp=0.0
        )

        niche.add_solution(sol1, max_per_niche=5)
        niche.add_solution(sol2, max_per_niche=5)

        assert len(niche.solutions) == 2
        assert niche.best_score == 0.8
        assert niche.best_solution_id == "s2"

    def test_niche_pruning(self):
        """Test that niche prunes when over capacity."""
        niche = Niche(key="test", values={})

        for i in range(10):
            sol = Solution(
                id=f"s{i}", code="", score=i * 0.1, niche_key="test",
                niche_values={}, iteration=i, timestamp=0.0
            )
            niche.add_solution(sol, max_per_niche=3)

        # Should keep only top 3
        assert len(niche.solutions) == 3
        scores = [s.score for s in niche.solutions]
        assert min(scores) >= 0.7  # Only top solutions kept


class TestSolutionArchive:
    """Tests for SolutionArchive."""

    def test_empty_archive(self):
        """Test empty archive."""
        config = ArchiveConfig()
        archive = SolutionArchive(config)

        assert len(archive) == 0
        assert archive.get_stats()["total_solutions"] == 0

    def test_add_solution_to_archive(self):
        """Test adding solution to archive."""
        config = ArchiveConfig(
            niches=[
                NicheDefinition(name="type", type="categorical", values=["a", "b"])
            ]
        )
        archive = SolutionArchive(config)

        sol = archive.add(
            code="def foo(): pass",
            score=0.75,
            niche_values={"type": "a"},
            iteration=1,
        )

        assert sol is not None
        assert len(archive) == 1
        assert archive.get_stats()["best_score"] == 0.75

    def test_get_top_k(self):
        """Test getting top K solutions."""
        config = ArchiveConfig()
        archive = SolutionArchive(config)

        for i in range(10):
            archive.add(
                code=f"solution_{i}",
                score=i * 0.1,
                niche_values={"n": str(i)},
                iteration=i,
            )

        top3 = archive.get_top_k(3)
        assert len(top3) == 3
        assert abs(top3[0].score - 0.9) < 0.01
        assert abs(top3[1].score - 0.8) < 0.01
        assert abs(top3[2].score - 0.7) < 0.01

    def test_archive_with_database(self):
        """Test archive with SQLite persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "archive.db"
            config = ArchiveConfig()

            # Create and populate archive
            archive1 = SolutionArchive(config, db_path=db_path)
            archive1.add(
                code="solution_1",
                score=0.8,
                niche_values={"test": "1"},
                iteration=1,
            )

            # Create new archive from same database
            archive2 = SolutionArchive(config, db_path=db_path)
            assert len(archive2) == 1
            assert archive2.get_stats()["best_score"] == 0.8


class TestEvaluationResults:
    """Tests for evaluation result types."""

    def test_correctness_result(self):
        """Test CorrectnessResult."""
        result = CorrectnessResult(
            passed=True,
            score=1.0,
            output="All tests passed",
            duration_ms=100,
        )
        assert result.passed
        assert result.score == 1.0

    def test_benchmark_result(self):
        """Test BenchmarkResult."""
        result = BenchmarkResult(
            raw_score=0.85,
            normalized_score=0.9,
            direction="maximize",
            duration_ms=500,
        )
        assert result.raw_score == 0.85
        assert result.normalized_score == 0.9

    def test_evaluation_result_to_dict(self):
        """Test EvaluationResult serialization."""
        result = EvaluationResult(
            score=0.75,
            passed=True,
            correctness=CorrectnessResult(passed=True, score=1.0),
            benchmark=BenchmarkResult(raw_score=0.7, normalized_score=0.7),
            novelty=NoveltyResult(score=0.8),
            solution_hash="abc123",
            iteration=5,
        )

        data = result.to_dict()
        assert data["score"] == 0.75
        assert data["passed"]
        assert data["iteration"] == 5


class TestEvolutionaryOperations:
    """Tests for evolutionary operations."""

    def create_test_archive(self):
        """Create a test archive with solutions."""
        config = ArchiveConfig(
            niches=[
                NicheDefinition(name="approach", type="categorical", values=["a", "b"])
            ]
        )
        archive = SolutionArchive(config)

        archive.add("solution_a", 0.8, {"approach": "a"}, 1)
        archive.add("solution_b", 0.6, {"approach": "b"}, 2)
        archive.add("solution_c", 0.7, {"approach": "a"}, 3)

        return archive

    def create_test_problem(self):
        """Create a test problem spec."""
        return ProblemSpec(
            name="Test",
            description="Test problem",
            archive=ArchiveConfig(
                niches=[
                    NicheDefinition(name="approach", type="categorical", values=["a", "b"])
                ]
            ),
        )

    def test_mutate_operation(self):
        """Test mutation operation."""
        archive = self.create_test_archive()
        problem = self.create_test_problem()

        op = MutateOperation(strength="medium")
        context = op.get_context(archive, problem)

        assert context.operation_type == OperationType.MUTATE
        assert len(context.parent_solutions) == 1
        assert context.mutation_instructions != ""

    def test_crossover_operation(self):
        """Test crossover operation."""
        archive = self.create_test_archive()
        problem = self.create_test_problem()

        op = CrossoverOperation()
        context = op.get_context(archive, problem)

        assert context.operation_type == OperationType.CROSSOVER
        assert len(context.parent_solutions) == 2
        assert context.crossover_instructions != ""

    def test_explore_operation(self):
        """Test exploration operation."""
        archive = self.create_test_archive()
        problem = self.create_test_problem()

        op = ExploreOperation()
        context = op.get_context(archive, problem)

        assert context.operation_type == OperationType.EXPLORE
        assert context.exploration_instructions != ""

    def test_exploit_operation(self):
        """Test exploitation operation."""
        archive = self.create_test_archive()
        problem = self.create_test_problem()

        op = ExploitOperation()
        context = op.get_context(archive, problem)

        assert context.operation_type == OperationType.EXPLOIT
        assert len(context.parent_solutions) == 1
        # Best solution should be selected
        assert context.parent_solutions[0].score == 0.8

    def test_evolution_controller(self):
        """Test evolution controller selects operations."""
        config = EvolutionConfig(
            mutate_prob=0.25,
            crossover_prob=0.25,
            explore_prob=0.25,
            exploit_prob=0.25,
        )
        controller = EvolutionController(config)

        archive = self.create_test_archive()
        problem = self.create_test_problem()

        # Run multiple times to test randomness
        operations = set()
        for i in range(100):
            context = controller.select_operation(archive, problem, i + 10)
            operations.add(context.operation_type)

        # Should see variety of operations
        assert len(operations) >= 2


class TestPromptBuilder:
    """Tests for prompt building."""

    def test_system_prompt(self):
        """Test system prompt generation."""
        problem = ProblemSpec(
            name="Test Problem",
            description="Solve the test problem",
            solution_file="solution.py",
        )

        builder = ResearchPromptBuilder(problem)
        prompt = builder.build_system_prompt()

        assert "Test Problem" in prompt
        assert "Solve the test problem" in prompt
        assert "solution.py" in prompt

    def test_iteration_prompt(self):
        """Test iteration prompt generation."""
        problem = ProblemSpec(
            name="Test",
            description="Test desc",
            loop=LoopConfig(max_iterations=100),
        )
        builder = ResearchPromptBuilder(problem)

        archive = SolutionArchive(ArchiveConfig())
        archive.add("code", 0.5, {"n": "1"}, 1)

        from obsidian.research.evolution import ExploreOperation
        op = ExploreOperation()
        context = op.get_context(archive, problem)

        prompt = builder.build_iteration_prompt(
            operation=context,
            archive=archive,
            iteration=5,
        )

        assert "ITERATION: 5" in prompt
        assert "EXPLORATION" in prompt or "EXPLORE" in prompt

    def test_feedback_prompt_passed(self):
        """Test feedback prompt for passed evaluation."""
        problem = ProblemSpec(name="Test", description="Test")
        builder = ResearchPromptBuilder(problem)

        archive = SolutionArchive(ArchiveConfig())
        archive.add("code", 0.8, {"n": "1"}, 1)

        evaluation = EvaluationResult(
            score=0.85,
            passed=True,
            correctness=CorrectnessResult(passed=True, score=1.0),
            benchmark=BenchmarkResult(raw_score=0.8, normalized_score=0.8),
            novelty=NoveltyResult(score=0.9),
        )

        prompt = builder.build_feedback_prompt(evaluation, archive)

        assert "0.85" in prompt or "85" in prompt
        assert "NEW BEST" in prompt  # 0.85 > 0.8

    def test_feedback_prompt_failed(self):
        """Test feedback prompt for failed evaluation."""
        problem = ProblemSpec(name="Test", description="Test")
        builder = ResearchPromptBuilder(problem)

        archive = SolutionArchive(ArchiveConfig())

        evaluation = EvaluationResult(
            score=0.0,
            passed=False,
            correctness=CorrectnessResult(passed=False, score=0.0, error="Test failed"),
        )

        prompt = builder.build_feedback_prompt(evaluation, archive)

        assert "FAILED" in prompt
        assert "correctness" in prompt.lower()


class TestUniversalEvaluator:
    """Tests for universal evaluator."""

    def test_normalized_edit_distance(self):
        """Test edit distance computation."""
        problem = ProblemSpec(name="Test", description="Test")
        evaluator = UniversalEvaluator(problem)

        # Same code should have 0 distance
        dist = evaluator._normalized_edit_distance("a = 1", "a = 1")
        assert dist == 0.0

        # Different code should have positive distance
        dist = evaluator._normalized_edit_distance("a = 1", "b = 2")
        assert dist > 0

    def test_compute_hash(self):
        """Test solution hash computation."""
        problem = ProblemSpec(name="Test", description="Test")
        evaluator = UniversalEvaluator(problem)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('hello')")
            f.flush()

            hash1 = evaluator._compute_hash(Path(f.name))
            hash2 = evaluator._compute_hash(Path(f.name))

            assert hash1 == hash2
            assert len(hash1) == 16

    def test_normalize_score_maximize(self):
        """Test score normalization for maximize direction."""
        problem = ProblemSpec(name="Test", description="Test")
        evaluator = UniversalEvaluator(problem)

        evaluator._min_benchmark = 0.0
        evaluator._max_benchmark = 100.0

        # Middle value should be 0.5
        norm = evaluator._normalize_score(50.0, "maximize")
        assert norm == 0.5

        # Max value should be 1.0
        norm = evaluator._normalize_score(100.0, "maximize")
        assert norm == 1.0

    def test_normalize_score_minimize(self):
        """Test score normalization for minimize direction."""
        problem = ProblemSpec(name="Test", description="Test")
        evaluator = UniversalEvaluator(problem)

        evaluator._min_benchmark = 0.0
        evaluator._max_benchmark = 100.0

        # For minimize, lower is better, so 0 should normalize to 1.0
        norm = evaluator._normalize_score(0.0, "minimize")
        assert norm == 1.0

        # Max value should be 0.0 when minimizing
        norm = evaluator._normalize_score(100.0, "minimize")
        assert norm == 0.0


class TestKnownAlgorithmDetection:
    """Tests for known algorithm detection."""

    def test_signature_matcher_basic(self):
        """Test basic signature matching."""
        from obsidian.research.known_algorithms import SignatureMatcher

        matcher = SignatureMatcher(
            patterns=[r"pivot", r"partition", r"quicksort"],
            threshold=0.3,
        )

        # Code with matching patterns
        code = """
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + [pivot] + quicksort(right)
"""
        score = matcher.match(code)
        assert score > 0.5  # Should match at least 2/3 patterns

        # Code without matching patterns
        code_other = "def add(a, b): return a + b"
        score_other = matcher.match(code_other)
        assert score_other == 0.0

    def test_keyword_matcher(self):
        """Test keyword matching."""
        from obsidian.research.known_algorithms import KeywordMatcher

        matcher = KeywordMatcher(
            keywords=["strassen", "m1", "m2", "m3"],
            threshold=0.25,
        )

        code = """
def strassen_multiply(a, b):
    m1 = (a[0][0] + a[1][1]) * (b[0][0] + b[1][1])
    m2 = (a[1][0] + a[1][1]) * b[0][0]
"""
        score = matcher.match(code)
        assert score > 0  # Should match strassen, m1, m2

    def test_behavioral_matcher(self):
        """Test behavioral matching."""
        from obsidian.research.known_algorithms import BehavioralMatcher

        matcher = BehavioralMatcher(
            expected_behavior={
                "metrics.multiplications.count": 7,
            },
            tolerance=0,
        )

        # Matching behavior (Strassen uses 7 multiplications)
        behavioral_data = {"metrics": {"multiplications": {"count": 7}}}
        score = matcher.match("", behavioral_data)
        assert score == 1.0

        # Non-matching behavior (naive uses 8)
        behavioral_data_naive = {"metrics": {"multiplications": {"count": 8}}}
        score_naive = matcher.match("", behavioral_data_naive)
        assert score_naive == 0.0

    def test_known_algorithm_detector(self):
        """Test full algorithm detection."""
        from obsidian.research.known_algorithms import (
            KnownAlgorithm,
            KnownAlgorithmDetector,
            SignatureMatcher,
            KeywordMatcher,
        )

        strassen = KnownAlgorithm(
            name="strassen",
            description="Strassen's matrix multiplication",
            patterns=[
                SignatureMatcher(
                    patterns=[r"m1\s*=", r"m2\s*=", r"m3\s*="],
                    threshold=0.4,
                ),
                KeywordMatcher(
                    keywords=["strassen", "m1", "m2", "m3", "m4", "m5", "m6", "m7"],
                    threshold=0.3,
                ),
            ],
            penalty=0.9,
        )

        detector = KnownAlgorithmDetector([strassen])

        # Strassen-like code
        strassen_code = """
def strassen(a, b):
    m1 = (a[0][0] + a[1][1]) * (b[0][0] + b[1][1])
    m2 = (a[1][0] + a[1][1]) * b[0][0]
    m3 = a[0][0] * (b[0][1] - b[1][1])
    m4 = a[1][1] * (b[1][0] - b[0][0])
    m5 = (a[0][0] + a[0][1]) * b[1][1]
    m6 = (a[1][0] - a[0][0]) * (b[0][0] + b[0][1])
    m7 = (a[0][1] - a[1][1]) * (b[1][0] + b[1][1])
"""
        result = detector.detect(strassen_code, confidence_threshold=0.3)
        assert result.is_known
        assert result.algorithm_name == "strassen"
        assert result.penalty > 0

    def test_penalty_computation(self):
        """Test score penalty computation."""
        from obsidian.research.known_algorithms import (
            KnownAlgorithmDetector,
            DetectionResult,
        )

        detector = KnownAlgorithmDetector()

        # Test multiplicative penalty
        detection = DetectionResult(
            is_known=True,
            algorithm_name="strassen",
            confidence=0.9,
            penalty=0.9,  # 90% penalty
        )

        base_score = 1.0
        penalized = detector.compute_penalized_score(
            base_score, detection, penalty_mode="multiplicative"
        )
        assert abs(penalized - 0.1) < 0.01  # 1.0 * (1 - 0.9) = 0.1

    def test_matmul_database(self):
        """Test matrix multiplication algorithm database."""
        from obsidian.research.known_algorithms_db import get_algorithm

        strassen = get_algorithm("strassen")
        assert strassen is not None
        assert strassen.name == "strassen"
        assert strassen.penalty > 0.8  # High penalty

        winograd = get_algorithm("winograd")
        assert winograd is not None

        naive = get_algorithm("naive")
        assert naive is not None

    def test_sorting_database(self):
        """Test sorting algorithm database."""
        from obsidian.research.known_algorithms_db import get_algorithm

        quicksort = get_algorithm("quicksort")
        assert quicksort is not None
        assert "pivot" in str(quicksort.patterns)

        mergesort = get_algorithm("mergesort")
        assert mergesort is not None

    def test_create_detector_from_config(self):
        """Test creating detector from config."""
        from obsidian.research.known_algorithms import create_detector_from_config

        detector = create_detector_from_config(["strassen", "winograd", "naive"])
        assert len(detector.algorithms) == 3

        algorithm_names = [a.name for a in detector.algorithms]
        assert "strassen" in algorithm_names
        assert "winograd" in algorithm_names
        assert "naive" in algorithm_names

    def test_no_false_positives(self):
        """Test that unrelated code doesn't trigger detection."""
        from obsidian.research.known_algorithms import create_detector_from_config

        detector = create_detector_from_config(["strassen", "quicksort"])

        # Generic code that shouldn't match
        generic_code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
"""
        result = detector.detect(generic_code, confidence_threshold=0.5)
        assert not result.is_known
        assert result.penalty == 0

    def test_dynamic_definitions(self):
        """Test creating detector from dynamic definitions (Claude-generated)."""
        from obsidian.research.known_algorithms import create_detector_from_definitions
        from obsidian.research.problem import AlgorithmDefinition

        # Simulate what Claude would generate during research-init
        definitions = [
            AlgorithmDefinition(
                name="dijkstra",
                description="Shortest path with priority queue",
                penalty=0.85,
                keywords=["dijkstra", "priority", "visited", "distance", "neighbors"],
                patterns=[r"heapq", r"priority.*queue", r"visited\s*=\s*set"],
            ),
            AlgorithmDefinition(
                name="bellman_ford",
                description="Shortest path with negative edges",
                penalty=0.8,
                keywords=["bellman", "ford", "relax", "edges"],
                patterns=[r"for.*range.*V.*-.*1", r"relax"],
            ),
        ]

        detector = create_detector_from_definitions(definitions)
        assert len(detector.algorithms) == 2

        # Test detection of Dijkstra-like code
        dijkstra_code = """
import heapq

def dijkstra(graph, start):
    visited = set()
    distance = {node: float('inf') for node in graph}
    distance[start] = 0
    priority_queue = [(0, start)]

    while priority_queue:
        dist, node = heapq.heappop(priority_queue)
        if node in visited:
            continue
        visited.add(node)
        for neighbor, weight in graph[node]:
            if distance[neighbor] > dist + weight:
                distance[neighbor] = dist + weight
                heapq.heappush(priority_queue, (distance[neighbor], neighbor))
"""
        result = detector.detect(dijkstra_code, confidence_threshold=0.3)
        assert result.is_known
        assert result.algorithm_name == "dijkstra"
        assert result.penalty > 0

    def test_yaml_definitions_parsing(self):
        """Test parsing algorithm definitions from YAML."""
        import tempfile
        from obsidian.research.problem import load_problem

        yaml_content = """
problem:
  name: "Graph Algorithm Discovery"
  description: "Find novel shortest path algorithm"

evaluator:
  novelty:
    known_algorithms:
      enabled: true
      confidence_threshold: 0.5
      definitions:
        - name: "dijkstra"
          description: "Priority queue based"
          penalty: 0.85
          keywords: ["dijkstra", "priority", "visited"]
          patterns: ["heapq", "priority.*queue"]
        - name: "astar"
          description: "Heuristic search"
          penalty: 0.8
          keywords: ["astar", "heuristic", "f_score"]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            spec = load_problem(f.name)

            assert spec.novelty.known_algorithms.enabled
            assert len(spec.novelty.known_algorithms.definitions) == 2

            dijkstra = spec.novelty.known_algorithms.definitions[0]
            assert dijkstra.name == "dijkstra"
            assert dijkstra.penalty == 0.85
            assert "priority" in dijkstra.keywords
