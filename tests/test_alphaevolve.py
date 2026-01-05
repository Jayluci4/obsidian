"""Tests for AlphaEvolve-style extensions."""

import tempfile
from pathlib import Path

import pytest

from obsidian.research.archive import ArchiveConfig, Solution, SolutionArchive
from obsidian.research.bandit import (
    ArmStats,
    BanditAlgorithm,
    BanditConfig,
    ContextualBandit,
    MultiArmedBandit,
)
from obsidian.research.evolution import (
    AdaptiveEvolutionController,
    EvolutionController,
    MultiParentCrossoverOperation,
    OperationType,
    create_evolution_controller,
)
from obsidian.research.lineage import LineageTracker
from obsidian.research.novelty import (
    ASTNoveltyComputer,
    compute_ast_distance,
    compute_ast_histogram,
)
from obsidian.research.problem import (
    AdaptiveSelectionConfig,
    EvolutionConfig,
    ParentSelectionConfig,
    ProblemSpec,
)
from obsidian.research.prompt_sampler import PromptSampler, get_prompt_text


class TestMultiArmedBandit:
    """Tests for multi-armed bandit algorithms."""

    def test_ucb1_initial_exploration(self):
        """Test that UCB1 explores all arms initially."""
        arms = ["mutate", "crossover", "explore", "exploit"]
        bandit = MultiArmedBandit(arms)

        # Should try each arm at least once
        selected = set()
        for _ in range(10):
            arm = bandit.select()
            selected.add(arm)
            bandit.update(arm, reward=0.5)

        assert len(selected) == len(arms)

    def test_ucb1_exploits_best(self):
        """Test that UCB1 eventually exploits best arm."""
        arms = ["a", "b", "c"]
        bandit = MultiArmedBandit(arms)

        # Train: arm 'b' always gives high reward
        for _ in range(50):
            for arm in arms:
                reward = 1.0 if arm == "b" else 0.1
                bandit.update(arm, reward)

        # Should mostly select 'b' now
        selections = [bandit.select() for _ in range(20)]
        b_count = selections.count("b")

        assert b_count >= 15  # At least 75% should be 'b'

    def test_thompson_sampling(self):
        """Test Thompson sampling selection."""
        arms = ["a", "b"]
        config = BanditConfig(algorithm=BanditAlgorithm.THOMPSON)
        bandit = MultiArmedBandit(arms, config)

        # Both arms should be selected initially
        selections = set()
        for _ in range(20):
            arm = bandit.select()
            selections.add(arm)
            bandit.update(arm, reward=0.5, success=True)

        assert len(selections) == 2

    def test_epsilon_greedy(self):
        """Test epsilon-greedy selection."""
        arms = ["a", "b"]
        config = BanditConfig(algorithm=BanditAlgorithm.EPSILON_GREEDY, epsilon=0.1)
        bandit = MultiArmedBandit(arms, config)

        # Train arm 'a' to be clearly better
        for _ in range(50):
            bandit.update("a", reward=1.0)
            bandit.update("b", reward=0.0)

        # Should mostly select 'a' (90% exploit + 5% random)
        selections = [bandit.select() for _ in range(100)]
        a_count = selections.count("a")

        assert a_count >= 80  # Should be > 80%

    def test_persistence(self):
        """Test that bandit persists stats to database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "bandit.db"
            arms = ["a", "b"]

            # Create and train bandit
            bandit1 = MultiArmedBandit(arms, db_path=db_path)
            bandit1.update("a", reward=1.0)
            bandit1.update("a", reward=0.8)
            bandit1.update("b", reward=0.2)

            # Create new bandit from same db
            bandit2 = MultiArmedBandit(arms, db_path=db_path)
            stats = bandit2.get_stats()

            assert stats["a"]["trials"] == 2
            assert stats["b"]["trials"] == 1
            assert stats["a"]["avg_reward"] == 0.9

    def test_get_best_arm(self):
        """Test getting best arm."""
        arms = ["a", "b", "c"]
        bandit = MultiArmedBandit(arms)

        bandit.update("a", reward=0.5)
        bandit.update("b", reward=0.9)
        bandit.update("c", reward=0.3)

        assert bandit.get_best_arm() == "b"


class TestContextualBandit:
    """Tests for contextual bandit."""

    def test_context_discretization(self):
        """Test that similar contexts give same key."""
        arms = ["a", "b"]
        bandit = ContextualBandit(arms, context_bins=10)

        context1 = [0.15, 0.25]
        context2 = [0.18, 0.22]  # Similar

        key1 = bandit._discretize_context(context1)
        key2 = bandit._discretize_context(context2)

        assert key1 == key2

    def test_learns_context(self):
        """Test that bandit learns context-specific preferences."""
        arms = ["a", "b"]
        bandit = ContextualBandit(arms, epsilon=0.0)

        # Context [0.1, 0.1] -> arm 'a' is better
        for _ in range(20):
            bandit.update([0.1, 0.1], "a", reward=1.0)
            bandit.update([0.1, 0.1], "b", reward=0.1)

        # Context [0.9, 0.9] -> arm 'b' is better
        for _ in range(20):
            bandit.update([0.9, 0.9], "a", reward=0.1)
            bandit.update([0.9, 0.9], "b", reward=1.0)

        # Should select appropriate arm for each context
        assert bandit.select([0.1, 0.1]) == "a"
        assert bandit.select([0.9, 0.9]) == "b"


class TestAdaptiveEvolutionController:
    """Tests for adaptive evolution controller."""

    def create_archive(self, tmpdir, num_solutions=5):
        """Create archive with test solutions."""
        config = ArchiveConfig()
        archive = SolutionArchive(config)

        for i in range(num_solutions):
            archive.add(
                code=f"def solution_{i}(): pass",
                score=0.3 + i * 0.1,
                niche_values={"approach": f"approach_{i % 3}"},
                iteration=i,
            )

        return archive

    def test_adaptive_controller_creation(self):
        """Test creating adaptive controller."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                adaptive=AdaptiveSelectionConfig(enabled=True, algorithm="ucb1"),
            )

            controller = AdaptiveEvolutionController(config, Path(tmpdir))

            assert controller.operation_bandit is not None
            assert controller.multi_crossover_op is not None

    def test_factory_function(self):
        """Test factory creates correct controller type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Adaptive disabled -> regular controller
            config1 = EvolutionConfig()
            controller1 = create_evolution_controller(config1, Path(tmpdir))
            assert isinstance(controller1, EvolutionController)
            assert not isinstance(controller1, AdaptiveEvolutionController)

            # Adaptive enabled -> adaptive controller
            config2 = EvolutionConfig(
                adaptive=AdaptiveSelectionConfig(enabled=True),
            )
            controller2 = create_evolution_controller(config2, Path(tmpdir))
            assert isinstance(controller2, AdaptiveEvolutionController)

    def test_record_outcome(self):
        """Test recording outcomes updates bandit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvolutionConfig(
                adaptive=AdaptiveSelectionConfig(enabled=True),
            )
            controller = AdaptiveEvolutionController(config, Path(tmpdir))
            archive = self.create_archive(tmpdir, 5)
            problem = ProblemSpec(name="test", description="test")

            # Select operation
            controller.select_operation(archive, problem, iteration=15)

            # Record outcome
            controller.record_outcome(score_before=0.5, score_after=0.7)

            # Check stats updated
            stats = controller.get_operation_stats()
            assert sum(s["trials"] for s in stats.values()) > 0


class TestMultiParentCrossover:
    """Tests for multi-parent crossover."""

    def create_archive_with_solutions(self, n=5):
        """Create archive with n solutions in UNIQUE niches and iterations."""
        import time

        config = ArchiveConfig()
        archive = SolutionArchive(config)

        # Use unique niches AND unique iterations to avoid ID collisions
        for i in range(n):
            archive.add(
                code=f"def solution_{i}(): pass",
                score=0.5 + i * 0.05,
                niche_values={"approach": f"approach_{i}"},  # Unique niche per solution
                iteration=i,  # Unique iteration for unique ID
            )
            time.sleep(0.002)  # Ensure unique timestamp

        return archive

    def test_multi_parent_selection(self):
        """Test selecting 3 diverse parents."""
        # Need at least 3 unique niches for 3 parents
        archive = self.create_archive_with_solutions(5)
        problem = ProblemSpec(name="test", description="test")

        op = MultiParentCrossoverOperation()
        context = op.get_context(archive, problem)

        assert len(context.parent_solutions) == 3
        assert context.operation_type == OperationType.CROSSOVER

    def test_fallback_to_2_parent(self):
        """Test fallback when only 2 solutions available."""
        import time

        # Create exactly 2 solutions in unique niches with unique iterations
        config = ArchiveConfig()
        archive = SolutionArchive(config)
        archive.add(code="def a(): pass", score=0.5, niche_values={"approach": "a"}, iteration=0)
        time.sleep(0.002)
        archive.add(code="def b(): pass", score=0.6, niche_values={"approach": "b"}, iteration=1)

        problem = ProblemSpec(name="test", description="test")

        op = MultiParentCrossoverOperation()
        context = op.get_context(archive, problem)

        # Should fall back to 2-parent crossover
        assert len(context.parent_solutions) == 2
        assert context.operation_type == OperationType.CROSSOVER

    def test_fallback_to_explore(self):
        """Test fallback to explore when < 2 solutions."""
        archive = self.create_archive_with_solutions(1)
        problem = ProblemSpec(name="test", description="test")

        op = MultiParentCrossoverOperation()
        context = op.get_context(archive, problem)

        # Should fall back to explore
        assert context.operation_type == OperationType.EXPLORE


class TestFitnessDiversitySelection:
    """Tests for fitness-diversity parent selection."""

    def create_archive(self, solutions):
        """Create archive with given solutions using unique iterations."""
        import time

        config = ArchiveConfig()
        archive = SolutionArchive(config)

        for i, (code, score, niche) in enumerate(solutions):
            archive.add(code=code, score=score, niche_values={"approach": niche}, iteration=i)
            time.sleep(0.002)

        return archive

    def test_fitness_diversity_selection(self):
        """Test fitness-diversity selection."""
        solutions = [
            ("def a(): pass", 0.9, "approach_a"),
            ("def b(): pass", 0.5, "approach_b"),
            ("def c(): pass", 0.3, "approach_c"),
        ]
        archive = self.create_archive(solutions)

        # With high diversity weight, should sometimes select lower-fitness diverse solutions
        selections = [
            archive.get_parent_for_mutation_fitness_diversity(diversity_weight=0.5)
            for _ in range(100)
        ]

        # Should not always select the best
        scores = [s.score for s in selections]
        assert min(scores) < 0.9  # Sometimes selects non-best

    def test_multi_crossover_diversity(self):
        """Test that multi-crossover selects diverse parents."""
        # Use unique niches so all solutions remain in archive
        solutions = [
            ("def a(): pass", 0.9, "approach_a"),
            ("def b(): pass", 0.85, "approach_b"),
            ("def c(): pass", 0.8, "approach_c"),
            ("def d(): pass", 0.7, "approach_d"),
        ]
        archive = self.create_archive(solutions)

        parents = archive.get_parents_for_multi_crossover(n=3)

        # Should select 3 parents
        assert len(parents) == 3
        # Should select from different niches
        niches = [p.niche_values.get("approach") for p in parents]
        assert len(set(niches)) >= 2  # At least 2 different niches


class TestASTNovelty:
    """Tests for AST-based novelty computation."""

    def test_identical_code_distance_zero(self):
        """Test that identical code has distance 0."""
        code = """
def sort(arr):
    for i in range(len(arr)):
        for j in range(i+1, len(arr)):
            if arr[i] > arr[j]:
                arr[i], arr[j] = arr[j], arr[i]
    return arr
"""
        distance = compute_ast_distance(code, code)
        assert distance == 0.0

    def test_different_code_distance_positive(self):
        """Test that different code has positive distance."""
        code1 = """
def sort(arr):
    for i in range(len(arr)):
        pass
"""
        code2 = """
def find(arr, x):
    if x in arr:
        return arr.index(x)
    return -1
"""
        distance = compute_ast_distance(code1, code2)
        assert distance > 0.0
        assert distance <= 1.0

    def test_histogram_computation(self):
        """Test AST histogram computation."""
        code = """
def example():
    for i in range(10):
        if i > 5:
            print(i)
"""
        histogram = compute_ast_histogram(code)

        assert histogram is not None
        assert histogram.counts["FunctionDef"] == 1
        assert histogram.counts["For"] == 1
        assert histogram.counts["If"] == 1

    def test_weighted_histogram(self):
        """Test that important nodes are weighted higher."""
        code = """
def example():
    for i in range(10):
        x = i + 1
"""
        histogram = compute_ast_histogram(code)

        assert histogram is not None
        # FunctionDef (weight 3.0) should have higher weighted count
        assert histogram.weighted_counts["FunctionDef"] > histogram.counts["FunctionDef"]

    def test_novelty_computer(self):
        """Test ASTNoveltyComputer."""
        computer = ASTNoveltyComputer()

        archive_codes = [
            "def sort(arr): arr.sort()",
            "def sort(arr): return sorted(arr)",
        ]

        # Novel code
        novel_code = """
def sort(arr):
    # Completely different approach
    for i in range(len(arr)):
        for j in range(len(arr) - 1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr
"""

        novelty = computer.compute_novelty(novel_code, archive_codes)
        assert 0.0 <= novelty <= 1.0

    def test_first_solution_is_novel(self):
        """Test that first solution gets novelty 1.0."""
        computer = ASTNoveltyComputer()
        novelty = computer.compute_novelty("def x(): pass", [])
        assert novelty == 1.0

    def test_structural_summary(self):
        """Test getting structural summary."""
        computer = ASTNoveltyComputer()
        code = """
def example():
    for i in range(10):
        if i > 5:
            yield i * 2
"""
        summary = computer.get_structural_summary(code)

        assert "total_nodes" in summary
        assert summary["control_flow_count"] >= 2  # For and If
        assert summary["function_count"] >= 1


class TestLineageTracking:
    """Tests for lineage tracking."""

    def create_archive_with_lineage(self):
        """Create archive with lineage relationships using unique niches and iterations."""
        import time

        config = ArchiveConfig()
        archive = SolutionArchive(config)

        # Root solution (lineage 1)
        root = archive.add(
            code="def root(): pass",
            score=0.5,
            niche_values={"approach": "a1"},  # Unique niche
            iteration=0,
            parent_ids=[],
            operation="explore",
        )
        time.sleep(0.002)  # Ensure unique timestamp for ID

        # Child 1 (improves) - different niche to avoid overwriting
        child1 = archive.add(
            code="def child1(): pass",
            score=0.6,
            niche_values={"approach": "a2"},  # Unique niche
            iteration=1,
            parent_ids=[root.id],
            operation="mutate",
        )
        time.sleep(0.002)

        # Child 2 (improves more)
        child2 = archive.add(
            code="def child2(): pass",
            score=0.7,
            niche_values={"approach": "a3"},  # Unique niche
            iteration=2,
            parent_ids=[child1.id],
            operation="mutate",
        )
        time.sleep(0.002)

        # Another root (different lineage) - use different iteration to avoid ID collision
        root2 = archive.add(
            code="def root2(): pass",
            score=0.4,
            niche_values={"approach": "b1"},  # Unique niche
            iteration=10,  # Different iteration for unique ID
            parent_ids=[],
            operation="explore",
        )
        time.sleep(0.002)

        # Child of root2 (stagnant)
        archive.add(
            code="def child_stagnant(): pass",
            score=0.41,
            niche_values={"approach": "b2"},  # Unique niche
            iteration=11,  # Different iteration for unique ID
            parent_ids=[root2.id],
            operation="mutate",
        )

        return archive

    def test_lineage_tree_building(self):
        """Test building lineage tree."""
        archive = self.create_archive_with_lineage()
        tracker = LineageTracker(archive)

        # With unique niches, all 5 solutions should be present
        assert len(tracker._nodes) == 5
        # Two roots: first solution of lineage 1 and first solution of lineage 2
        assert len(tracker._roots) == 2

    def test_successful_lineage_detection(self):
        """Test finding successful lineages."""
        archive = self.create_archive_with_lineage()
        tracker = LineageTracker(archive)

        successful = tracker.get_successful_lineages(min_improvement=0.1)
        assert len(successful) >= 1

        # First lineage should have higher improvement
        best = successful[0]
        assert best.total_improvement > 0.1

    def test_stagnant_lineage_detection(self):
        """Test finding stagnant lineages."""
        archive = self.create_archive_with_lineage()
        tracker = LineageTracker(archive)

        # Lineage 2 has improvement of only 0.01 (0.41 - 0.4)
        stagnant = tracker.get_stagnant_lineages(max_improvement=0.02, min_descendants=1)
        # At least one stagnant lineage (lineage 2)
        assert len(stagnant) >= 1

    def test_lineage_stats(self):
        """Test getting lineage statistics."""
        archive = self.create_archive_with_lineage()
        tracker = LineageTracker(archive)

        root_id = tracker._roots[0]
        stats = tracker.get_lineage_stats(root_id)

        assert stats is not None
        assert stats.total_descendants >= 0
        assert stats.best_score >= stats.root_score

    def test_crossover_pair_suggestions(self):
        """Test suggesting crossover pairs."""
        archive = self.create_archive_with_lineage()
        tracker = LineageTracker(archive)

        pairs = tracker.suggest_crossover_pairs()
        # May or may not have suggestions depending on lineage quality
        assert isinstance(pairs, list)


class TestPromptSampler:
    """Tests for prompt sampler."""

    def create_archive(self, n=5):
        """Create test archive."""
        config = ArchiveConfig()
        archive = SolutionArchive(config)
        for i in range(n):
            archive.add(
                code=f"def s{i}(): pass",
                score=0.5 + i * 0.1,
                niche_values={"approach": f"a{i}"},
            )
        return archive

    def test_context_features(self):
        """Test extracting context features."""
        archive = self.create_archive(5)
        sampler = PromptSampler()

        features = sampler.get_context_features(archive)

        # Should have at least 4 base features
        assert len(features) >= 4
        # First 4 features should be normalized to [0, 1]
        # Note: archive size is normalized to min(1.0, size/100), others may vary
        assert features[0] >= 0.0  # Normalized archive size
        assert features[0] <= 1.0

    def test_prompt_selection(self):
        """Test selecting prompts."""
        archive = self.create_archive(5)
        sampler = PromptSampler(epsilon=1.0)  # Always explore

        prompt = sampler.select_prompt(
            OperationType.MUTATE,
            archive,
            mutation_strength="medium",
        )

        assert prompt is not None
        assert prompt.startswith("medium_")

    def test_outcome_recording(self):
        """Test recording outcomes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = self.create_archive(5)
            sampler = PromptSampler(db_path=Path(tmpdir) / "prompts.db")

            # Select and record
            sampler.select_prompt(OperationType.MUTATE, archive)
            sampler.record_outcome(reward=0.5)

            stats = sampler.get_stats()
            assert len(stats) > 0

    def test_get_prompt_text(self):
        """Test getting prompt text from ID."""
        text = get_prompt_text("medium_optimize_core")
        assert "Optimize" in text

        text2 = get_prompt_text("unknown_prompt_id")
        assert text2 == "unknown_prompt_id"


class TestConfigParsing:
    """Tests for new config dataclasses."""

    def test_adaptive_selection_config(self):
        """Test AdaptiveSelectionConfig defaults."""
        config = AdaptiveSelectionConfig()
        assert config.enabled is False
        assert config.algorithm == "ucb1"

    def test_parent_selection_config(self):
        """Test ParentSelectionConfig defaults."""
        config = ParentSelectionConfig()
        assert config.method == "tournament"
        assert config.diversity_weight == 0.3

    def test_evolution_config_with_new_fields(self):
        """Test EvolutionConfig with new fields."""
        config = EvolutionConfig(
            adaptive=AdaptiveSelectionConfig(enabled=True),
            parent_config=ParentSelectionConfig(method="fitness_diversity"),
            crossover_parents=3,
        )

        assert config.adaptive.enabled is True
        assert config.parent_config.method == "fitness_diversity"
        assert config.crossover_parents == 3
