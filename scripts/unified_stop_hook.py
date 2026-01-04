#!/usr/bin/env python3
"""
Obsidian Unified Stop Hook.

This hook automatically detects the mode based on project configuration:
- If problem.yaml exists → Research Mode (algorithm discovery)
- If obsidian.yaml exists → Standard Mode (test-driven learning)
- Otherwise → Pass through (no intervention)

This allows seamless switching between modes without changing hooks.
"""

import json
import os
import sys
from pathlib import Path

# Add src to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))


def detect_mode(cwd: Path) -> str:
    """
    Detect which mode to use based on project files.

    Returns:
        "research" - If problem.yaml exists
        "standard" - If obsidian.yaml exists (but not problem.yaml)
        "passthrough" - If neither exists
    """
    problem_file = cwd / "problem.yaml"
    config_file = cwd / "obsidian.yaml"

    if problem_file.exists():
        return "research"
    elif config_file.exists():
        return "standard"
    else:
        return "passthrough"


def run_research_mode():
    """Execute research mode hook."""
    # Import and run research hook
    from scripts.research_hook import main as research_main
    research_main()


def run_standard_mode():
    """Execute standard mode hook."""
    # Import and run standard hook
    from scripts.stop_hook import main as standard_main
    standard_main()


def main():
    """Main unified hook logic."""
    # Read input from Claude Code
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # No input, pass through
        print(json.dumps({"continue": False}))
        return

    cwd = Path(input_data.get("cwd", os.getcwd()))

    # Detect mode
    mode = detect_mode(cwd)

    if mode == "research":
        # Re-read stdin for research hook (it needs the data)
        # Since stdin is consumed, we pass data via environment
        os.environ["OBSIDIAN_INPUT"] = json.dumps(input_data)

        # Import research hook inline to avoid circular imports
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "research_hook",
            SCRIPT_DIR / "research_hook.py"
        )
        research_hook = importlib.util.module_from_spec(spec)

        # Patch stdin for the research hook
        import io
        sys.stdin = io.StringIO(json.dumps(input_data))

        spec.loader.exec_module(research_hook)

    elif mode == "standard":
        # Same approach for standard hook
        import io
        sys.stdin = io.StringIO(json.dumps(input_data))

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "stop_hook",
            SCRIPT_DIR / "stop_hook.py"
        )
        stop_hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stop_hook)

    else:
        # Passthrough - allow stop
        print(json.dumps({"continue": False}))


if __name__ == "__main__":
    main()
