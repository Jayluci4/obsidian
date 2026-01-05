# Obsidian

Obsessive learning loop plugin for Claude Code with In-Context Reinforcement Learning (ICRL).

## What is Obsidian?

Obsidian enables Claude Code to obsess over problems like humans do - iterating, learning from feedback, and improving until goals are achieved.

| Mode | Use Case | Configuration |
|------|----------|---------------|
| **Standard Mode** | Fix tests, improve coverage | `obsidian.yaml` |
| **Research Mode** | Discover novel algorithms | `problem.yaml` |

### Key Features

- **Autonomous Loop**: Blocks Claude from stopping until goals achieved (Ralph Wiggum pattern)
- **ICRL Context**: Injects past attempts with rewards to guide learning
- **MAP-Elites Archive**: Quality-diversity storage for algorithm discovery
- **AlphaEvolve Extensions**: Adaptive bandits, multi-parent crossover, AST novelty
- **Known Algorithm Detection**: Penalizes rediscovery of existing algorithms
- **Circuit Breaker**: Prevents infinite loops when stuck

## Installation

### Step 1: Install Python Package

```bash
pip install -e /path/to/obsidian
```

### Step 2: Add Plugin to Claude Code

**Option A: Via Marketplace (Recommended)**

Inside Claude Code, run:
```
/plugin marketplace add /path/to/obsidian
/plugin install obsidian@obsidian-marketplace
```

Or if hosted on GitHub:
```
/plugin marketplace add username/obsidian
/plugin install obsidian@obsidian-marketplace
```

**Option B: Direct Load**

```bash
claude --plugin-dir /path/to/obsidian
```

### Step 3: Verify Installation

Inside Claude Code, run:
```
/obsidian:status
```

## Quick Start

### Standard Mode: Fix Failing Tests

1. Create `obsidian.yaml` in your project:

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

2. Start Claude Code and give it a task:

```
Fix the failing tests
```

Obsidian will automatically:
- Run tests after each attempt
- Block Claude from stopping until tests pass
- Inject feedback to guide improvements

### Research Mode: Discover Algorithms

1. Initialize a research problem:

```
/obsidian:research-init algorithm
```

Or via CLI:
```bash
obsidian research init --template algorithm --name "My Algorithm"
```

2. Edit the generated files:
   - `problem.yaml` - Problem specification
   - `solution.py` - Initial solution (can be empty)
   - `tests/` - Correctness tests
   - `benchmark.py` - Performance benchmark

3. Start Claude Code and give it a task:

```
Discover an efficient sorting algorithm that beats the baseline
```

Obsidian will iterate for hundreds of attempts, storing discoveries in a MAP-Elites archive.

## Plugin Commands

| Command | Description |
|---------|-------------|
| `/obsidian:status` | Show current learning loop status |
| `/obsidian:history` | View attempt history |
| `/obsidian:research-init` | Initialize and start a research problem |
| `/obsidian:research-status` | Show research progress |
| `/obsidian:research-export` | Export best solutions |

### Research Init Syntax

```
/obsidian:research-init "your prompt here" --max-loops N --target SCORE
```

**Parameters:**
- `"prompt"` - The research task description (required)
- `--max-loops` - Maximum iterations (default: 100)
- `--target` - Target score 0.0-1.0 (default: 0.9)
- `--template` - algorithm, ml_model, optimization, custom (default: algorithm)

**Examples:**

```
/obsidian:research-init "Discover a 2x2 matrix multiplication using fewer than 8 multiplications" --max-loops 50 --target 0.95

/obsidian:research-init "Find an efficient sorting algorithm for nearly-sorted arrays" --max-loops 100

/obsidian:research-init "Design a neural network architecture for MNIST with <10k parameters" --template ml_model --max-loops 200
```

## How It Works

```
┌─────────────────────────────────────────────────┐
│  1. Claude makes changes to code                │
│                    ↓                            │
│  2. Claude tries to stop                        │
│                    ↓                            │
│  3. Obsidian Stop Hook triggers                 │
│     • Runs evaluators (pytest, benchmark)       │
│     • Computes reward score                     │
│                    ↓                            │
│  4. Decision:                                   │
│     • Target achieved? → Allow stop             │
│     • Not achieved? → Block + inject feedback   │
│                    ↓                            │
│  5. Claude continues with ICRL context          │
│     (past attempts + rewards + strategy)        │
└─────────────────────────────────────────────────┘
```

## Configuration

### Standard Mode (obsidian.yaml)

```yaml
max_attempts: 10
success_threshold: 0.90

evaluator:
  weights:
    pytest: 0.60
    coverage: 0.40
  pytest:
    enabled: true
  coverage:
    enabled: true
    source: "src"
    threshold: 70

circuit_breaker:
  enabled: true
  no_progress_threshold: 3
```

### Research Mode (problem.yaml)

```yaml
problem:
  name: "Novel Algorithm"
  description: "Discover an efficient algorithm..."
  solution_file: "solution.py"

evaluator:
  correctness:
    command: "pytest tests/ -x"
  benchmark:
    command: "python benchmark.py solution.py"
    direction: "maximize"
    target_score: 0.9

archive:
  type: "map_elites"
  niches:
    - name: "approach"
      values: ["greedy", "dynamic", "other"]

loop:
  max_iterations: 1000
```

### AlphaEvolve Extensions (Research Mode)

Enable advanced evolutionary features for improved algorithm discovery:

```yaml
evolution:
  # Adaptive operation selection (learns what works)
  adaptive:
    enabled: true
    algorithm: "ucb1"  # ucb1, thompson, epsilon_greedy

  # Fitness-diversity parent selection
  parent_selection:
    method: "fitness_diversity"
    diversity_weight: 0.3

  # 3-parent crossover
  crossover_parents: 3

  # Strategic prompt learning
  prompt_sampling:
    enabled: true
    epsilon: 0.15
```

See [AlphaEvolve Documentation](docs/ALPHAEVOLVE.md) for complete details.

## CLI Commands

```bash
# Standard Mode
obsidian status              # Session status
obsidian history             # View attempt history
obsidian stats               # Statistics
obsidian reset circuit       # Reset circuit breaker
obsidian config validate     # Validate configuration

# Research Mode
obsidian research init       # Initialize research problem
obsidian research status     # Show progress
obsidian research archive    # View solution archive
obsidian research export     # Export best solutions
obsidian research reset      # Reset research state
```

## Research Mode Templates

```bash
obsidian research init --template algorithm      # Sorting, search, graph
obsidian research init --template ml_model       # Neural network design
obsidian research init --template optimization   # Mathematical optimization
obsidian research init --template custom         # Custom problem
```

## Examples

See `examples/` directory for complete working examples:

### Matrix Multiplication (`examples/matmul_test/`)

Discover novel 2x2 matrix multiplication algorithms (beat Strassen's 7 multiplications):

```bash
cd examples/matmul_test
# problem.yaml is pre-configured with AlphaEvolve features enabled
```

**Features demonstrated:**
- Known algorithm detection (Strassen, Winograd, naive)
- Benchmark scoring (minimize multiplications)
- MAP-Elites archive with approach/complexity niches
- UCB1 adaptive operation selection

**Run tests:**
```bash
pytest examples/matmul_test/tests/
```

### Continual Learning (`examples/continual_learning/`)

Example of continual learning problem setup.

### Running an Example

1. Navigate to example directory
2. Start Claude Code: `claude`
3. Give task: "Discover a novel algorithm that beats the baseline"
4. Watch Obsidian iterate automatically

## Documentation

- [Configuration Reference](docs/CONFIGURATION.md) - All configuration options
- [AlphaEvolve Extensions](docs/ALPHAEVOLVE.md) - Adaptive evolution features
- [Architecture Overview](docs/ARCHITECTURE.md) - System design
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues

## Testing

Run the test suite:

```bash
# All tests (352 tests)
pytest tests/

# Specific test files
pytest tests/test_alphaevolve.py    # AlphaEvolve features (35 tests)
pytest tests/test_research.py       # Research mode (39 tests)
pytest tests/test_evaluator.py      # Evaluator system
pytest tests/test_memory.py         # Memory system
pytest tests/test_strategy.py       # Strategy controller
pytest tests/test_icrl.py           # ICRL context building

# With coverage
pytest tests/ --cov=src/obsidian --cov-report=term-missing

# Run example tests
pytest examples/matmul_test/tests/
```

### Test Categories

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_alphaevolve.py` | 35 | Bandits, AST novelty, lineage, prompts |
| `test_research.py` | 39 | Problem spec, archive, evolution, evaluator |
| `test_icrl.py` | 46 | Context building, episode selection |
| `test_memory.py` | 40 | SQLite storage, episodes, sessions |
| `test_strategy.py` | 39 | Circuit breaker, mode switching |
| `test_evaluator.py` | 5 | Composite evaluator |
| `test_cli.py` | 32 | CLI commands |

## Requirements

- Python 3.10+
- Claude Code CLI
- pytest (for evaluation)

## License

MIT
