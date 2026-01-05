# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Obsidian is a Claude Code plugin that implements In-Context Reinforcement Learning (ICRL) for obsessive learning loops. It enables Claude to iterate on problems until goals are achieved, with two operational modes:

- **Standard Mode**: Fix tests, improve coverage (configured via `obsidian.yaml`)
- **Research Mode**: Discover algorithms using MAP-Elites quality-diversity (configured via `problem.yaml`)

## Common Commands

### Development
```bash
pip install -e .                    # Install in dev mode
pip install -e ".[dev]"             # Install with dev dependencies (pytest, ruff)
```

### Testing
```bash
pytest tests/                       # Run all tests
pytest tests/test_evaluator.py      # Run single test file
pytest tests/ -k "test_circuit"     # Run tests matching pattern
pytest tests/ --cov=src/obsidian    # Run with coverage
```

### Linting
```bash
ruff check src/                     # Check linting
ruff format src/                    # Format code
```

### CLI Usage
```bash
obsidian status                     # Session status
obsidian history                    # View attempt history
obsidian stats                      # Statistics
obsidian reset circuit              # Reset circuit breaker
obsidian config validate            # Validate configuration

# Research mode
obsidian research init --template algorithm --name "My Algo"
obsidian research status
obsidian research archive
obsidian research export --count 5
```

## Architecture

### Core Flow
The plugin uses Claude Code hooks to create a learning loop:
1. **SessionStart Hook** (`scripts/session_start.py`): Injects ICRL context from memory
2. **Stop Hook** (`scripts/unified_stop_hook.py`): Evaluates code, blocks if target not met (exit code 2)

### Key Components

**Evaluator System** (`src/obsidian/evaluator/`)
- `CompositeEvaluator`: Combines weighted scores from multiple evaluators
- Evaluators: `PytestEvaluator`, `CoverageEvaluator`, `RuffEvaluator`, `PyrightEvaluator`
- Score computation: `reward = sum(weight_i * score_i)`

**Memory System** (`src/obsidian/memory/`)
- SQLite-backed storage for episodes, session state
- `EpisodicMemory`: Individual attempts with rewards
- `SemanticMemory`: Learned facts
- `ProceduralMemory`: Strategy effectiveness

**Strategy System** (`src/obsidian/strategy/`)
- `CircuitBreaker`: CLOSED -> HALF_OPEN -> OPEN state machine
- `StrategyController`: EXPLOIT/EXPLORE/AUTONOMOUS modes based on reward trends

**ICRL System** (`src/obsidian/icrl/`)
- `ContextBuilder`: Builds experience buffer with quality-diversity filtering
- Episode selection: 60% top performers, 20% failures, 20% diverse approaches

**Research Mode** (`src/obsidian/research/`)
- `ProblemSpec`: Loads `problem.yaml` configuration
- `UniversalEvaluator`: Correctness + Benchmark + Novelty scoring
- `SolutionArchive`: MAP-Elites niche-based storage
- `EvolutionController`: Selects mutation/crossover/explore/exploit operations
- `AdaptiveEvolutionController`: AlphaEvolve-style UCB1 bandit for operation selection

**AlphaEvolve Extensions** (`src/obsidian/research/`)
- `bandit.py`: Multi-armed bandits (UCB1, Thompson, Epsilon-Greedy)
- `novelty/ast_distance.py`: AST-based structural code similarity
- `prompt_sampler.py`: Contextual bandit for strategic prompt selection
- `lineage.py`: Solution lineage tracking and analysis
- `prompt_queue.py`: Prompt pre-computation for different outcomes

See `docs/ALPHAEVOLVE.md` for complete documentation of these features.

### Hook Exit Codes
- `0`: Allow stop (target achieved, circuit open, max attempts)
- `2`: Block stop, inject feedback (continue learning)

### Configuration Files
- `obsidian.yaml`: Standard mode config (evaluators, thresholds, ICRL settings)
- `problem.yaml`: Research mode config (problem spec, benchmark, archive niches)
- State stored in `.obsidian/` directory

### Plugin Structure
- `hooks/hooks.json`: Hook definitions for Claude Code
- `.claude-plugin/plugin.json`: Plugin manifest

## File Organization
- `src/obsidian/`: Main package source
- `scripts/`: Hook scripts executed by Claude Code
- `tests/`: Test files
- `commands/`: Slash command markdown files
- `examples/`: Example configurations
