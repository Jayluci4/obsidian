"""
Response Analyzer for detecting completion signals and loop patterns.

Inspired by Ralph Claude Code's response_analyzer.sh.
Detects:
- Completion keywords ("done", "complete", "finished")
- Test-only loops (tests running but no implementation)
- No-work patterns ("nothing to do", "no changes")
- Stuck patterns (repeating same errors)
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoopType(Enum):
    """Classification of loop behavior."""

    IMPLEMENTATION = "implementation"  # Writing new code
    TEST_ONLY = "test_only"  # Only running tests
    REFACTORING = "refactoring"  # Restructuring code
    DEBUGGING = "debugging"  # Fixing issues
    NO_WORK = "no_work"  # Nothing to do
    STUCK = "stuck"  # Repeating same errors


@dataclass
class ResponseAnalysis:
    """Result of analyzing Claude's response."""

    has_completion_signal: bool = False
    loop_type: LoopType = LoopType.IMPLEMENTATION
    confidence_score: int = 0  # 0-100
    exit_signal: bool = False
    work_summary: str = ""
    error_hash: str = ""
    is_stuck: bool = False
    details: dict[str, Any] = field(default_factory=dict)


# Completion keywords that suggest task is done
COMPLETION_KEYWORDS = [
    "done",
    "complete",
    "finished",
    "all tasks complete",
    "project complete",
    "ready for review",
    "implementation complete",
    "all tests pass",
    "successfully implemented",
]

# Patterns indicating test-only activity
TEST_PATTERNS = [
    r"\bpytest\b",
    r"\bnpm test\b",
    r"\bjest\b",
    r"\bcargo test\b",
    r"\bgo test\b",
    r"\brunning tests\b",
    r"\btest results\b",
    r"\btests passed\b",
    r"\btests failed\b",
]

# Patterns indicating implementation activity
IMPLEMENTATION_PATTERNS = [
    r"\bimplementing\b",
    r"\bcreating\b",
    r"\bwriting\b",
    r"\badding\b",
    r"\bdef \w+\(",
    r"\bclass \w+",
    r"\bfunction\b",
    r"\bnew file\b",
    r"\bwrote to\b",
]

# Patterns indicating no work needed
NO_WORK_PATTERNS = [
    "nothing to do",
    "no changes needed",
    "already implemented",
    "up to date",
    "no modifications required",
    "looks good",
    "no issues found",
]

# Error patterns for stuck detection
ERROR_PATTERNS = [
    r"^Error:",
    r"^ERROR:",
    r"^error:",
    r"\]: error",
    r"Error occurred",
    r"failed with error",
    r"Exception",
    r"Fatal",
    r"FATAL",
    r"Traceback",
    r"SyntaxError",
    r"TypeError",
    r"ValueError",
    r"ImportError",
]


class ResponseAnalyzer:
    """
    Analyzes Claude's response output for loop patterns.

    Used to detect:
    - When Claude thinks it's done (completion signals)
    - When it's stuck in test-only loops
    - When it's repeating the same errors
    """

    def __init__(
        self,
        completion_threshold: int = 40,  # Confidence threshold for exit signal
        stuck_error_count: int = 5,  # Errors to consider stuck
    ):
        self.completion_threshold = completion_threshold
        self.stuck_error_count = stuck_error_count
        self._last_error_hash: str = ""
        self._consecutive_same_errors: int = 0

    def analyze(
        self,
        output: str,
        files_changed: int = 0,
        previous_output: str | None = None,
    ) -> ResponseAnalysis:
        """
        Analyze Claude's response output.

        Args:
            output: The response text to analyze
            files_changed: Number of files modified (from git diff)
            previous_output: Previous response for comparison

        Returns:
            ResponseAnalysis with detection results
        """
        analysis = ResponseAnalysis()

        if not output:
            analysis.work_summary = "Empty output"
            return analysis

        output_lower = output.lower()
        confidence = 0

        # 1. Check for completion keywords
        for keyword in COMPLETION_KEYWORDS:
            if keyword.lower() in output_lower:
                analysis.has_completion_signal = True
                confidence += 10
                break

        # 2. Detect loop type
        test_matches = sum(
            1 for pattern in TEST_PATTERNS if re.search(pattern, output, re.IGNORECASE)
        )
        impl_matches = sum(
            1 for pattern in IMPLEMENTATION_PATTERNS
            if re.search(pattern, output, re.IGNORECASE)
        )

        if test_matches > 0 and impl_matches == 0:
            analysis.loop_type = LoopType.TEST_ONLY
            analysis.work_summary = "Test execution only, no implementation"
        elif impl_matches > test_matches:
            analysis.loop_type = LoopType.IMPLEMENTATION
            analysis.work_summary = "Implementation in progress"
        elif test_matches > impl_matches:
            analysis.loop_type = LoopType.DEBUGGING
            analysis.work_summary = "Debugging/testing"

        # 3. Check for no-work patterns
        for pattern in NO_WORK_PATTERNS:
            if pattern.lower() in output_lower:
                analysis.has_completion_signal = True
                analysis.loop_type = LoopType.NO_WORK
                analysis.work_summary = "No work remaining"
                confidence += 15
                break

        # 4. Detect errors and compute hash
        errors = self._extract_errors(output)
        if errors:
            analysis.error_hash = self._hash_errors(errors)
            analysis.details["error_count"] = len(errors)
            analysis.details["errors"] = errors[:5]  # First 5 for reference

            # Check for stuck pattern
            if analysis.error_hash == self._last_error_hash:
                self._consecutive_same_errors += 1
            else:
                self._consecutive_same_errors = 1
                self._last_error_hash = analysis.error_hash

            if self._consecutive_same_errors >= 3:
                analysis.is_stuck = True
                analysis.loop_type = LoopType.STUCK
                analysis.work_summary = "Stuck on same errors"

            if len(errors) > self.stuck_error_count:
                analysis.is_stuck = True

        # 5. Check file changes
        if files_changed > 0:
            confidence += 20
            analysis.details["files_changed"] = files_changed
        else:
            analysis.details["files_changed"] = 0

        # 6. Output length comparison
        if previous_output:
            length_ratio = len(output) / max(len(previous_output), 1)
            if length_ratio < 0.5:
                # Output is <50% of previous - possible completion
                confidence += 10
                analysis.details["output_declined"] = True

        # 7. Determine exit signal
        analysis.confidence_score = min(confidence, 100)
        if confidence >= self.completion_threshold or analysis.has_completion_signal:
            analysis.exit_signal = True

        return analysis

    def _extract_errors(self, output: str) -> list[str]:
        """Extract error lines from output."""
        errors = []
        for line in output.split("\n"):
            # Skip JSON field patterns like "is_error": false
            if re.search(r'"[^"]*error[^"]*":', line, re.IGNORECASE):
                continue

            for pattern in ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(line.strip()[:200])  # Limit line length
                    break

        return errors

    def _hash_errors(self, errors: list[str]) -> str:
        """Create hash of error messages for comparison."""
        # Normalize and sort for consistent hashing
        normalized = sorted(set(e.lower().strip() for e in errors))
        content = "\n".join(normalized)
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def reset_stuck_tracking(self) -> None:
        """Reset stuck detection state."""
        self._last_error_hash = ""
        self._consecutive_same_errors = 0


def analyze_response(
    output: str,
    files_changed: int = 0,
    previous_output: str | None = None,
) -> ResponseAnalysis:
    """Convenience function for one-off analysis."""
    analyzer = ResponseAnalyzer()
    return analyzer.analyze(output, files_changed, previous_output)


def detect_completion(output: str) -> bool:
    """Quick check for completion signals."""
    output_lower = output.lower()
    return any(kw.lower() in output_lower for kw in COMPLETION_KEYWORDS)


def is_test_only_output(output: str) -> bool:
    """Check if output shows only test activity."""
    test_matches = sum(
        1 for pattern in TEST_PATTERNS if re.search(pattern, output, re.IGNORECASE)
    )
    impl_matches = sum(
        1 for pattern in IMPLEMENTATION_PATTERNS
        if re.search(pattern, output, re.IGNORECASE)
    )
    return test_matches > 0 and impl_matches == 0
