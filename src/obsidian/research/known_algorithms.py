"""
Known Algorithm Detection Module.

Detects when solutions match known algorithms and applies penalties
to encourage discovery of truly novel approaches.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PatternMatcher(ABC):
    """Base class for pattern matching strategies."""

    type: str

    @abstractmethod
    def match(self, code: str, behavioral_data: dict | None = None) -> float:
        """
        Match code against pattern.

        Returns confidence score 0.0 to 1.0.
        """
        pass


@dataclass
class SignatureMatcher(PatternMatcher):
    """Match code patterns using regex/string matching."""

    type: str = "signature"
    patterns: list[str] = field(default_factory=list)
    threshold: float = 0.5  # Fraction of patterns that must match

    def match(self, code: str, behavioral_data: dict | None = None) -> float:
        """Match using regex patterns."""
        if not self.patterns:
            return 0.0

        code_normalized = self._normalize_code(code)
        matches = 0

        for pattern in self.patterns:
            try:
                if re.search(pattern, code_normalized, re.IGNORECASE | re.MULTILINE):
                    matches += 1
            except re.error:
                # Invalid regex, try literal match
                if pattern.lower() in code_normalized.lower():
                    matches += 1

        match_ratio = matches / len(self.patterns)
        return match_ratio if match_ratio >= self.threshold else 0.0

    def _normalize_code(self, code: str) -> str:
        """Normalize code for matching (remove extra whitespace)."""
        # Remove comments
        code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
        # Normalize whitespace
        code = re.sub(r"\s+", " ", code)
        return code


@dataclass
class BehavioralMatcher(PatternMatcher):
    """Match based on runtime behavior (e.g., multiplication count)."""

    type: str = "behavioral"
    expected_behavior: dict[str, Any] = field(default_factory=dict)
    tolerance: float = 0.0  # Exact match by default

    def match(self, code: str, behavioral_data: dict | None = None) -> float:
        """Match using behavioral signatures."""
        if not behavioral_data or not self.expected_behavior:
            return 0.0

        matches = 0
        total = len(self.expected_behavior)

        for key, expected in self.expected_behavior.items():
            actual = self._get_nested(behavioral_data, key)
            if actual is not None:
                if isinstance(expected, (int, float)):
                    if abs(actual - expected) <= self.tolerance:
                        matches += 1
                elif actual == expected:
                    matches += 1

        return matches / total if total > 0 else 0.0

    def _get_nested(self, data: dict, key: str) -> Any:
        """Get nested key like 'metrics.mult_count'."""
        parts = key.split(".")
        value = data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value


@dataclass
class KeywordMatcher(PatternMatcher):
    """Match based on keywords/variable names in code."""

    type: str = "keyword"
    keywords: list[str] = field(default_factory=list)
    threshold: float = 0.5

    def match(self, code: str, behavioral_data: dict | None = None) -> float:
        """Match using keyword detection."""
        if not self.keywords:
            return 0.0

        code_lower = code.lower()
        matches = sum(1 for kw in self.keywords if kw.lower() in code_lower)
        match_ratio = matches / len(self.keywords)
        return match_ratio if match_ratio >= self.threshold else 0.0


@dataclass
class KnownAlgorithm:
    """Definition of a known algorithm to detect and penalize."""

    name: str
    description: str
    patterns: list[PatternMatcher] = field(default_factory=list)
    penalty: float = 0.5  # 0.0 to 1.0, higher = more penalty
    severity: str = "hard"  # "hard" (multiplicative) or "soft" (additive)
    allow_variations: bool = False  # Whether variations are also penalized
    variation_penalty_factor: float = 0.5  # Reduced penalty for variations


@dataclass
class DetectionResult:
    """Result of known algorithm detection."""

    is_known: bool
    algorithm_name: str | None = None
    confidence: float = 0.0
    match_details: dict[str, Any] = field(default_factory=dict)
    penalty: float = 0.0
    matcher_scores: dict[str, float] = field(default_factory=dict)


class KnownAlgorithmDetector:
    """Detects known algorithms in submitted solutions."""

    def __init__(self, algorithms: list[KnownAlgorithm] | None = None):
        self.algorithms = algorithms or []

    def add_algorithm(self, algorithm: KnownAlgorithm) -> None:
        """Add an algorithm to detect."""
        self.algorithms.append(algorithm)

    def detect(
        self,
        code: str,
        behavioral_data: dict | None = None,
        confidence_threshold: float = 0.75,
    ) -> DetectionResult:
        """
        Check if code matches any known algorithm.

        Args:
            code: The solution code to analyze
            behavioral_data: Runtime behavior data (e.g., from benchmark)
            confidence_threshold: Minimum confidence to consider a match

        Returns:
            DetectionResult with match information and penalty
        """
        best_match: DetectionResult | None = None
        best_confidence = 0.0

        for algorithm in self.algorithms:
            result = self._check_algorithm(
                code, algorithm, behavioral_data, confidence_threshold
            )
            if result.is_known and result.confidence > best_confidence:
                best_match = result
                best_confidence = result.confidence

        if best_match:
            return best_match

        return DetectionResult(is_known=False)

    def _check_algorithm(
        self,
        code: str,
        algorithm: KnownAlgorithm,
        behavioral_data: dict | None,
        confidence_threshold: float,
    ) -> DetectionResult:
        """Check if code matches a specific algorithm."""
        if not algorithm.patterns:
            return DetectionResult(is_known=False)

        matcher_scores: dict[str, float] = {}
        total_score = 0.0

        for i, matcher in enumerate(algorithm.patterns):
            score = matcher.match(code, behavioral_data)
            matcher_key = f"{matcher.type}_{i}"
            matcher_scores[matcher_key] = score
            total_score += score

        # Average confidence across all matchers
        avg_confidence = total_score / len(algorithm.patterns)

        # Also check max (any single matcher with high confidence)
        max_confidence = max(matcher_scores.values()) if matcher_scores else 0.0

        # Use higher of average and max
        confidence = max(avg_confidence, max_confidence * 0.9)

        is_known = confidence >= confidence_threshold

        # Compute penalty
        penalty = 0.0
        if is_known:
            penalty = algorithm.penalty * confidence
        elif algorithm.allow_variations and confidence >= confidence_threshold * 0.6:
            # Partial penalty for variations
            penalty = algorithm.penalty * algorithm.variation_penalty_factor * confidence

        return DetectionResult(
            is_known=is_known or (algorithm.allow_variations and penalty > 0),
            algorithm_name=algorithm.name if is_known else None,
            confidence=confidence,
            match_details={
                "algorithm": algorithm.name,
                "avg_score": avg_confidence,
                "max_score": max_confidence,
                "threshold": confidence_threshold,
            },
            penalty=penalty,
            matcher_scores=matcher_scores,
        )

    def compute_penalized_score(
        self,
        base_score: float,
        detection_result: DetectionResult,
        penalty_mode: str = "multiplicative",
    ) -> float:
        """
        Compute final score after applying penalty.

        Args:
            base_score: Original score before penalty
            detection_result: Result from detect()
            penalty_mode: "multiplicative" or "additive"

        Returns:
            Penalized score
        """
        if not detection_result.is_known and detection_result.penalty == 0:
            return base_score

        if penalty_mode == "multiplicative":
            # Score * (1 - penalty)
            return base_score * (1.0 - detection_result.penalty)
        else:
            # Score - penalty
            return max(0.0, base_score - detection_result.penalty)


def create_detector_from_definitions(
    definitions: list,  # list[AlgorithmDefinition] from problem.py
) -> KnownAlgorithmDetector:
    """
    Create a detector from dynamic algorithm definitions.

    These definitions are generated by Claude during research-init,
    making the system domain-agnostic.

    Args:
        definitions: List of AlgorithmDefinition objects

    Returns:
        Configured KnownAlgorithmDetector
    """
    detector = KnownAlgorithmDetector()

    for defn in definitions:
        patterns = []

        # Create keyword matcher if keywords provided
        if defn.keywords:
            patterns.append(
                KeywordMatcher(
                    keywords=defn.keywords,
                    threshold=0.3,  # At least 30% of keywords must match
                )
            )

        # Create signature matcher if patterns provided
        if defn.patterns:
            patterns.append(
                SignatureMatcher(
                    patterns=defn.patterns,
                    threshold=0.4,  # At least 40% of patterns must match
                )
            )

        if patterns:
            algorithm = KnownAlgorithm(
                name=defn.name,
                description=defn.description,
                patterns=patterns,
                penalty=defn.penalty,
                severity="hard",
                allow_variations=True,
                variation_penalty_factor=0.5,
            )
            detector.add_algorithm(algorithm)

    return detector


def create_detector_from_config(
    algorithm_names: list[str],
    custom_definitions: dict[str, KnownAlgorithm] | None = None,
) -> KnownAlgorithmDetector:
    """
    Create a detector from algorithm names (legacy fallback).

    Args:
        algorithm_names: List of algorithm names to detect
        custom_definitions: Optional custom algorithm definitions

    Returns:
        Configured KnownAlgorithmDetector
    """
    from obsidian.research.known_algorithms_db import get_algorithm

    detector = KnownAlgorithmDetector()

    for name in algorithm_names:
        # Check custom definitions first
        if custom_definitions and name in custom_definitions:
            detector.add_algorithm(custom_definitions[name])
        else:
            # Try to load from database
            algorithm = get_algorithm(name)
            if algorithm:
                detector.add_algorithm(algorithm)

    return detector
