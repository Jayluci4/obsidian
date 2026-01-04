# Obsidian

Obsessive learning loop plugin for Claude Code with In-Context Reinforcement Learning (ICRL).

## What is Obsidian?

Obsidian enables Claude Code to obsess over problems like humans do - iterating, learning from feedback, and improving until goals are achieved.

| Mode | Use Case | Configuration |
|------|----------|---------------|
| **Standard Mode** | Fix tests, improve coverage | `obsidian.yaml` |
| **Research Mode** | Discover novel algorithms | `problem.yaml` |

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

See `examples/` directory:
- `examples/sorting/` - Algorithm discovery example

## Documentation

- [Configuration Reference](docs/CONFIGURATION.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Requirements

- Python 3.10+
- Claude Code CLI
- pytest (for evaluation)

## License

MIT
