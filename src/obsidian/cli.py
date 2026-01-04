"""CLI commands for Obsidian plugin management."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_config, get_state_dir, find_config_file, ObsidianConfig
from .strategy.circuit_breaker import CircuitBreaker, CircuitState

# Problem templates for research mode
PROBLEM_TEMPLATES = {
    "algorithm": '''# Problem: {name}
# Discover a novel algorithm

problem:
  name: "{name}"
  description: |
    {description}

  solution_file: "solution.py"
  solution_interface: |
    # Define your solution interface here
    def solve(input_data):
        """Your algorithm implementation."""
        pass

evaluator:
  correctness:
    type: "pytest"
    command: "pytest tests/ -x -v"
    timeout: 120

  benchmark:
    command: "python benchmark.py solution.py"
    output_parser: "json"
    timeout: 300
    direction: "maximize"
    baseline_score: 0.3
    target_score: 0.9

  weights:
    correctness: 0.2
    benchmark: 0.6
    novelty: 0.2

archive:
  type: "map_elites"
  niches:
    - name: "approach"
      type: "categorical"
      values: ["greedy", "dynamic", "divide_conquer", "heuristic", "other"]
    - name: "complexity"
      type: "continuous"
      bins: [0, 50, 200, 1000]
  max_solutions_per_niche: 5

loop:
  max_iterations: 1000
  checkpoint_every: 50
  early_stop:
    threshold: 0.95
    patience: 100
''',
    "ml_model": '''# Problem: {name}
# Design a machine learning model/approach

problem:
  name: "{name}"
  description: |
    {description}

  solution_file: "model.py"
  solution_interface: |
    class Model:
        def __init__(self, config=None):
            pass

        def train(self, data):
            """Train the model."""
            pass

        def predict(self, inputs):
            """Make predictions."""
            pass

        def evaluate(self, test_data):
            """Return evaluation metrics."""
            pass

evaluator:
  correctness:
    type: "pytest"
    command: "pytest tests/ -x -v"
    timeout: 300

  benchmark:
    command: "python benchmark.py model.py"
    output_parser: "json"
    timeout: 3600
    direction: "maximize"
    baseline_score: 0.5
    target_score: 0.95

  weights:
    correctness: 0.1
    benchmark: 0.7
    novelty: 0.2

archive:
  type: "map_elites"
  niches:
    - name: "architecture"
      type: "categorical"
      values: ["linear", "tree", "neural", "ensemble", "other"]
    - name: "complexity"
      type: "continuous"
      bins: [0, 100, 1000, 10000]
  max_solutions_per_niche: 5

loop:
  max_iterations: 500
  checkpoint_every: 25
  early_stop:
    threshold: 0.98
    patience: 50
''',
    "optimization": '''# Problem: {name}
# Optimize a function or process

problem:
  name: "{name}"
  description: |
    {description}

  solution_file: "optimizer.py"
  solution_interface: |
    def optimize(objective_fn, constraints, initial_guess=None):
        """
        Find optimal solution.

        Args:
            objective_fn: Function to minimize/maximize
            constraints: Dict of constraints
            initial_guess: Starting point

        Returns:
            Optimal solution and value
        """
        pass

evaluator:
  correctness:
    type: "pytest"
    command: "pytest tests/ -x -v"
    timeout: 120

  benchmark:
    command: "python benchmark.py optimizer.py"
    output_parser: "json"
    timeout: 600
    direction: "maximize"
    baseline_score: 0.4
    target_score: 0.9

  weights:
    correctness: 0.2
    benchmark: 0.6
    novelty: 0.2

archive:
  type: "map_elites"
  niches:
    - name: "method"
      type: "categorical"
      values: ["gradient", "evolutionary", "bayesian", "local_search", "other"]
  max_solutions_per_niche: 5

loop:
  max_iterations: 500
  checkpoint_every: 25
''',
    "custom": '''# Problem: {name}
# Custom research problem

problem:
  name: "{name}"
  description: |
    {description}

  solution_file: "solution.py"

evaluator:
  correctness:
    type: "script"
    command: "python check_solution.py"
    timeout: 120

  benchmark:
    command: "python benchmark.py solution.py"
    output_parser: "json"
    timeout: 300
    direction: "maximize"

  weights:
    correctness: 0.2
    benchmark: 0.6
    novelty: 0.2

archive:
  type: "map_elites"
  niches: []
  max_solutions_per_niche: 10

loop:
  max_iterations: 1000
  checkpoint_every: 50
''',
}


def get_project_path() -> Path:
    """Get the project path (current directory)."""
    return Path.cwd()


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts or "N/A"


def format_reward(reward: float) -> str:
    """Format reward with color indicator."""
    if reward >= 0.9:
        return f"{reward:.3f} (target met)"
    elif reward >= 0.7:
        return f"{reward:.3f} (good)"
    elif reward >= 0.5:
        return f"{reward:.3f} (moderate)"
    else:
        return f"{reward:.3f} (low)"


class ObsidianCLI:
    """CLI handler for Obsidian commands."""

    def __init__(self, project_path: Path | None = None):
        self.project_path = project_path or get_project_path()
        self.config = load_config(self.project_path)
        self.state_dir = get_state_dir(self.project_path, self.config)

    def cmd_status(self, args: argparse.Namespace) -> int:
        """Show current session status."""
        print("=" * 60)
        print("OBSIDIAN STATUS")
        print("=" * 60)
        print()

        # Config info
        config_file = find_config_file(self.project_path)
        print(f"Project: {self.project_path}")
        print(f"Config: {config_file or 'Using defaults'}")
        print(f"State dir: {self.state_dir}")
        print()

        # Circuit breaker status
        cb = CircuitBreaker(self.state_dir)
        cb_status = cb.get_status()
        print("-" * 60)
        print("CIRCUIT BREAKER")
        print("-" * 60)
        state = cb_status.get("state", "UNKNOWN")
        state_indicator = {
            "CLOSED": "[OK]",
            "HALF_OPEN": "[WARN]",
            "OPEN": "[BLOCKED]",
        }.get(state, "[?]")
        print(f"State: {state} {state_indicator}")
        print(f"Current loop: {cb_status.get('current_loop', 0)}")
        print(f"Loops since progress: {cb_status.get('consecutive_no_progress', 0)}")
        print(f"Same error count: {cb_status.get('consecutive_same_error', 0)}")
        print(f"Total opens: {cb_status.get('total_opens', 0)}")
        if cb_status.get("reason"):
            print(f"Last reason: {cb_status.get('reason')}")
        print()

        # Session state
        state_file = self.state_dir / "session_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    session_state = json.load(f)
                print("-" * 60)
                print("SESSION STATE")
                print("-" * 60)
                print(f"Attempt count: {session_state.get('attempt_count', 0)}")
                print(f"Best reward: {format_reward(session_state.get('best_reward', 0.0))}")
                print(f"Target: {self.config.success_threshold:.2f}")

                reward_history = session_state.get("reward_history", [])
                if reward_history:
                    print(f"Last 5 rewards: {[f'{r:.3f}' for r in reward_history[-5:]]}")
                print()
            except (json.JSONDecodeError, IOError):
                pass

        # Memory database info
        db_file = self.state_dir / "memory.db"
        if db_file.exists():
            print("-" * 60)
            print("MEMORY")
            print("-" * 60)
            print(f"Database: {db_file}")
            print(f"Size: {db_file.stat().st_size / 1024:.1f} KB")
            print()

        # Log file info
        log_file = self.state_dir / self.config.logging.file
        if log_file.exists():
            print("-" * 60)
            print("LOGS")
            print("-" * 60)
            print(f"Log file: {log_file}")
            print(f"Size: {log_file.stat().st_size / 1024:.1f} KB")
            print()

        print("=" * 60)
        return 0

    def cmd_reset(self, args: argparse.Namespace) -> int:
        """Reset circuit breaker or session state."""
        target = args.target

        if target in ("circuit", "all"):
            cb = CircuitBreaker(self.state_dir)
            cb.reset()
            print("Circuit breaker reset to CLOSED state")

        if target in ("session", "all"):
            state_file = self.state_dir / "session_state.json"
            if state_file.exists():
                state_file.unlink()
                print("Session state cleared")
            else:
                print("No session state to clear")

        if target in ("baseline", "all"):
            baseline_dir = self.state_dir / "baselines"
            if baseline_dir.exists():
                for f in baseline_dir.glob("*.json"):
                    f.unlink()
                print("Baselines cleared")
            else:
                print("No baselines to clear")

        if target == "all":
            # Clear episodes from memory db
            db_file = self.state_dir / "memory.db"
            if db_file.exists():
                import sqlite3
                conn = sqlite3.connect(db_file)
                try:
                    conn.execute("DELETE FROM episodes")
                    conn.commit()
                    print("Episodes cleared from memory")
                except sqlite3.OperationalError:
                    pass
                finally:
                    conn.close()

        return 0

    def cmd_history(self, args: argparse.Namespace) -> int:
        """View episode history."""
        db_file = self.state_dir / "memory.db"
        if not db_file.exists():
            print("No history available (memory database not found)")
            return 1

        import sqlite3
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row

        try:
            # Get episodes
            limit = args.limit or 10
            cursor = conn.execute(
                """
                SELECT id, session_id, attempt_number, timestamp, reward,
                       action_summary, metrics
                FROM episodes
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            episodes = cursor.fetchall()

            if not episodes:
                print("No episodes recorded yet")
                return 0

            print("=" * 60)
            print(f"EPISODE HISTORY (last {len(episodes)})")
            print("=" * 60)
            print()

            for ep in reversed(episodes):  # Show oldest first
                print(f"Attempt #{ep['attempt_number']} | Reward: {format_reward(ep['reward'])}")
                print(f"  Time: {format_timestamp(ep['timestamp'])}")
                if ep["action_summary"]:
                    summary = ep["action_summary"][:80]
                    if len(ep["action_summary"]) > 80:
                        summary += "..."
                    print(f"  Action: {summary}")
                if ep["metrics"]:
                    try:
                        metrics = json.loads(ep["metrics"]) if isinstance(ep["metrics"], str) else ep["metrics"]
                        metrics_str = ", ".join(f"{k}={v:.2f}" for k, v in metrics.items())
                        print(f"  Metrics: {metrics_str}")
                    except (json.JSONDecodeError, TypeError):
                        pass
                print()

        except sqlite3.OperationalError as e:
            print(f"Error reading history: {e}")
            return 1
        finally:
            conn.close()

        return 0

    def cmd_stats(self, args: argparse.Namespace) -> int:
        """Show statistics."""
        db_file = self.state_dir / "memory.db"

        print("=" * 60)
        print("OBSIDIAN STATISTICS")
        print("=" * 60)
        print()

        # Config stats
        print("-" * 60)
        print("CONFIGURATION")
        print("-" * 60)
        print(f"Max attempts: {self.config.max_attempts}")
        print(f"Success threshold: {self.config.success_threshold:.2f}")
        print(f"ICRL enabled: {self.config.icrl.enabled}")
        print(f"Circuit breaker enabled: {self.config.circuit_breaker.enabled}")
        print()

        # Evaluator weights
        print("-" * 60)
        print("EVALUATOR WEIGHTS")
        print("-" * 60)
        if self.config.pytest.enabled:
            print(f"  pytest: {self.config.pytest.weight:.2f}")
        if self.config.coverage.enabled:
            print(f"  coverage: {self.config.coverage.weight:.2f}")
        if self.config.ruff.enabled:
            print(f"  ruff: {self.config.ruff.weight:.2f}")
        if self.config.pyright.enabled:
            print(f"  pyright: {self.config.pyright.weight:.2f}")
        print()

        if not db_file.exists():
            print("No episode data available")
            return 0

        import sqlite3
        conn = sqlite3.connect(db_file)

        try:
            # Episode stats
            cursor = conn.execute("SELECT COUNT(*) FROM episodes")
            total_episodes = cursor.fetchone()[0]

            cursor = conn.execute("SELECT AVG(reward), MIN(reward), MAX(reward) FROM episodes")
            row = cursor.fetchone()
            avg_reward, min_reward, max_reward = row

            cursor = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM episodes"
            )
            total_sessions = cursor.fetchone()[0]

            print("-" * 60)
            print("EPISODE STATISTICS")
            print("-" * 60)
            print(f"Total episodes: {total_episodes}")
            print(f"Total sessions: {total_sessions}")
            if avg_reward is not None:
                print(f"Average reward: {avg_reward:.3f}")
                print(f"Min reward: {min_reward:.3f}")
                print(f"Max reward: {max_reward:.3f}")
            print()

            # Reward distribution
            cursor = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN reward >= 0.9 THEN 1 ELSE 0 END) as excellent,
                    SUM(CASE WHEN reward >= 0.7 AND reward < 0.9 THEN 1 ELSE 0 END) as good,
                    SUM(CASE WHEN reward >= 0.5 AND reward < 0.7 THEN 1 ELSE 0 END) as moderate,
                    SUM(CASE WHEN reward < 0.5 THEN 1 ELSE 0 END) as low
                FROM episodes
                """
            )
            dist = cursor.fetchone()
            if dist and total_episodes > 0:
                print("-" * 60)
                print("REWARD DISTRIBUTION")
                print("-" * 60)
                print(f"  >= 0.9 (target): {dist[0] or 0} ({100*(dist[0] or 0)/total_episodes:.1f}%)")
                print(f"  0.7-0.9 (good): {dist[1] or 0} ({100*(dist[1] or 0)/total_episodes:.1f}%)")
                print(f"  0.5-0.7 (moderate): {dist[2] or 0} ({100*(dist[2] or 0)/total_episodes:.1f}%)")
                print(f"  < 0.5 (low): {dist[3] or 0} ({100*(dist[3] or 0)/total_episodes:.1f}%)")
                print()

        except sqlite3.OperationalError as e:
            print(f"Error reading stats: {e}")
        finally:
            conn.close()

        # Circuit breaker stats
        cb = CircuitBreaker(self.state_dir)
        cb_status = cb.get_status()
        print("-" * 60)
        print("CIRCUIT BREAKER STATS")
        print("-" * 60)
        print(f"Total opens: {cb_status.get('total_opens', 0)}")
        print(f"Current state: {cb_status.get('state', 'UNKNOWN')}")
        print()

        print("=" * 60)
        return 0

    def cmd_config(self, args: argparse.Namespace) -> int:
        """Config subcommand handler."""
        if args.config_action == "validate":
            return self.cmd_config_validate(args)
        elif args.config_action == "show":
            return self.cmd_config_show(args)
        else:
            print(f"Unknown config action: {args.config_action}")
            return 1

    def cmd_config_validate(self, args: argparse.Namespace) -> int:
        """Validate configuration file."""
        config_file = find_config_file(self.project_path)

        print("=" * 60)
        print("CONFIGURATION VALIDATION")
        print("=" * 60)
        print()

        if config_file is None:
            print("No obsidian.yaml found - using defaults")
            print("Status: OK (defaults are valid)")
            return 0

        print(f"Config file: {config_file}")
        print()

        errors = []
        warnings = []

        # Check evaluator weights
        total_weight = 0.0
        enabled_count = 0
        for name, eval_config in [
            ("pytest", self.config.pytest),
            ("coverage", self.config.coverage),
            ("ruff", self.config.ruff),
            ("pyright", self.config.pyright),
        ]:
            if eval_config.enabled:
                total_weight += eval_config.weight
                enabled_count += 1

        if enabled_count > 0 and abs(total_weight - 1.0) > 0.01:
            warnings.append(
                f"Evaluator weights sum to {total_weight:.2f}, should be 1.0"
            )

        if enabled_count == 0:
            errors.append("No evaluators enabled")

        # Check thresholds
        if self.config.success_threshold <= 0 or self.config.success_threshold > 1:
            errors.append(
                f"Invalid success_threshold: {self.config.success_threshold} (must be 0-1)"
            )

        if self.config.max_attempts < 1:
            errors.append(f"Invalid max_attempts: {self.config.max_attempts}")

        # Check ICRL config
        if self.config.icrl.enabled:
            ratio_sum = (
                self.config.icrl.top_k_ratio
                + self.config.icrl.failure_ratio
                + self.config.icrl.diversity_ratio
            )
            if abs(ratio_sum - 1.0) > 0.01:
                warnings.append(
                    f"ICRL ratios sum to {ratio_sum:.2f}, should be 1.0"
                )

        # Check circuit breaker
        if self.config.circuit_breaker.no_progress_threshold < 1:
            errors.append("circuit_breaker.no_progress_threshold must be >= 1")

        # Report results
        if errors:
            print("ERRORS:")
            for err in errors:
                print(f"  - {err}")
            print()

        if warnings:
            print("WARNINGS:")
            for warn in warnings:
                print(f"  - {warn}")
            print()

        if not errors and not warnings:
            print("Status: OK (no issues found)")
        elif errors:
            print("Status: INVALID (fix errors before use)")
            return 1
        else:
            print("Status: VALID (with warnings)")

        return 0

    def cmd_config_show(self, args: argparse.Namespace) -> int:
        """Show current configuration."""
        import yaml

        print("=" * 60)
        print("CURRENT CONFIGURATION")
        print("=" * 60)
        print()

        # Convert config to dict for display
        config_dict = {
            "max_attempts": self.config.max_attempts,
            "success_threshold": self.config.success_threshold,
            "state_dir": self.config.state_dir,
            "evaluator": {
                "pytest": {
                    "enabled": self.config.pytest.enabled,
                    "weight": self.config.pytest.weight,
                    "timeout": self.config.pytest.timeout,
                },
                "coverage": {
                    "enabled": self.config.coverage.enabled,
                    "weight": self.config.coverage.weight,
                    "threshold": self.config.coverage.threshold,
                },
                "ruff": {
                    "enabled": self.config.ruff.enabled,
                    "weight": self.config.ruff.weight,
                },
                "pyright": {
                    "enabled": self.config.pyright.enabled,
                    "weight": self.config.pyright.weight,
                },
            },
            "icrl": {
                "enabled": self.config.icrl.enabled,
                "top_k": self.config.icrl.top_k,
                "max_context_tokens": self.config.icrl.max_context_tokens,
            },
            "circuit_breaker": {
                "enabled": self.config.circuit_breaker.enabled,
                "no_progress_threshold": self.config.circuit_breaker.no_progress_threshold,
                "same_error_threshold": self.config.circuit_breaker.same_error_threshold,
            },
            "logging": {
                "enabled": self.config.logging.enabled,
                "level": self.config.logging.level,
            },
        }

        print(yaml.dump(config_dict, default_flow_style=False, sort_keys=False))
        return 0

    def cmd_test_evaluator(self, args: argparse.Namespace) -> int:
        """Test a single evaluator."""
        evaluator_name = args.evaluator

        print("=" * 60)
        print(f"TESTING EVALUATOR: {evaluator_name}")
        print("=" * 60)
        print()

        # Import evaluators
        from .evaluator import CompositeEvaluator

        try:
            evaluator = CompositeEvaluator.from_config(self.config)

            # Find the specific evaluator
            target_eval = None
            for ev in evaluator.evaluators:
                if ev.name.lower() == evaluator_name.lower():
                    target_eval = ev
                    break

            if target_eval is None:
                print(f"Evaluator '{evaluator_name}' not found or not enabled")
                print(f"Available: {[e.name for e in evaluator.evaluators]}")
                return 1

            print(f"Running {target_eval.name}...")
            print()

            import time
            start = time.time()
            result = target_eval.evaluate(str(self.project_path))
            duration = time.time() - start

            print("-" * 60)
            print("RESULT")
            print("-" * 60)
            print(f"Passed: {result.passed}")
            print(f"Score: {result.score:.3f}")
            print(f"Duration: {duration:.2f}s")

            if result.details:
                print()
                print("Details:")
                for key, value in result.details.items():
                    if isinstance(value, list) and len(value) > 5:
                        print(f"  {key}: [{len(value)} items]")
                    else:
                        print(f"  {key}: {value}")

        except Exception as e:
            print(f"Error running evaluator: {e}")
            return 1

        return 0

    # =========================================================================
    # RESEARCH MODE COMMANDS
    # =========================================================================

    def cmd_research(self, args: argparse.Namespace) -> int:
        """Research subcommand handler."""
        action = getattr(args, "research_action", None)

        if action == "init":
            return self.cmd_research_init(args)
        elif action == "status":
            return self.cmd_research_status(args)
        elif action == "archive":
            return self.cmd_research_archive(args)
        elif action == "export":
            return self.cmd_research_export(args)
        elif action == "reset":
            return self.cmd_research_reset(args)
        else:
            print("Usage: obsidian research <init|status|archive|export|reset>")
            return 1

    def cmd_research_init(self, args: argparse.Namespace) -> int:
        """Initialize a new research problem."""
        template = getattr(args, "template", "custom")
        name = getattr(args, "name", "My Research Problem")
        description = getattr(args, "description", "Describe your problem here")
        output_dir = Path(getattr(args, "output", "."))

        print("=" * 60)
        print("INITIALIZING RESEARCH PROBLEM")
        print("=" * 60)
        print()

        if template not in PROBLEM_TEMPLATES:
            print(f"Unknown template: {template}")
            print(f"Available: {list(PROBLEM_TEMPLATES.keys())}")
            return 1

        # Generate problem.yaml
        problem_content = PROBLEM_TEMPLATES[template].format(
            name=name,
            description=description,
        )

        problem_file = output_dir / "problem.yaml"

        if problem_file.exists() and not getattr(args, "force", False):
            print(f"problem.yaml already exists. Use --force to overwrite.")
            return 1

        output_dir.mkdir(parents=True, exist_ok=True)
        problem_file.write_text(problem_content)
        print(f"Created: {problem_file}")

        # Create tests directory
        tests_dir = output_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "__init__.py").touch()
        print(f"Created: {tests_dir}/")

        # Create placeholder files
        solution_file = output_dir / "solution.py"
        if not solution_file.exists():
            solution_file.write_text('"""Solution placeholder - Claude will overwrite this."""\n\ndef solve(input_data):\n    pass\n')
            print(f"Created: {solution_file}")

        benchmark_file = output_dir / "benchmark.py"
        if not benchmark_file.exists():
            benchmark_file.write_text('''#!/usr/bin/env python3
"""Benchmark script - customize for your problem."""

import json
import sys

def benchmark(solution_path):
    """Run benchmark and return score."""
    # TODO: Implement your benchmark
    return {"score": 0.5, "details": {}}

if __name__ == "__main__":
    result = benchmark(sys.argv[1] if len(sys.argv) > 1 else "solution.py")
    print(json.dumps(result))
''')
            print(f"Created: {benchmark_file}")

        # Create hooks directory
        hooks_dir = output_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)

        # Get the obsidian installation path
        import obsidian
        obsidian_path = Path(obsidian.__file__).parent.parent.parent

        hooks_content = {
            "hooks": {
                "Stop": [{
                    "hooks": [{
                        "type": "command",
                        "command": f"python3 {obsidian_path}/scripts/research_hook.py",
                        "timeout": 300
                    }]
                }]
            }
        }

        hooks_file = hooks_dir / "hooks.json"
        hooks_file.write_text(json.dumps(hooks_content, indent=2))
        print(f"Created: {hooks_file}")

        print()
        print("=" * 60)
        print("NEXT STEPS")
        print("=" * 60)
        print()
        print("1. Edit problem.yaml to define your problem")
        print("2. Create tests in tests/ directory")
        print("3. Implement benchmark.py")
        print("4. Start Claude Code in this directory")
        print("5. Claude will iterate until target achieved!")
        print()

        return 0

    def cmd_research_status(self, args: argparse.Namespace) -> int:
        """Show research mode status."""
        print("=" * 60)
        print("RESEARCH MODE STATUS")
        print("=" * 60)
        print()

        # Check for problem.yaml
        problem_file = self.project_path / "problem.yaml"
        if not problem_file.exists():
            print("No problem.yaml found")
            print("Run 'obsidian research init' to create one")
            return 1

        try:
            from .research.problem import load_problem, validate_problem
            from .research.archive import SolutionArchive

            problem = load_problem(problem_file)
            errors = validate_problem(problem)

            print(f"Problem: {problem.name}")
            print(f"Description: {problem.description[:100]}...")
            print()

            if errors:
                print("VALIDATION ERRORS:")
                for err in errors:
                    print(f"  - {err}")
                return 1

            # Load research state
            state_file = self.state_dir / "research_state.json"
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)

                print("-" * 60)
                print("PROGRESS")
                print("-" * 60)
                print(f"Iteration: {state.get('iteration', 0)} / {problem.loop.max_iterations}")
                print(f"Best score: {state.get('best_score', 0):.4f}")

                target = problem.benchmark.target_score
                if target:
                    print(f"Target: {target}")
                    progress = min(1.0, state.get('best_score', 0) / target)
                    print(f"Progress: {progress:.1%}")
            else:
                print("No research session started yet")

            # Load archive
            archive_db = self.state_dir / "archive.db"
            if archive_db.exists():
                archive = SolutionArchive(problem.archive, db_path=archive_db)
                stats = archive.get_stats()

                print()
                print("-" * 60)
                print("ARCHIVE")
                print("-" * 60)
                print(f"Total solutions: {stats['total_solutions']}")
                print(f"Niches explored: {stats['total_niches']}")
                print(f"Best score: {stats['best_score']:.4f}")
                print(f"Average score: {stats['avg_score']:.4f}")
                print(f"Coverage: {stats.get('coverage', 0):.1%}")

        except Exception as e:
            print(f"Error loading research status: {e}")
            return 1

        print()
        return 0

    def cmd_research_archive(self, args: argparse.Namespace) -> int:
        """Show solution archive."""
        print("=" * 60)
        print("SOLUTION ARCHIVE")
        print("=" * 60)
        print()

        problem_file = self.project_path / "problem.yaml"
        if not problem_file.exists():
            print("No problem.yaml found")
            return 1

        try:
            from .research.problem import load_problem
            from .research.archive import SolutionArchive

            problem = load_problem(problem_file)
            archive_db = self.state_dir / "archive.db"

            if not archive_db.exists():
                print("No archive found. Start a research session first.")
                return 1

            archive = SolutionArchive(problem.archive, db_path=archive_db)

            limit = getattr(args, "limit", 10)
            solutions = archive.get_top_k(limit)

            if not solutions:
                print("No solutions in archive")
                return 0

            for i, sol in enumerate(solutions, 1):
                niche_str = ", ".join(f"{k}={v}" for k, v in sol.niche_values.items())
                print(f"{i}. [{sol.id}] score={sol.score:.4f}")
                print(f"   Niche: {niche_str}")
                print(f"   Operation: {sol.operation}")
                print(f"   Iteration: {sol.iteration}")
                print()

        except Exception as e:
            print(f"Error loading archive: {e}")
            return 1

        return 0

    def cmd_research_export(self, args: argparse.Namespace) -> int:
        """Export best solution(s)."""
        print("=" * 60)
        print("EXPORTING SOLUTIONS")
        print("=" * 60)
        print()

        problem_file = self.project_path / "problem.yaml"
        if not problem_file.exists():
            print("No problem.yaml found")
            return 1

        try:
            from .research.problem import load_problem
            from .research.archive import SolutionArchive

            problem = load_problem(problem_file)
            archive_db = self.state_dir / "archive.db"

            if not archive_db.exists():
                print("No archive found")
                return 1

            archive = SolutionArchive(problem.archive, db_path=archive_db)

            output_dir = Path(getattr(args, "output", "exported_solutions"))
            output_dir.mkdir(parents=True, exist_ok=True)

            count = getattr(args, "count", 1)
            solutions = archive.get_top_k(count)

            for i, sol in enumerate(solutions, 1):
                filename = f"solution_{i}_score_{sol.score:.4f}.py"
                filepath = output_dir / filename
                filepath.write_text(sol.code)
                print(f"Exported: {filepath}")

            print()
            print(f"Exported {len(solutions)} solution(s) to {output_dir}")

        except Exception as e:
            print(f"Error exporting: {e}")
            return 1

        return 0

    def cmd_research_reset(self, args: argparse.Namespace) -> int:
        """Reset research state."""
        print("=" * 60)
        print("RESETTING RESEARCH STATE")
        print("=" * 60)
        print()

        state_file = self.state_dir / "research_state.json"
        archive_db = self.state_dir / "archive.db"

        target = getattr(args, "target", "state")

        if target in ["state", "all"]:
            if state_file.exists():
                state_file.unlink()
                print("Deleted: research_state.json")

        if target in ["archive", "all"]:
            if archive_db.exists():
                archive_db.unlink()
                print("Deleted: archive.db")

        print()
        print("Reset complete")
        return 0


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="obsidian",
        description="Obsidian - Obsessive learning loop plugin for Claude Code",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show current session status",
    )

    # reset command
    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset circuit breaker or session state",
    )
    reset_parser.add_argument(
        "target",
        choices=["circuit", "session", "baseline", "all"],
        help="What to reset",
    )

    # history command
    history_parser = subparsers.add_parser(
        "history",
        help="View episode history",
    )
    history_parser.add_argument(
        "-n", "--limit",
        type=int,
        default=10,
        help="Number of episodes to show (default: 10)",
    )

    # stats command
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show statistics",
    )

    # config command
    config_parser = subparsers.add_parser(
        "config",
        help="Configuration management",
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_action",
        help="Config actions",
    )
    config_subparsers.add_parser("validate", help="Validate configuration")
    config_subparsers.add_parser("show", help="Show current configuration")

    # test-evaluator command
    test_parser = subparsers.add_parser(
        "test-evaluator",
        help="Test a single evaluator",
    )
    test_parser.add_argument(
        "evaluator",
        help="Name of evaluator to test (pytest, coverage, ruff, pyright)",
    )

    # research command
    research_parser = subparsers.add_parser(
        "research",
        help="Research mode commands for algorithm discovery",
    )
    research_subparsers = research_parser.add_subparsers(
        dest="research_action",
        help="Research actions",
    )

    # research init
    research_init = research_subparsers.add_parser(
        "init",
        help="Initialize a new research problem",
    )
    research_init.add_argument(
        "--template", "-t",
        choices=["algorithm", "ml_model", "optimization", "custom"],
        default="algorithm",
        help="Problem template to use",
    )
    research_init.add_argument(
        "--name", "-n",
        default="My Research Problem",
        help="Problem name",
    )
    research_init.add_argument(
        "--description", "-d",
        default="Describe your problem here",
        help="Problem description",
    )
    research_init.add_argument(
        "--output", "-o",
        default=".",
        help="Output directory",
    )
    research_init.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing files",
    )

    # research status
    research_subparsers.add_parser(
        "status",
        help="Show research progress",
    )

    # research archive
    research_archive = research_subparsers.add_parser(
        "archive",
        help="Show solution archive",
    )
    research_archive.add_argument(
        "-n", "--limit",
        type=int,
        default=10,
        help="Number of solutions to show",
    )

    # research export
    research_export = research_subparsers.add_parser(
        "export",
        help="Export best solutions",
    )
    research_export.add_argument(
        "--output", "-o",
        default="exported_solutions",
        help="Output directory",
    )
    research_export.add_argument(
        "--count", "-c",
        type=int,
        default=1,
        help="Number of solutions to export",
    )

    # research reset
    research_reset = research_subparsers.add_parser(
        "reset",
        help="Reset research state",
    )
    research_reset.add_argument(
        "target",
        choices=["state", "archive", "all"],
        nargs="?",
        default="state",
        help="What to reset",
    )

    return parser


def main(args: list[str] | None = None) -> int:
    """Main entry point for CLI."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if parsed_args.command is None:
        parser.print_help()
        return 0

    cli = ObsidianCLI()

    command_handlers = {
        "status": cli.cmd_status,
        "reset": cli.cmd_reset,
        "history": cli.cmd_history,
        "stats": cli.cmd_stats,
        "config": cli.cmd_config,
        "test-evaluator": cli.cmd_test_evaluator,
        "research": cli.cmd_research,
    }

    handler = command_handlers.get(parsed_args.command)
    if handler:
        return handler(parsed_args)
    else:
        print(f"Unknown command: {parsed_args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
