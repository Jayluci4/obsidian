# Troubleshooting Guide

## Common Issues

### Circuit Breaker is OPEN

**Symptom:** `Circuit breaker OPEN: No recovery after N loops`

**Cause:** The loop made no progress for multiple iterations.

**Solutions:**

```bash
# Check current status
obsidian status

# Reset circuit breaker
obsidian reset circuit

# Reset everything (including session state)
obsidian reset all
```

**Prevention:**
- Check if tests are actually runnable
- Verify evaluator configuration
- Review recent history: `obsidian history`

---

### Module Not Found Error

**Symptom:** `ModuleNotFoundError: No module named 'obsidian'`

**Solutions:**

```bash
# Option 1: Install package
pip install -e /path/to/obsidian

# Option 2: Set PYTHONPATH
export PYTHONPATH="/path/to/obsidian/src:$PYTHONPATH"

# Option 3: In scripts, add to path
import sys
sys.path.insert(0, "/path/to/obsidian/src")
```

---

### Evaluator Timeout

**Symptom:** Evaluation takes too long or times out.

**Solutions:**

1. Increase timeout in config:
```yaml
evaluator:
  pytest:
    timeout: 300  # 5 minutes
```

2. Optimize test suite:
```bash
# Run specific tests
pytest tests/unit/ -x --tb=short
```

3. Disable slow evaluators:
```yaml
evaluator:
  pyright:
    enabled: false
```

---

### No Episodes Recorded

**Symptom:** `obsidian history` shows no episodes.

**Causes:**
- Memory database not created
- Session not running through hooks
- Errors during episode storage

**Solutions:**

```bash
# Check if database exists
ls -la .obsidian/memory.db

# Check logs for errors
tail -50 .obsidian/obsidian.log

# Verify hooks are registered
cat hooks/hooks.json
```

---

### Reward Not Improving

**Symptom:** Reward stays flat across multiple iterations.

**Causes:**
- Tests not actually being fixed
- Evaluator weights misconfigured
- Claude stuck in a pattern

**Solutions:**

1. Check evaluator output:
```bash
obsidian test-evaluator pytest
obsidian test-evaluator coverage
```

2. Review recent episodes:
```bash
obsidian history -n 20
```

3. Force exploration mode by resetting:
```bash
obsidian reset session
```

4. Check if weights sum to 1.0:
```bash
obsidian config validate
```

---

### Config Validation Errors

**Symptom:** `obsidian config validate` reports errors.

**Common issues:**

1. **Weights don't sum to 1.0:**
```yaml
evaluator:
  weights:
    pytest: 0.60
    coverage: 0.40  # Must sum to 1.0
```

2. **Invalid threshold:**
```yaml
success_threshold: 0.90  # Must be 0-1
```

3. **No evaluators enabled:**
```yaml
evaluator:
  pytest:
    enabled: true  # At least one required
```

---

### Hook Not Executing

**Symptom:** Claude stops without running evaluation.

**Causes:**
- Hook not registered
- Script path incorrect
- Permission denied

**Solutions:**

1. Verify hook registration:
```json
{
  "hooks": [{
    "matcher": "Stop",
    "hooks": [{
      "type": "command",
      "command": "python /absolute/path/to/scripts/stop_hook.py"
    }]
  }]
}
```

2. Make scripts executable:
```bash
chmod +x scripts/*.py
```

3. Test hook manually:
```bash
echo '{"session_id": "test", "cwd": "'$(pwd)'"}' | python scripts/stop_hook.py
```

---

### SQLite Errors

**Symptom:** `sqlite3.OperationalError: database is locked`

**Cause:** Concurrent access to database.

**Solutions:**

1. Ensure WAL mode is enabled (default):
```yaml
database:
  journal_mode: "WAL"
```

2. Close other processes accessing the database.

3. Delete and recreate database:
```bash
rm .obsidian/memory.db
# Will be recreated on next run
```

---

### High Memory Usage

**Symptom:** Python process using too much memory.

**Causes:**
- Too many episodes loaded
- Large log files

**Solutions:**

1. Prune old episodes:
```yaml
advanced:
  prune_old_episodes: true
  prune_threshold: 100
```

2. Reduce top-k:
```yaml
icrl:
  top_k: 3
```

3. Rotate logs:
```yaml
logging:
  max_size_mb: 5
  backup_count: 2
```

---

### Context Limit Exceeded

**Symptom:** Claude runs out of context window.

**Solutions:**

1. Reduce context budget:
```yaml
icrl:
  max_context_tokens: 5000  # Default 10000
```

2. Enable compression:
```yaml
icrl:
  compression_threshold: 10  # Compress older episodes
```

3. Reduce episodes:
```yaml
icrl:
  top_k: 3
```

---

## Debug Mode

Enable debug logging:

```yaml
logging:
  level: "DEBUG"

advanced:
  debug: true
```

Then check logs:
```bash
tail -f .obsidian/obsidian.log
```

## Getting Help

1. Check status: `obsidian status`
2. Validate config: `obsidian config validate`
3. Review logs: `tail .obsidian/obsidian.log`
4. Check history: `obsidian history`

## Reporting Issues

When reporting issues, include:

1. Output of `obsidian status`
2. Output of `obsidian config validate`
3. Last 50 lines of log: `tail -50 .obsidian/obsidian.log`
4. Python version: `python --version`
5. OS: `uname -a`
