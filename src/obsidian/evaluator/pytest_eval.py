"""Pytest metric evaluator."""

import json
import re
import tempfile
import time
from pathlib import Path

from .base import EvalResult, MetricCollector


class PytestEvaluator(MetricCollector):
    """Collects test pass/fail metrics from pytest."""

    def __init__(self, timeout: int = 120, args: list[str] | None = None):
        super().__init__(name="pytest", timeout=timeout)
        self.args = args or ["--tb=short", "-q"]

    def collect(self, project_path: str) -> EvalResult:
        """Run pytest and collect results."""
        start_time = time.perf_counter()

        # Create temp file for JSON report
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as tmp:
            report_path = tmp.name

        try:
            # Try with json-report first
            cmd = [
                "pytest",
                "--json-report",
                f"--json-report-file={report_path}",
                *self.args,
            ]

            stdout, stderr, exit_code = self.run_command(cmd, project_path)

            # Check if json-report plugin is not available
            if "unrecognized arguments: --json-report" in stderr:
                # Fallback: run without json-report
                cmd = ["pytest", *self.args]
                stdout, stderr, exit_code = self.run_command(cmd, project_path)
                result = self._parse_stdout(stdout, stderr, exit_code)
            else:
                # Try to parse JSON report first
                result = self._parse_json_report(report_path)
                if result is None:
                    # Fallback to parsing stdout
                    result = self._parse_stdout(stdout, stderr, exit_code)

            execution_time = (time.perf_counter() - start_time) * 1000

            passed = result["passed"]
            failed = result["failed"]
            errors = result["errors"]
            skipped = result["skipped"]
            total = passed + failed + errors

            # Compute score: passed / total
            if total == 0:
                # No tests found - check if this is an error
                if exit_code != 0 and exit_code != 5:  # 5 = no tests collected
                    return EvalResult(
                        name=self.name,
                        score=0.0,
                        passed=False,
                        raw_value=(0, 0),
                        details={"error": stderr or "Unknown error"},
                        error=stderr[:500] if stderr else "Failed to run pytest",
                        execution_time_ms=execution_time,
                    )
                # No tests - consider it neutral
                return EvalResult(
                    name=self.name,
                    score=1.0,
                    passed=True,
                    raw_value=(0, 0),
                    details={"message": "No tests found"},
                    execution_time_ms=execution_time,
                )

            score = passed / total

            return EvalResult(
                name=self.name,
                score=score,
                passed=failed == 0 and errors == 0,
                raw_value=(passed, total),
                details={
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "skipped": skipped,
                    "total": total,
                    "failures": result.get("failure_details", []),
                },
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            return EvalResult(
                name=self.name,
                score=0.0,
                passed=False,
                error=str(e),
                execution_time_ms=execution_time,
            )

        finally:
            # Clean up temp file
            try:
                Path(report_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _parse_json_report(self, report_path: str) -> dict | None:
        """Parse pytest-json-report output."""
        try:
            path = Path(report_path)
            if not path.exists():
                return None

            with open(path) as f:
                report = json.load(f)

            summary = report.get("summary", {})

            # Extract failure details
            failure_details = []
            for test in report.get("tests", []):
                if test.get("outcome") in ("failed", "error"):
                    nodeid = test.get("nodeid", "unknown")
                    call = test.get("call", {})
                    longrepr = call.get("longrepr", "")
                    # Truncate long error messages
                    if len(longrepr) > 500:
                        longrepr = longrepr[:500] + "..."
                    failure_details.append({"test": nodeid, "message": longrepr})

            return {
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "errors": summary.get("error", 0),
                "skipped": summary.get("skipped", 0),
                "failure_details": failure_details[:10],  # Limit to 10
            }

        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return None

    def _parse_stdout(
        self, stdout: str, stderr: str, exit_code: int
    ) -> dict:
        """Fallback: parse pytest stdout for results."""
        passed = 0
        failed = 0
        errors = 0
        skipped = 0

        # Parse patterns like "5 passed, 2 failed, 1 error"
        for pattern, key in [
            (r"(\d+)\s+passed", "passed"),
            (r"(\d+)\s+failed", "failed"),
            (r"(\d+)\s+error", "errors"),
            (r"(\d+)\s+skipped", "skipped"),
        ]:
            match = re.search(pattern, stdout)
            if match:
                if key == "passed":
                    passed = int(match.group(1))
                elif key == "failed":
                    failed = int(match.group(1))
                elif key == "errors":
                    errors = int(match.group(1))
                elif key == "skipped":
                    skipped = int(match.group(1))

        # Extract failure messages from stderr/stdout
        failure_details = []
        failure_pattern = r"FAILED\s+(\S+)"
        for match in re.finditer(failure_pattern, stdout):
            failure_details.append({"test": match.group(1), "message": ""})

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "failure_details": failure_details[:10],
        }


def format_pytest_failures(details: dict, max_show: int = 5) -> str:
    """Format pytest failures for feedback message."""
    failures = details.get("failures", [])
    if not failures:
        failures = details.get("failure_details", [])

    if not failures:
        return ""

    lines = ["Failed tests:"]
    for i, failure in enumerate(failures[:max_show]):
        test = failure.get("test", "unknown")
        msg = failure.get("message", "")
        lines.append(f"  - {test}")
        if msg:
            # First line of message only
            first_line = msg.split("\n")[0][:100]
            lines.append(f"    {first_line}")

    if len(failures) > max_show:
        lines.append(f"  ... and {len(failures) - max_show} more")

    return "\n".join(lines)
