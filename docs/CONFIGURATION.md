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
