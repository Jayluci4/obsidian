# AlphaEvolve-Style Extensions

Obsidian's research mode now includes AlphaEvolve-inspired capabilities for more effective algorithm discovery. These features are **off by default** for backward compatibility and can be enabled via configuration.

## Overview

The extensions add four major capabilities:

| Feature | Description | Benefit |
|---------|-------------|---------|
| **Adaptive Operation Selection** | UCB1/Thompson bandit learns which operations work best | Faster convergence to good solutions |
| **Fitness-Diversity Selection** | Balances exploitation and exploration when selecting parents | Avoids local optima |
| **Multi-Parent Crossover** | Combines 3 parents with role-based guidance | Richer solution combinations |
| **Strategic Prompt Sampling** | Contextual bandit learns which prompts work in which situations | More effective guidance |

Additional supporting features:
- **AST-Based Novelty**: Structural code similarity using AST node histograms
- **Lineage Tracking**: Family tree analysis to identify successful lineages
- **Prompt Queue**: Pre-computation of prompts for different evaluation outcomes

---

## Quick Start

Enable all features in your `problem.yaml`:

```yaml
evolution:
  adaptive:
    enabled: true
    algorithm: "ucb1"
  parent_selection:
    method: "fitness_diversity"
    diversity_weight: 0.3
  crossover_parents: 3
  prompt_sampling:
    enabled: true
    epsilon: 0.15
```

---

## Configuration Reference

### Adaptive Operation Selection

Controls how the system learns which evolutionary operations (mutate, crossover, explore, exploit) work best.

```yaml
evolution:
  adaptive:
    enabled: true              # Enable adaptive selection (default: false)
    algorithm: "ucb1"          # Algorithm: ucb1, thompson, epsilon_greedy
    exploration_factor: 1.0    # UCB1 exploration constant (higher = more exploration)
    epsilon: 0.1               # Epsilon-greedy exploration rate
    min_trials_per_arm: 2      # Minimum trials before exploitation
```

**Algorithms:**

| Algorithm | Description | Best For |
|-----------|-------------|----------|
| `ucb1` | Upper Confidence Bound - balances exploration/exploitation mathematically | General use, recommended |
| `thompson` | Thompson Sampling - Bayesian approach with Beta distributions | When you want probabilistic exploration |
| `epsilon_greedy` | Random exploration with probability epsilon | Simple, predictable behavior |

**How it works:**
1. Each operation (mutate, crossover, explore, exploit) is an "arm" in the bandit
2. After each iteration, the reward (score improvement) is recorded
3. The bandit learns which operations produce the best improvements
4. Over time, it favors successful operations while still exploring

---

### Parent Selection

Controls how parent solutions are selected for mutation and crossover operations.

```yaml
evolution:
  parent_selection:
    method: "fitness_diversity"  # Method: tournament, fitness_diversity
    diversity_weight: 0.3        # Balance between fitness (0) and diversity (1)
    tournament_size: 3           # Tournament size (for tournament method)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `tournament` | Standard tournament selection based on fitness only |
| `fitness_diversity` | Weighted combination of fitness and diversity from archive centroid |

**Fitness-Diversity Formula:**
```
score = (1 - diversity_weight) * normalized_fitness + diversity_weight * diversity
```

Where:
- `normalized_fitness` = solution score normalized to [0, 1]
- `diversity` = niche distance from archive centroid

---

### Multi-Parent Crossover

Enables combining 3 parent solutions instead of 2, with role-based guidance.

```yaml
evolution:
  crossover_parents: 3  # Number of parents: 2 or 3 (default: 2)
```

**3-Parent Crossover Prompts:**
- "Combine: core algorithm from A, optimizations from B, edge-case handling from C"
- "Synthesize: A's approach + B's data structures + C's performance techniques"
- "Create hybrid: best algorithmic idea from A, best optimization from B, best validation from C"

**Parent Selection for Multi-Crossover:**
1. First parent: Selected via fitness-diversity balance
2. Second parent: Maximizes diversity from first parent
3. Third parent: Maximizes diversity from both selected parents

---

### Strategic Prompt Sampling

Learns which prompt variations work best in different contexts using a contextual bandit.

```yaml
evolution:
  prompt_sampling:
    enabled: true    # Enable prompt learning (default: false)
    epsilon: 0.15    # Exploration rate (0 = always exploit, 1 = always explore)
```

**Context Features Used:**
1. Archive size (normalized)
2. Niche coverage
3. Best score achieved
4. Average score
5. Number of parent solutions
6. Parent diversity (score variance)

**Prompt Pools by Operation:**

| Operation | Prompt Categories |
|-----------|-------------------|
| Mutate (light) | efficiency, edge_cases, simplify, error_handling |
| Mutate (medium) | optimize_core, refactor_design, enhance_technique, generalize |
| Mutate (heavy) | restructure, replace_component, combine_strategies, scalability |
| Crossover | hybrid, algo_from_a_opt_from_b, merge_techniques, leverage_strengths |
| Explore | different_approach, unconventional, paradigm_shift, cross_domain |
| Exploit | optimize_further, micro_optimize, more_efficient, polish |

---

## Supporting Features

### AST-Based Novelty

Computes structural similarity between solutions using Abstract Syntax Tree analysis.

**Location:** `src/obsidian/research/novelty/ast_distance.py`

**How it works:**
1. Parses code into AST
2. Creates weighted histogram of node types
3. Computes cosine distance between histograms

**Node Weights (examples):**
```python
{
    "FunctionDef": 3.0,    # High weight - algorithmic structure
    "For": 2.5,
    "While": 2.5,
    "If": 2.0,
    "Call": 1.5,
    "BinOp": 1.5,
    "Constant": 0.3,       # Low weight - literals
    "Pass": 0.1,
}
```

**Usage:**
```python
from obsidian.research.novelty import compute_ast_distance, ASTNoveltyComputer

# Direct distance computation
distance = compute_ast_distance(code1, code2)  # Returns 0.0-1.0

# Novelty against archive
computer = ASTNoveltyComputer(k_nearest=5)
novelty = computer.compute_novelty(new_code, archive_codes)
```

---

### Lineage Tracking

Tracks solution family trees to identify successful and stagnant lineages.

**Location:** `src/obsidian/research/lineage.py`

**Features:**
- Build family trees from parent_ids
- Identify lineages with consistent improvement
- Find stagnant lineages to abandon
- Suggest cross-pollination between successful lineages

**Usage:**
```python
from obsidian.research.lineage import LineageTracker

tracker = LineageTracker(archive)

# Find successful lineages
successful = tracker.get_successful_lineages(
    min_improvement=0.05,
    min_descendants=2
)

# Find stagnant lineages
stagnant = tracker.get_stagnant_lineages(
    max_improvement=0.01,
    min_descendants=3
)

# Suggest crossover pairs from different lineages
pairs = tracker.suggest_crossover_pairs()

# Get lineage statistics
stats = tracker.get_lineage_stats(root_solution_id)
# Returns: LineageStats(root_id, best_score, avg_score,
#          total_descendants, max_depth, improvement_rate, is_active)
```

---

### Prompt Queue

Pre-computes prompts for different evaluation outcomes to reduce latency.

**Location:** `src/obsidian/research/prompt_queue.py`

**Scenarios Pre-computed:**
- `failed`: Solution failed correctness tests
- `low_score`: Score < 0.4
- `medium_score`: Score 0.4-0.7
- `high_score`: Score > 0.7
- `known_algorithm`: Known algorithm detected

**Usage:**
```python
from obsidian.research.prompt_queue import PromptQueue

queue = PromptQueue(
    problem=problem,
    archive=archive,
    evolution_controller=evolution,
    prompt_builder=prompt_builder,
    cache_dir=state_dir / "prompt_cache"
)

# Pre-compute prompts for next iteration
queue.precompute_prompts(current_iteration=5)

# Get cached prompt based on evaluation outcome
prompt = queue.get_prompt_for_outcome(
    score=0.65,
    passed=True,
    is_known_algorithm=False,
    current_iteration=5
)
```

---

## Architecture

### Component Flow

```
problem.yaml
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                    research_hook.py                      │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ create_evolution │  │     UniversalEvaluator       │  │
│  │   _controller()  │  │  ┌────────────────────────┐  │  │
│  └────────┬────────┘  │  │ ASTNoveltyComputer     │  │  │
│           │           │  │ (if novelty.type=ast)  │  │  │
│           ▼           │  └────────────────────────┘  │  │
│  ┌─────────────────┐  └──────────────────────────────┘  │
│  │   Adaptive      │                                     │
│  │   Evolution     │◄──── record_outcome() ────┐        │
│  │   Controller    │                           │        │
│  │  ┌───────────┐  │                           │        │
│  │  │UCB1 Bandit│  │                    evaluation      │
│  │  └───────────┘  │                     result         │
│  └────────┬────────┘                           │        │
│           │                                    │        │
│           ▼                                    │        │
│  ┌─────────────────┐      ┌─────────────────┐ │        │
│  │ select_operation│ ───► │PromptSampler    │ │        │
│  │  - mutate       │      │ (contextual     │ │        │
│  │  - crossover    │      │  bandit)        │◄┘        │
│  │  - explore      │      └─────────────────┘          │
│  │  - exploit      │                                    │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ SolutionArchive │                                    │
│  │  - fitness_     │                                    │
│  │    diversity    │                                    │
│  │    selection    │                                    │
│  │  - multi_parent │                                    │
│  │    crossover    │                                    │
│  └─────────────────┘                                    │
└─────────────────────────────────────────────────────────┘
```

### Files Created/Modified

| File | Type | Description |
|------|------|-------------|
| `src/obsidian/research/bandit.py` | New | UCB1, Thompson, Epsilon-Greedy bandits |
| `src/obsidian/research/novelty/__init__.py` | New | Novelty module exports |
| `src/obsidian/research/novelty/ast_distance.py` | New | AST-based code distance |
| `src/obsidian/research/prompt_sampler.py` | New | Contextual bandit for prompts |
| `src/obsidian/research/lineage.py` | New | Lineage tracking and analysis |
| `src/obsidian/research/prompt_queue.py` | New | Prompt pre-computation |
| `src/obsidian/research/problem.py` | Modified | Added config dataclasses |
| `src/obsidian/research/evolution.py` | Modified | Added AdaptiveEvolutionController |
| `src/obsidian/research/archive.py` | Modified | Added fitness-diversity selection |
| `src/obsidian/research/prompt_builder.py` | Modified | 3-parent crossover support |
| `scripts/research_hook.py` | Modified | Integrated all components |
| `tests/test_alphaevolve.py` | New | 35 tests for new features |

---

## Example Configuration

### Minimal (Enable Adaptive Only)

```yaml
evolution:
  adaptive:
    enabled: true
```

### Recommended (Balanced)

```yaml
evolution:
  adaptive:
    enabled: true
    algorithm: "ucb1"
    exploration_factor: 1.0
  parent_selection:
    method: "fitness_diversity"
    diversity_weight: 0.3
  crossover_parents: 3
  prompt_sampling:
    enabled: true
    epsilon: 0.15
```

### Aggressive Exploration

```yaml
evolution:
  adaptive:
    enabled: true
    algorithm: "ucb1"
    exploration_factor: 2.0  # Higher exploration
  parent_selection:
    method: "fitness_diversity"
    diversity_weight: 0.5   # More diversity
  crossover_parents: 3
  prompt_sampling:
    enabled: true
    epsilon: 0.3            # More prompt exploration
```

### Conservative (More Exploitation)

```yaml
evolution:
  adaptive:
    enabled: true
    algorithm: "epsilon_greedy"
    epsilon: 0.05           # Less exploration
  parent_selection:
    method: "fitness_diversity"
    diversity_weight: 0.1   # Favor fitness
  crossover_parents: 2      # Standard crossover
  prompt_sampling:
    enabled: true
    epsilon: 0.05
```

---

## Monitoring and Debugging

### Adaptive Learning Stats

The research hook output includes adaptive learning statistics:

```
Adaptive Learning: Best operation = crossover, Stats = {
  'mutate': {'trials': 5, 'avg_reward': 0.023, 'success_rate': 0.6},
  'crossover': {'trials': 8, 'avg_reward': 0.065, 'success_rate': 0.75},
  'explore': {'trials': 12, 'avg_reward': 0.051, 'success_rate': 0.5},
  'exploit': {'trials': 3, 'avg_reward': 0.054, 'success_rate': 0.67}
}
```

### Database Files

Adaptive learning state is persisted in `.obsidian/`:

| File | Contents |
|------|----------|
| `bandit_stats.db` | Operation selection statistics |
| `prompt_stats.db` | Prompt sampling statistics |
| `archive.db` | Solution archive |

### Programmatic Access

```python
from obsidian.research.evolution import create_evolution_controller

# Create controller
evolution = create_evolution_controller(problem.evolution, state_dir)

# Get operation stats
if hasattr(evolution, 'get_operation_stats'):
    stats = evolution.get_operation_stats()
    print(f"Best operation: {evolution.operation_bandit.get_best_arm()}")

# Get prompt sampler stats
if prompt_sampler:
    prompt_stats = prompt_sampler.get_stats()
    top_prompts = prompt_sampler.get_best_prompts(5)
```

---

## References

- [AlphaEvolve (DeepMind)](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/) - Inspiration for evolutionary code generation
- [Ralph Wiggum Pattern](https://paddo.dev/blog/ralph-wiggum-autonomous-loops/) - Autonomous loop pattern using Claude Code hooks
- [MAP-Elites](https://arxiv.org/abs/1504.04909) - Quality-Diversity algorithm used for archive
- [UCB1 Algorithm](https://homes.di.unimi.it/~cesabian/Pubblicazioni/ml-02.pdf) - Multi-armed bandit algorithm
