"""
Circuit Breaker Pattern for preventing runaway loops.

Based on Michael Nygard's "Release It!" pattern and Ralph Claude Code implementation.
Prevents infinite loops by detecting stagnation and allowing recovery monitoring.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"  # Normal operation, progress detected
    HALF_OPEN = "HALF_OPEN"  # Monitoring mode, checking for recovery
    OPEN = "OPEN"  # Failure detected, execution halted


@dataclass
class CircuitBreakerState:
    """Persisted circuit breaker state."""

    state: CircuitState = CircuitState.CLOSED
    last_change: str = ""
    consecutive_no_progress: int = 0
    consecutive_same_error: int = 0
    last_progress_loop: int = 0
    total_opens: int = 0
    reason: str = ""
    current_loop: int = 0
    last_error_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "last_change": self.last_change,
            "consecutive_no_progress": self.consecutive_no_progress,
            "consecutive_same_error": self.consecutive_same_error,
            "last_progress_loop": self.last_progress_loop,
            "total_opens": self.total_opens,
            "reason": self.reason,
            "current_loop": self.current_loop,
            "last_error_hash": self.last_error_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CircuitBreakerState":
        return cls(
            state=CircuitState(data.get("state", "CLOSED")),
            last_change=data.get("last_change", ""),
            consecutive_no_progress=data.get("consecutive_no_progress", 0),
            consecutive_same_error=data.get("consecutive_same_error", 0),
            last_progress_loop=data.get("last_progress_loop", 0),
            total_opens=data.get("total_opens", 0),
            reason=data.get("reason", ""),
            current_loop=data.get("current_loop", 0),
            last_error_hash=data.get("last_error_hash", ""),
        )


@dataclass
class CircuitTransition:
    """Record of a state transition."""

    timestamp: str
    loop: int
    from_state: str
    to_state: str
    reason: str


class CircuitBreaker:
    """
    Circuit breaker to prevent runaway loops.

    States:
    - CLOSED: Normal operation, can execute
    - HALF_OPEN: Monitoring after issues, one more no-progress triggers OPEN
    - OPEN: Halted, requires manual reset

    Triggers:
    - No progress for N consecutive loops
    - Same error repeated M times
    - Reward declining consistently
    """

    def __init__(
        self,
        state_dir: Path,
        no_progress_threshold: int = 3,
        same_error_threshold: int = 5,
        reward_decline_threshold: float = 0.1,
    ):
        self.state_dir = state_dir
        self.state_file = state_dir / "circuit_breaker.json"
        self.history_file = state_dir / "circuit_history.json"

        self.no_progress_threshold = no_progress_threshold
        self.same_error_threshold = same_error_threshold
        self.reward_decline_threshold = reward_decline_threshold

        self._state: CircuitBreakerState | None = None

    def _load_state(self) -> CircuitBreakerState:
        """Load or initialize state."""
        if self._state is not None:
            return self._state

        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                self._state = CircuitBreakerState.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                self._state = CircuitBreakerState()
        else:
            self._state = CircuitBreakerState()

        return self._state

    def _save_state(self, state: CircuitBreakerState) -> None:
        """Save state to disk."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state.to_dict(), f, indent=2)
        self._state = state

    def _log_transition(self, transition: CircuitTransition) -> None:
        """Log state transition to history."""
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                history = []

        history.append({
            "timestamp": transition.timestamp,
            "loop": transition.loop,
            "from_state": transition.from_state,
            "to_state": transition.to_state,
            "reason": transition.reason,
        })

        # Keep last 100 transitions
        history = history[-100:]

        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2)

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self._load_state().state

    def can_execute(self) -> bool:
        """Check if circuit allows execution."""
        state = self.get_state()
        return state != CircuitState.OPEN

    def should_halt(self) -> tuple[bool, str]:
        """Check if execution should halt."""
        s = self._load_state()
        if s.state == CircuitState.OPEN:
            return True, s.reason
        return False, ""

    def record_result(
        self,
        loop_number: int,
        has_progress: bool,
        has_errors: bool,
        error_hash: str = "",
        reward_delta: float = 0.0,
    ) -> tuple[CircuitState, str]:
        """
        Record loop result and update circuit state.

        Args:
            loop_number: Current loop iteration
            has_progress: Whether files changed or reward improved
            has_errors: Whether errors occurred
            error_hash: Hash of error messages (for repetition detection)
            reward_delta: Change in reward from last loop

        Returns:
            (new_state, reason) tuple
        """
        state = self._load_state()
        old_state = state.state

        # Update counters
        state.current_loop = loop_number

        if has_progress:
            state.consecutive_no_progress = 0
            state.last_progress_loop = loop_number
        else:
            state.consecutive_no_progress += 1

        # Check for same error repetition
        if has_errors and error_hash:
            if error_hash == state.last_error_hash:
                state.consecutive_same_error += 1
            else:
                state.consecutive_same_error = 1
                state.last_error_hash = error_hash
        else:
            state.consecutive_same_error = 0
            state.last_error_hash = ""

        # State machine transitions
        new_state = state.state
        reason = ""

        if state.state == CircuitState.CLOSED:
            # Normal operation - check for issues
            if state.consecutive_no_progress >= self.no_progress_threshold:
                new_state = CircuitState.OPEN
                reason = f"No progress in {state.consecutive_no_progress} consecutive loops"
            elif state.consecutive_same_error >= self.same_error_threshold:
                new_state = CircuitState.OPEN
                reason = f"Same error repeated {state.consecutive_same_error} times"
            elif reward_delta < -self.reward_decline_threshold:
                new_state = CircuitState.HALF_OPEN
                reason = f"Reward declined by {abs(reward_delta):.3f}"
            elif state.consecutive_no_progress >= 2:
                new_state = CircuitState.HALF_OPEN
                reason = f"{state.consecutive_no_progress} loops without progress, monitoring"

        elif state.state == CircuitState.HALF_OPEN:
            # Monitoring mode
            if has_progress:
                new_state = CircuitState.CLOSED
                reason = "Progress detected, circuit recovered"
            elif state.consecutive_no_progress >= self.no_progress_threshold:
                new_state = CircuitState.OPEN
                reason = f"No recovery after {state.consecutive_no_progress} loops"

        elif state.state == CircuitState.OPEN:
            # Stay open until manual reset
            reason = "Circuit is open, requires manual reset"

        # Update state
        if new_state != old_state:
            state.state = new_state
            state.last_change = datetime.utcnow().isoformat()
            state.reason = reason

            if new_state == CircuitState.OPEN:
                state.total_opens += 1

            # Log transition
            self._log_transition(CircuitTransition(
                timestamp=state.last_change,
                loop=loop_number,
                from_state=old_state.value,
                to_state=new_state.value,
                reason=reason,
            ))

        self._save_state(state)
        return new_state, reason

    def reset(self, reason: str = "Manual reset") -> None:
        """Reset circuit to CLOSED state."""
        state = CircuitBreakerState(
            state=CircuitState.CLOSED,
            last_change=datetime.utcnow().isoformat(),
            reason=reason,
        )
        self._save_state(state)

        self._log_transition(CircuitTransition(
            timestamp=state.last_change,
            loop=0,
            from_state="RESET",
            to_state=CircuitState.CLOSED.value,
            reason=reason,
        ))

    def get_status(self) -> dict[str, Any]:
        """Get full status for monitoring."""
        state = self._load_state()
        return {
            "state": state.state.value,
            "can_execute": state.state != CircuitState.OPEN,
            "reason": state.reason,
            "consecutive_no_progress": state.consecutive_no_progress,
            "consecutive_same_error": state.consecutive_same_error,
            "last_progress_loop": state.last_progress_loop,
            "current_loop": state.current_loop,
            "total_opens": state.total_opens,
            "thresholds": {
                "no_progress": self.no_progress_threshold,
                "same_error": self.same_error_threshold,
                "reward_decline": self.reward_decline_threshold,
            },
        }

    def format_status(self) -> str:
        """Format status for display."""
        status = self.get_status()
        state = status["state"]

        icon = {"CLOSED": "✅", "HALF_OPEN": "⚠️", "OPEN": "🛑"}.get(state, "?")

        lines = [
            f"Circuit Breaker: {icon} {state}",
            f"  Reason: {status['reason'] or 'Normal operation'}",
            f"  Loops since progress: {status['consecutive_no_progress']}",
            f"  Last progress: Loop #{status['last_progress_loop']}",
            f"  Total opens: {status['total_opens']}",
        ]

        return "\n".join(lines)
