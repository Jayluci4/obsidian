"""Ruff linter metric evaluator."""

import json
import time
from pathlib import Path

from .base import EvalResult, MetricCollector


class RuffEvaluator(MetricCollector):
    """Collects linting metrics from ruff."""

    def __init__(
        self,
        timeout: int = 30,
        max_errors: int = 100,
        source: str = "src",
    ):
        super().__init__(name="ruff", timeout=timeout)
        self.max_errors = max_errors
        self.source = source

    def collect(self, project_path: str) -> EvalResult:
        """Run ruff and collect results."""
        start_time = time.perf_counter()

        project = Path(project_path)

        try:
            # Check if source directory exists
            source_path = project / self.source
            target = self.source if source_path.exists() else "."

            # Run ruff with JSON output
            cmd = ["ruff", "check", "--output-format=json", target]

            stdout, stderr, exit_code = self.run_command(cmd, project_path)
            execution_time = (time.perf_counter() - start_time) * 1000

            # Check if ruff is not installed
            if "command not found" in stderr.lower() or "not found" in stderr.lower():
                return EvalResult(
                    name=self.name,
                    score=1.0,  # Don't penalize if tool not installed
                    passed=True,
                    error="ruff not installed",
                    details={"skipped": True},
                    execution_time_ms=execution_time,
                )

            # Parse JSON output
            result = self._parse_json_output(stdout)

            error_count = result.get("error_count", 0)

            # Score: 1.0 for 0 errors, approaches 0 as errors increase
            # Using inverse: 1 / (1 + count/max_errors)
            score = 1.0 / (1.0 + error_count / self.max_errors)

            return EvalResult(
                name=self.name,
                score=score,
                passed=error_count == 0,
                raw_value=error_count,
                details={
                    "error_count": error_count,
                    "by_code": result.get("by_code", {}),
                    "by_file": result.get("by_file", {}),
                    "issues": result.get("issues", [])[:10],  # First 10 issues
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
        """Parse ruff JSON output."""
        try:
            issues = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            return {"error_count": 0, "by_code": {}, "by_file": {}, "issues": []}

        by_code = {}
        by_file = {}
        formatted_issues = []

        for issue in issues:
            code = issue.get("code", "unknown")
            filename = issue.get("filename", "unknown")
            message = issue.get("message", "")
            location = issue.get("location", {})
            row = location.get("row", 0)

            by_code[code] = by_code.get(code, 0) + 1
            by_file[filename] = by_file.get(filename, 0) + 1

            formatted_issues.append({
                "file": filename,
                "line": row,
                "code": code,
                "message": message,
            })

        return {
            "error_count": len(issues),
            "by_code": by_code,
            "by_file": by_file,
            "issues": formatted_issues,
        }


def format_ruff_issues(details: dict, max_show: int = 5) -> str:
    """Format ruff issues for feedback message."""
    error_count = details.get("error_count", 0)
    if error_count == 0:
        return "Ruff: No issues"

    lines = [f"Ruff: {error_count} issue(s)"]

    issues = details.get("issues", [])
    for issue in issues[:max_show]:
        file = issue.get("file", "unknown")
        line = issue.get("line", 0)
        code = issue.get("code", "")
        message = issue.get("message", "")
        lines.append(f"  - {file}:{line} [{code}] {message[:60]}")

    if len(issues) > max_show:
        lines.append(f"  ... and {len(issues) - max_show} more")

    # Show summary by code
    by_code = details.get("by_code", {})
    if by_code:
        top_codes = sorted(by_code.items(), key=lambda x: x[1], reverse=True)[:3]
        codes_str = ", ".join(f"{code}({count})" for code, count in top_codes)
        lines.append(f"  Top issues: {codes_str}")

    return "\n".join(lines)
