# Installation Guide

## Prerequisites

- Python 3.10 or higher
- Claude Code CLI installed and configured
- pytest (for test evaluation)
- coverage (for coverage evaluation)

## Installation Methods

### Method 1: Install from Source (Recommended)

```bash
# Clone or copy the obsidian directory to your project
cd /path/to/your/project

# Install in editable mode
pip install -e /path/to/obsidian

# Verify installation
obsidian --version
```

### Method 2: Add to PYTHONPATH

```bash
# Add to your shell profile (.bashrc, .zshrc)
export PYTHONPATH="/path/to/obsidian/src:$PYTHONPATH"

# Run CLI directly
python -m obsidian.cli status
```

## Claude Code Plugin Setup

### 1. Register the Plugin

Create or update `.claude-plugin/plugin.json` in your project:

```json
{
  "name": "obsidian",
  "version": "0.1.0",
  "description": "Obsessive learning loop with ICRL feedback",
  "hooks": "../hooks/hooks.json"
}
```

### 2. Configure Hooks

Create `hooks/hooks.json`:

```json
{
  "hooks": [
    {
      "matcher": "Stop",
      "hooks": [{
        "type": "command",
        "command": "python /path/to/obsidian/scripts/stop_hook.py",
        "timeout": 300
      }]
    },
    {
      "matcher": "SessionStart",
      "hooks": [{
        "type": "command",
        "command": "python /path/to/obsidian/scripts/session_start.py",
        "timeout": 10
      }]
    }
  ]
}
```

### 3. Create Configuration

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
  coverage:
    enabled: true
    source: "src"
    threshold: 70
```

## Verification

```bash
# Check plugin status
obsidian status

# Validate configuration
obsidian config validate

# Test an evaluator
obsidian test-evaluator pytest
```

## Directory Structure After Setup

```
your-project/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json
├── .obsidian/              # Created at runtime
│   ├── memory.db           # Episode database
│   ├── circuit_breaker.json
│   ├── session_state.json
│   └── obsidian.log
├── obsidian.yaml           # Configuration
└── src/                    # Your source code
```

## Troubleshooting Installation

### Import Errors

If you see `ModuleNotFoundError: No module named 'obsidian'`:

```bash
# Ensure package is installed
pip install -e /path/to/obsidian

# Or set PYTHONPATH
export PYTHONPATH="/path/to/obsidian/src:$PYTHONPATH"
```

### Permission Issues

If hooks fail to execute:

```bash
# Make scripts executable
chmod +x /path/to/obsidian/scripts/*.py
```

### Missing Dependencies

```bash
# Install required packages
pip install pyyaml pytest pytest-cov
```

## Updating

```bash
# Pull latest changes
cd /path/to/obsidian
git pull

# Reinstall
pip install -e .
```

## Uninstalling

```bash
# Remove package
pip uninstall obsidian

# Remove state directory (optional)
rm -rf .obsidian/

# Remove config (optional)
rm obsidian.yaml
```
