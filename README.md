# Obsidian

Obsessive learning loop plugin for Claude Code with In-Context Reinforcement Learning (ICRL).

## Overview

Obsidian enables Claude Code to obsess over problems like humans do - iterating, learning from feedback, and improving until goals are achieved. It supports two modes:

| Mode | Use Case | Configuration |
|------|----------|---------------|
| **Standard Mode** | Fix tests, improve coverage | `obsidian.yaml` |
| **Research Mode** | Discover novel algorithms | `problem.yaml` |

## Quick Start

### Standard Mode (Test-Driven Learning)

```bash
# Install
pip install -e /path/to/obsidian

# In your project, create obsidian.yaml
cat > obsidian.yaml << 'EOF'
max_attempts: 10
success_threshold: 0.90
evaluator:
  pytest:
    enabled: true
  coverage:
    enabled: true
    source: "src"
EOF

# Copy hooks to your project
mkdir -p hooks
cat > hooks/hooks.json << 'EOF'
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "python3 /path/to/obsidian/scripts/stop_hook.py", "timeout": 300}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 /path/to/obsidian/scripts/session_start.py", "timeout": 10}]}]
  }
}
EOF

# Start Claude Code - it will loop until tests pass!
```

### Research Mode (Algorithm Discovery)

```bash
# Initialize a research problem
obsidian research init --template algorithm --name "Novel Sorting"

# Edit problem.yaml, create tests, implement benchmark.py

# Start Claude Code
# Give it: "Discover an efficient sorting algorithm"
# Obsidian will iterate, storing discoveries in a quality-diversity archive
```

## Modes

### Standard Mode

For code quality improvement:
- **Evaluators**: pytest, coverage, ruff, pyright
- **Reward**: Weighted composite score
- **Memory**: Episodic (past attempts with outcomes)
- **Strategy**: Explore/Exploit switching

### Research Mode

For algorithm discovery:
- **Evaluators**: User-defined (correctness, benchmark, novelty)
- **Archive**: MAP-Elites quality-diversity
- **Evolution**: Mutation, crossover, exploration, exploitation
- **Scale**: 1000+ iterations with checkpointing

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

## How It Works

### The Learning Loop

1. **Claude makes changes** to the codebase
2. **Stop hook triggers** when Claude tries to stop
3. **Evaluators run** (tests, benchmarks)
4. **Reward computed** from scores
5. **Decision**:
   - Target achieved → Allow stop
   - Not achieved → Exit code 2 (block, inject feedback)
6. **Claude continues** with feedback

### ICRL (In-Context Reinforcement Learning)

- Past attempts with rewards injected as context
- Claude learns what works and what doesn't
- Strategy adapts based on reward trends

### Quality-Diversity (Research Mode)

- MAP-Elites archive stores solutions by niche
- Evolutionary operations guide exploration
- Novelty rewarded to encourage diversity

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

## Project Structure

```
obsidian/
├── src/obsidian/
│   ├── cli.py              # CLI commands
│   ├── config.py           # Configuration
│   ├── evaluator/          # Pytest, coverage, etc.
│   ├── memory/             # Episode storage
│   ├── strategy/           # Circuit breaker, modes
│   ├── icrl/               # Context building
│   ├── research/           # Research mode (MAP-Elites, evolution)
│   └── logging.py          # Structured logging
├── scripts/
│   ├── stop_hook.py        # Standard mode hook
│   ├── session_start.py    # Context injection
│   └── research_hook.py    # Research mode hook
├── hooks/
│   └── hooks.json          # Hook configuration
├── examples/
│   └── sorting/            # Research mode example
├── tests/                  # 143 tests
└── docs/                   # Documentation
```

## Documentation

- [Installation Guide](docs/INSTALLATION.md)
- [Configuration Reference](docs/CONFIGURATION.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Requirements

- Python 3.10+
- Claude Code CLI
- pytest (for evaluation)

## Research Mode Templates

```bash
obsidian research init --template algorithm      # Algorithm discovery
obsidian research init --template ml_model       # ML model design
obsidian research init --template optimization   # Optimization problems
obsidian research init --template custom         # Custom problem
```

## License

MIT
