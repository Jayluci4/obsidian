#!/usr/bin/env python3
"""
Obsidian SessionStart Hook: Inject ICRL context at session start.

This hook runs at the beginning of a Claude Code session.
It loads previous attempt history and injects it as context
for in-context reinforcement learning.
"""

import json
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from obsidian.config import get_state_dir, load_config
from obsidian.errors import safe_execute, HookError
from obsidian.icrl import ICRLContextBuilder, ContextBudgetManager
from obsidian.logging import setup_logging, ObsidianLogger


def main():
    """Main hook handler."""
    start_time = time.time()

    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # No input - nothing to inject
        print(json.dumps({"continue": True}))
        sys.exit(0)

    session_id = input_data.get("session_id", "default")
    cwd = input_data.get("cwd", os.getcwd())

    project_path = Path(cwd)

    # Load configuration
    config = load_config(project_path)

    # Check if ICRL context injection is enabled
    if not config.icrl.enabled:
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Get state directory
    state_dir = get_state_dir(project_path, config)

    # Setup logging
    logger = None
    obs_logger = None
    if config.logging.enabled:
        try:
            logger = setup_logging(
                state_dir=state_dir,
                level=config.logging.level,
                log_file=config.logging.file,
                max_size_mb=config.logging.max_size_mb,
                backup_count=config.logging.backup_count,
                json_format=config.logging.json_format,
            )
            obs_logger = ObsidianLogger(logger)
            obs_logger.hook_start("session_start", session_id)
        except Exception as e:
            # Continue without logging if setup fails
            sys.stderr.write(f"Warning: Logging setup failed: {e}\n")

    # Check if memory database exists
    db_path = state_dir / "memory.db"
    if not db_path.exists():
        # No history - nothing to inject
        if obs_logger:
            obs_logger.debug("session_start", "No memory database found, skipping context injection")
            obs_logger.hook_end(
                hook_name="session_start",
                duration_ms=(time.time() - start_time) * 1000,
                result="no_history",
            )
        print(json.dumps({"continue": True}))
        sys.exit(0)

    try:
        # Initialize context budget manager
        budget_manager = ContextBudgetManager(
            max_tokens=config.icrl.max_context_tokens,
            compression_threshold=config.icrl.compression_threshold,
        )

        # Build ICRL context
        builder = ICRLContextBuilder(
            state_dir=state_dir,
            session_id=session_id,
            top_k=config.icrl.top_k,
            include_failures=config.icrl.include_failures,
        )

        context = builder.build_session_start_context()
        builder.close()

        if not context:
            # No history to inject
            if obs_logger:
                obs_logger.debug("session_start", "No context to inject")
                obs_logger.hook_end(
                    hook_name="session_start",
                    duration_ms=(time.time() - start_time) * 1000,
                    result="empty_context",
                )
            print(json.dumps({"continue": True}))
            sys.exit(0)

        # Log context budget usage
        if obs_logger:
            from obsidian.icrl.context_budget import estimate_tokens
            tokens_used = estimate_tokens(context)
            obs_logger.context_budget(
                tokens_used=tokens_used,
                budget=config.icrl.max_context_tokens,
                episodes_included=context.count("<attempt"),
            )
            obs_logger.hook_end(
                hook_name="session_start",
                duration_ms=(time.time() - start_time) * 1000,
                result="context_injected",
            )

        # Inject context as system message
        output = {
            "continue": True,
            "systemMessage": context,
        }

        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block session
        if obs_logger:
            obs_logger.error("session_start", f"Context building failed: {e}", e)
            obs_logger.hook_end(
                hook_name="session_start",
                duration_ms=(time.time() - start_time) * 1000,
                result="error",
            )
        else:
            sys.stderr.write(f"Obsidian SessionStart error: {e}\n")

        print(json.dumps({"continue": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
