"""Coverage.py metric evaluator."""

import json
import re
import time
from pathlib import Path

from .base import EvalResult, MetricCollector


class CoverageEvaluator(MetricCollector):
    """Collects code coverage metrics from pytest-cov."""

    def __init__(
        self,
        timeout: int = 180,
        source: str = "src",
        threshold: float = 70.0,
    ):
        super().__init__(name="coverage", timeout=timeout)
        self.source = source
        self.threshold = threshold

    def collect(self, project_path: str) -> EvalResult:
        """Run pytest with coverage and collect results."""
        start_time = time.perf_counter()

        project = Path(project_path)
        coverage_json = project / "coverage.json"

        # Clean up old coverage file
        if coverage_json.exists():
            coverage_json.unlink()

        try:
            # Check if source directory exists
            source_path = project / self.source
            if not source_path.exists():
                # Try common alternatives
                for alt in [".", "lib", "app"]:
                    alt_path = project / alt
                    if alt_path.exists() and (alt_path / "__init__.py").exists():
                        self.source = alt
                        break

            # Run pytest with coverage
            cmd = [
                "pytest",
                f"--cov={self.source}",
                "--cov-report=json",
                "-q",
                "--tb=no",
            ]

            stdout, stderr, exit_code = self.run_command(cmd, project_path)
            execution_time = (time.perf_counter() - start_time) * 1000

            # Check for coverage plugin not installed
            if "unrecognized arguments: --cov" in stderr:
                return EvalResult(
                    name=self.name,
                    score=0.0,
                    passed=False,
                    error="pytest-cov not installed",
                    execution_time_ms=execution_time,
                )

            # Parse coverage.json
            result = self._parse_coverage_json(coverage_json)
            if result is None:
                # Fallback to parsing stdout
                result = self._parse_stdout(stdout)

            coverage_percent = result.get("percent", 0.0)
            score = coverage_percent / 100.0  # Normalize to 0-1

            return EvalResult(
                name=self.name,
                score=score,
                passed=coverage_percent >= self.threshold,
                raw_value=coverage_percent,
                details={
                    "percent": coverage_percent,
                    "covered_lines": result.get("covered_lines", 0),
                    "total_lines": result.get("total_lines", 0),
                    "missing_lines": result.get("missing_lines", 0),
                    "files": result.get("files", {}),
                    "threshold": self.threshold,
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
            # Clean up coverage.json
            try:
                if coverage_json.exists():
                    coverage_json.unlink()
            except Exception:
                pass

    def _parse_coverage_json(self, json_path: Path) -> dict | None:
        """Parse coverage.json report."""
        try:
            if not json_path.exists():
                return None

            with open(json_path) as f:
                report = json.load(f)

            totals = report.get("totals", {})

            # Get per-file breakdown
            files = {}
            for filepath, data in report.get("files", {}).items():
                summary = data.get("summary", {})
                files[filepath] = {
                    "covered": summary.get("covered_lines", 0),
                    "missing": summary.get("missing_lines", 0),
                    "percent": summary.get("percent_covered", 0),
                }

            return {
                "percent": totals.get("percent_covered", 0.0),
                "covered_lines": totals.get("covered_lines", 0),
                "total_lines": totals.get("num_statements", 0),
                "missing_lines": totals.get("missing_lines", 0),
                "files": files,
            }

        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return None

    def _parse_stdout(self, stdout: str) -> dict:
        """Fallback: parse coverage from stdout."""
        # Look for pattern like "TOTAL    100    20    80%"
        match = re.search(r"TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", stdout)
        if match:
            total = int(match.group(1))
            missing = int(match.group(2))
            percent = int(match.group(3))
            return {
                "percent": float(percent),
                "total_lines": total,
                "missing_lines": missing,
                "covered_lines": total - missing,
                "files": {},
            }

        # Try simpler pattern
        match = re.search(r"(\d+)%", stdout)
        if match:
            return {"percent": float(match.group(1)), "files": {}}

        return {"percent": 0.0, "files": {}}


def format_coverage_details(details: dict, show_files: int = 5) -> str:
    """Format coverage details for feedback message."""
    lines = [f"Coverage: {details.get('percent', 0):.1f}% (threshold: {details.get('threshold', 70)}%)"]

    files = details.get("files", {})
    if files:
        # Sort by coverage percentage (lowest first)
        sorted_files = sorted(files.items(), key=lambda x: x[1].get("percent", 0))

        if sorted_files:
            lines.append("Low coverage files:")
            for filepath, data in sorted_files[:show_files]:
                pct = data.get("percent", 0)
                missing = data.get("missing", 0)
                if pct < 100:
                    lines.append(f"  - {filepath}: {pct:.0f}% ({missing} lines missing)")

            if len(sorted_files) > show_files:
                lines.append(f"  ... and {len(sorted_files) - show_files} more files")

    return "\n".join(lines)
