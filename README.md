# Obsidian

An obsessive learning loop plugin for Claude Code with In-Context Reinforcement Learning (ICRL) feedback.

## Overview

Obsidian enables Claude Code to learn from its attempts through:

- **Multi-objective evaluation**: pytest, coverage, ruff, pyright
- **Composite reward signals**: Weighted scoring with delta tracking
- **Persistent memory**: Episodic, semantic, and procedural memory in SQLite
- **Adaptive strategy**: Explore/exploit mode switching based on reward trends
- **Circuit breaker**: Prevents runaway loops when stuck

## Quick Start

```bash
# Install
pip install -e .

# Check status
obsidian status

# Validate config
obsidian config validate

# View history
obsidian history -n 10
```

## How It Works

1. **Stop Hook**: After each Claude response, Obsidian:
   - Runs evaluators (pytest, coverage)
   - Computes composite reward (0-1)
   - Checks circuit breaker state
   - Decides: continue (exit 2) or stop (exit 0)

2. **Session Start Hook**: Injects ICRL context:
   - Top-K episodes with rewards
   - Strategy mode guidance
   - Historical patterns to follow/avoid

3. **Learning Loop**:
   ```
   Claude Response → Evaluate → Store Episode → Update Strategy → Inject Feedback → Continue
   ```

## Configuration

Create `obsidian.yaml` in your project root:

```yaml
max_attempts: 10
success_threshold: 0.90

evaluator:
  weights:
    pytest: 0.60
    coverage: 0.40
  pytest:
    enabled: true
    timeout: 120
  coverage:
    enabled: true
    threshold: 70

icrl:
  enabled: true
  top_k: 5
  max_context_tokens: 10000

circuit_breaker:
  enabled: true
  no_progress_threshold: 3
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for full reference.

## CLI Commands

| Command | Description |
|---------|-------------|
| `obsidian status` | Show current session status |
| `obsidian reset circuit` | Reset circuit breaker |
| `obsidian reset all` | Reset all state |
| `obsidian history` | View episode history |
| `obsidian stats` | Show statistics |
| `obsidian config validate` | Validate configuration |
| `obsidian config show` | Show current config |
| `obsidian test-evaluator pytest` | Test single evaluator |

## Project Structure

```
obsidian/
├── src/obsidian/
│   ├── cli.py              # CLI commands
│   ├── config.py           # Configuration loader
│   ├── errors.py           # Error handling
│   ├── logging.py          # Logging infrastructure
│   ├── state.py            # Session state
│   ├── evaluator/          # Evaluators (pytest, coverage, etc.)
│   ├── memory/             # Memory system (episodic, semantic)
│   ├── strategy/           # Strategy controller, circuit breaker
│   └── icrl/               # ICRL context building
├── scripts/
│   ├── stop_hook.py        # Main learning loop
│   └── session_start.py    # Context injection
├── hooks/
│   └── hooks.json          # Hook registrations
├── tests/                  # Test suite (115 tests)
├── docs/                   # Documentation
└── obsidian.yaml           # Configuration
```

## Documentation

- [Installation Guide](docs/INSTALLATION.md)
- [Configuration Reference](docs/CONFIGURATION.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Requirements

- Python 3.10+
- Claude Code CLI
- pytest (for test evaluation)

## License

MIT
