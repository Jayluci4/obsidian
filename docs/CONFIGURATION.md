# Configuration Reference

Obsidian is configured via `obsidian.yaml` in your project root.

## Complete Configuration Example

```yaml
# Learning Loop Settings
max_attempts: 10
success_threshold: 0.90
state_dir: ".obsidian"

# Evaluator Configuration
evaluator:
  weights:
    pytest: 0.60
    coverage: 0.40
    ruff: 0.00
    pyright: 0.00

  pytest:
    enabled: true
    timeout: 120
    args: ["--tb=short", "-q"]

  coverage:
    enabled: true
    source: "src"
    threshold: 70
    timeout: 180

  ruff:
    enabled: false
    max_errors: 100
    timeout: 30
    source: "src"

  pyright:
    enabled: false
    max_errors: 50
    timeout: 60
    source: "src"

# ICRL Configuration
icrl:
  enabled: true
  top_k: 5
  include_failures: true
  max_context_tokens: 10000
  compression_threshold: 20
  filter_strategy: "quality_diversity"
  top_k_ratio: 0.6
  failure_ratio: 0.2
  diversity_ratio: 0.2

# Circuit Breaker
circuit_breaker:
  enabled: true
  no_progress_threshold: 3
  same_error_threshold: 5
  reward_decline_threshold: 0.1
  half_open_threshold: 2

# Strategy Controller
strategy:
  improve_threshold: 0.05
  decline_threshold: -0.05
  stuck_threshold: 0.02
  min_variance_window: 3
  max_consecutive_mode: 5

# Performance
performance:
  parallel_evaluators: true
  max_workers: 4
  cache_enabled: false

# Database
database:
  journal_mode: "WAL"
  synchronous: "NORMAL"
  cache_size: -64000

# Feedback Formatting
feedback:
  include_failed_tests: true
  max_failures_shown: 5
  include_coverage_delta: true
  verbose: false
  show_circuit_status: true
  show_strategy_mode: true

# Logging
logging:
  enabled: true
  level: "INFO"
  file: "obsidian.log"
  max_size_mb: 10
  backup_count: 3
  json_format: false
  log_evaluations: true
  log_state_changes: true
  log_circuit_breaker: true
  log_strategy_changes: true

# Response Analysis
response_analysis:
  enabled: true
  completion_threshold: 40
  stuck_error_count: 5
  detect_test_only: true
  detect_no_work: true
  detect_stuck: true

# Error Handling
error_handling:
  max_retries: 3
  retry_delay_seconds: 5
  global_timeout_seconds: 300
  continue_on_evaluator_failure: true
  fallback_reward: 0.0

# Hooks
hooks:
  session_start:
    enabled: true
    timeout: 10
  stop:
    enabled: true
    timeout: 300

# Advanced
advanced:
  prune_old_episodes: true
  prune_threshold: 100
  debug: false
  dry_run: false
```

## Configuration Sections

### Learning Loop

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_attempts` | int | 10 | Maximum iterations before stopping |
| `success_threshold` | float | 0.90 | Reward threshold to consider task complete |
| `state_dir` | string | ".obsidian" | Directory for state files |

### Evaluators

Each evaluator can be configured with:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | varies | Whether to run this evaluator |
| `weight` | float | varies | Weight in composite reward (must sum to 1.0) |
| `timeout` | int | 120 | Timeout in seconds |

#### pytest

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `args` | list | ["--tb=short", "-q"] | Additional pytest arguments |

#### coverage

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `source` | string | "src" | Source directory to measure |
| `threshold` | int | 70 | Minimum acceptable coverage % |

#### ruff / pyright

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_errors` | int | 100 | Maximum errors before score = 0 |
| `source` | string | "src" | Directory to check |

### ICRL (In-Context Reinforcement Learning)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | true | Enable ICRL context injection |
| `top_k` | int | 5 | Number of episodes to include |
| `include_failures` | bool | true | Include failure examples |
| `max_context_tokens` | int | 10000 | Token budget for ICRL context |
| `compression_threshold` | int | 20 | Compress episodes older than N |
| `filter_strategy` | string | "quality_diversity" | Episode selection strategy |

Filter strategies:
- `top_k`: Simply take top K by reward
- `quality_diversity`: Mix of top performers, failures, and diverse approaches
- `recent`: Most recent episodes

### Circuit Breaker

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | true | Enable circuit breaker |
| `no_progress_threshold` | int | 3 | Open after N loops without progress |
| `same_error_threshold` | int | 5 | Open after N loops with same error |
| `reward_decline_threshold` | float | 0.1 | Open if reward declines by >10% |
| `half_open_threshold` | int | 2 | Enter HALF_OPEN after N no-progress |

States:
- `CLOSED`: Normal operation
- `HALF_OPEN`: Monitoring for recovery
- `OPEN`: Halted, requires reset

### Strategy Controller

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `improve_threshold` | float | 0.05 | Switch to EXPLOIT if trend > 5% |
| `decline_threshold` | float | -0.05 | Switch to EXPLORE if trend < -5% |
| `stuck_threshold` | float | 0.02 | Variance threshold for stuck detection |
| `max_consecutive_mode` | int | 5 | Force mode switch after N consecutive |

### Logging

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | true | Enable logging |
| `level` | string | "INFO" | Log level (DEBUG, INFO, WARN, ERROR) |
| `file` | string | "obsidian.log" | Log file name |
| `max_size_mb` | int | 10 | Max log size before rotation |
| `json_format` | bool | false | Use JSON format for logs |

### Error Handling

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_retries` | int | 3 | Retry count for transient failures |
| `retry_delay_seconds` | float | 5.0 | Delay between retries |
| `continue_on_evaluator_failure` | bool | true | Continue if one evaluator fails |
| `fallback_reward` | float | 0.0 | Reward if all evaluators fail |

## Minimal Configuration

For most projects, a minimal config is sufficient:

```yaml
max_attempts: 10
success_threshold: 0.90

evaluator:
  pytest:
    enabled: true
  coverage:
    enabled: true
    source: "src"
```

All other settings will use sensible defaults.

## Validation

Validate your configuration:

```bash
obsidian config validate
```

This checks:
- Evaluator weights sum to 1.0
- Thresholds are in valid ranges
- Required settings are present

---

# Research Mode Configuration

Research Mode uses `problem.yaml` instead of `obsidian.yaml` for algorithm discovery tasks.

## Complete problem.yaml Example

```yaml
problem:
  name: "Novel Sorting Algorithm"
  description: |
    Discover an efficient sorting algorithm that sorts integers in ascending order.
    The algorithm should be correct, efficient, and potentially novel.
  solution_file: "solution.py"

evaluator:
  correctness:
    command: "pytest tests/ -x -q"
    timeout: 60

  benchmark:
    command: "python benchmark.py solution.py"
    timeout: 120
    direction: "maximize"
    baseline_score: 0.2
    target_score: 0.85
    weight: 0.7

  novelty:
    enabled: true
    weight: 0.3

archive:
  type: "map_elites"
  niches:
    - name: "approach"
      values: ["divide_conquer", "comparison", "distribution", "hybrid", "other"]
    - name: "complexity"
      values: ["linear", "linearithmic", "quadratic", "other"]

  max_solutions: 1000
  diversity_threshold: 0.1

evolution:
  mutation_rate: 0.4
  crossover_rate: 0.3
  explore_rate: 0.2
  exploit_rate: 0.1

  temperature: 1.0
  temperature_decay: 0.995
  min_temperature: 0.1

loop:
  max_iterations: 1000
  checkpoint_interval: 50
  early_stop_iterations: 100
  min_archive_size: 5
```

## Problem Specification

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| `problem.name` | string | Yes | Name of the research problem |
| `problem.description` | string | Yes | Description for Claude |
| `problem.solution_file` | string | Yes | File containing the solution |

## Evaluator Configuration

### Correctness

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `command` | string | Required | Command to verify correctness |
| `timeout` | int | 60 | Timeout in seconds |

### Benchmark

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `command` | string | Required | Benchmark command (must output JSON) |
| `timeout` | int | 120 | Timeout in seconds |
| `direction` | string | "maximize" | "maximize" or "minimize" |
| `baseline_score` | float | 0.0 | Score for naive solution |
| `target_score` | float | 1.0 | Target score to achieve |
| `weight` | float | 0.7 | Weight in final score |

Benchmark output format:
```json
{"score": 0.85, "metrics": {"time_ms": 12.5, "memory_mb": 1.2}}
```

### Novelty

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | true | Enable novelty scoring |
| `weight` | float | 0.3 | Weight in final score |

## Archive Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `type` | string | "map_elites" | Archive type |
| `niches` | list | Required | Niche definitions |
| `max_solutions` | int | 1000 | Maximum solutions to store |
| `diversity_threshold` | float | 0.1 | Minimum diversity between solutions |

### Niche Definition

```yaml
niches:
  - name: "approach"
    values: ["greedy", "dynamic", "other"]
```

## Evolution Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `mutation_rate` | float | 0.4 | Probability of mutation |
| `crossover_rate` | float | 0.3 | Probability of crossover |
| `explore_rate` | float | 0.2 | Probability of exploration |
| `exploit_rate` | float | 0.1 | Probability of exploitation |
| `temperature` | float | 1.0 | Initial temperature |
| `temperature_decay` | float | 0.995 | Decay per iteration |
| `min_temperature` | float | 0.1 | Minimum temperature |

### AlphaEvolve-Style Extensions

Enable advanced evolutionary features for improved algorithm discovery. See [ALPHAEVOLVE.md](ALPHAEVOLVE.md) for complete documentation.

```yaml
evolution:
  # Adaptive operation selection (UCB1 bandit)
  adaptive:
    enabled: true
    algorithm: "ucb1"        # ucb1, thompson, epsilon_greedy
    exploration_factor: 1.0  # UCB1 exploration constant

  # Fitness-diversity parent selection
  parent_selection:
    method: "fitness_diversity"  # tournament, fitness_diversity
    diversity_weight: 0.3

  # Multi-parent crossover (3 parents)
  crossover_parents: 3

  # Strategic prompt sampling
  prompt_sampling:
    enabled: true
    epsilon: 0.15
```

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `adaptive.enabled` | bool | false | Enable adaptive operation selection |
| `adaptive.algorithm` | string | "ucb1" | Bandit algorithm |
| `parent_selection.method` | string | "tournament" | Parent selection method |
| `parent_selection.diversity_weight` | float | 0.3 | Balance fitness vs diversity |
| `crossover_parents` | int | 2 | Number of parents for crossover |
| `prompt_sampling.enabled` | bool | false | Enable prompt learning |
| `prompt_sampling.epsilon` | float | 0.1 | Prompt exploration rate |

## Loop Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_iterations` | int | 1000 | Maximum iterations |
| `checkpoint_interval` | int | 50 | Save checkpoint every N iterations |
| `early_stop_iterations` | int | 100 | Stop if no improvement for N iterations |
| `min_archive_size` | int | 5 | Minimum solutions before early stopping |

## Minimal Research Configuration

```yaml
problem:
  name: "My Algorithm"
  description: "Discover an algorithm for..."
  solution_file: "solution.py"

evaluator:
  correctness:
    command: "pytest tests/ -x"
  benchmark:
    command: "python benchmark.py solution.py"
    target_score: 0.9

archive:
  niches:
    - name: "approach"
      values: ["type1", "type2", "other"]

loop:
  max_iterations: 100
```
