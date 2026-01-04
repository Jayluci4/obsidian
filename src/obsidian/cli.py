"""CLI commands for Obsidian plugin management."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_config, get_state_dir, find_config_file, ObsidianConfig
from .strategy.circuit_breaker import CircuitBreaker, CircuitState


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
    }

    handler = command_handlers.get(parsed_args.command)
    if handler:
        return handler(parsed_args)
    else:
        print(f"Unknown command: {parsed_args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
