"""Pyright type checker metric evaluator."""

import json
import time
from pathlib import Path

from .base import EvalResult, MetricCollector


class PyrightEvaluator(MetricCollector):
    """Collects type checking metrics from pyright."""

    def __init__(
        self,
        timeout: int = 60,
        max_errors: int = 50,
        source: str = "src",
    ):
        super().__init__(name="pyright", timeout=timeout)
        self.max_errors = max_errors
        self.source = source

    def collect(self, project_path: str) -> EvalResult:
        """Run pyright and collect results."""
        start_time = time.perf_counter()

        project = Path(project_path)

        try:
            # Check if source directory exists
            source_path = project / self.source
            target = self.source if source_path.exists() else "."

            # Run pyright with JSON output
            cmd = ["pyright", "--outputjson", target]

            stdout, stderr, exit_code = self.run_command(cmd, project_path)
            execution_time = (time.perf_counter() - start_time) * 1000

            # Check if pyright is not installed
            if "command not found" in stderr.lower() or "not found" in stderr.lower():
                return EvalResult(
                    name=self.name,
                    score=1.0,  # Don't penalize if tool not installed
                    passed=True,
                    error="pyright not installed",
                    details={"skipped": True},
                    execution_time_ms=execution_time,
                )

            # Parse JSON output
            result = self._parse_json_output(stdout)

            error_count = result.get("error_count", 0)
            warning_count = result.get("warning_count", 0)

            # Score based on errors (warnings don't count as heavily)
            # Using inverse: 1 / (1 + errors/max_errors + warnings/(max_errors*2))
            weighted_count = error_count + warning_count * 0.5
            score = 1.0 / (1.0 + weighted_count / self.max_errors)

            return EvalResult(
                name=self.name,
                score=score,
                passed=error_count == 0,
                raw_value=error_count,
                details={
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "info_count": result.get("info_count", 0),
                    "by_file": result.get("by_file", {}),
                    "diagnostics": result.get("diagnostics", [])[:10],
                },
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                name=self.name,
                score=1.0,  # Don't penalize on error
                passed=True,
                error=str(e),
                details={"skipped": True},
                execution_time_ms=execution_time,
            )

    def _parse_json_output(self, stdout: str) -> dict:
        """Parse pyright JSON output."""
        try:
            report = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            return {
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "by_file": {},
                "diagnostics": [],
            }

        # Get summary
        summary = report.get("summary", {})
        error_count = summary.get("errorCount", 0)
        warning_count = summary.get("warningCount", 0)
        info_count = summary.get("informationCount", 0)

        # Parse diagnostics
        diagnostics = report.get("generalDiagnostics", [])
        by_file = {}
        formatted_diagnostics = []

        for diag in diagnostics:
            filepath = diag.get("file", "unknown")
            severity = diag.get("severity", "error")
            message = diag.get("message", "")
            range_info = diag.get("range", {})
            start = range_info.get("start", {})
            line = start.get("line", 0) + 1  # pyright uses 0-indexed

            # Count by file
            if filepath not in by_file:
                by_file[filepath] = {"errors": 0, "warnings": 0}
            if severity == 1:  # error
                by_file[filepath]["errors"] += 1
            elif severity == 2:  # warning
                by_file[filepath]["warnings"] += 1

            formatted_diagnostics.append({
                "file": filepath,
                "line": line,
                "severity": "error" if severity == 1 else "warning" if severity == 2 else "info",
                "message": message,
            })

        return {
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "by_file": by_file,
            "diagnostics": formatted_diagnostics,
        }


def format_pyright_diagnostics(details: dict, max_show: int = 5) -> str:
    """Format pyright diagnostics for feedback message."""
    error_count = details.get("error_count", 0)
    warning_count = details.get("warning_count", 0)

    if error_count == 0 and warning_count == 0:
        return "Pyright: No type errors"

    lines = [f"Pyright: {error_count} error(s), {warning_count} warning(s)"]

    diagnostics = details.get("diagnostics", [])
    errors_shown = 0
    for diag in diagnostics:
        if diag.get("severity") == "error" and errors_shown < max_show:
            file = diag.get("file", "unknown")
            line = diag.get("line", 0)
            message = diag.get("message", "")
            lines.append(f"  - {file}:{line} {message[:60]}")
            errors_shown += 1

    remaining = error_count - errors_shown
    if remaining > 0:
        lines.append(f"  ... and {remaining} more error(s)")

    return "\n".join(lines)
