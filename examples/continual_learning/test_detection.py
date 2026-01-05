#!/usr/bin/env python3
"""Test known algorithm detection for continual learning."""

import sys
sys.path.insert(0, "../../src")

from pathlib import Path
from obsidian.research.problem import load_problem
from obsidian.research.known_algorithms import create_detector_from_definitions


def main():
    # Load problem
    problem = load_problem("problem.yaml")
    config = problem.novelty.known_algorithms

    print("=" * 60)
    print("Continual Learning - Known Algorithm Detection")
    print("=" * 60)

    print(f"\nLoaded {len(config.definitions)} known algorithms:")
    for defn in config.definitions:
        print(f"  - {defn.name}: {defn.penalty:.0%} penalty")

    detector = create_detector_from_definitions(config.definitions)

    # Test 1: EWC-like code
    print("\n" + "-" * 60)
    print("Test 1: EWC-style code")
    print("-" * 60)

    ewc_code = """
class EWCOptimizer:
    def __init__(self, params, lr=0.01, ewc_lambda=1000):
        self.fisher = {}  # Fisher information
        self.old_params = {}
        self.importance = {}

    def step(self):
        for name, param in self.params.items():
            # EWC penalty: lambda * F * (theta - theta_old)^2
            ewc_penalty = self.fisher[name] * (param - self.old_params[name])
            grad = self.grads[name] + self.ewc_lambda * ewc_penalty
            param -= self.lr * grad

    def consolidate(self):
        # Compute Fisher information from gradients
        for name in self.params:
            self.fisher[name] = self.grads[name] ** 2
"""
    result = detector.detect(ewc_code, confidence_threshold=config.confidence_threshold)
    print(f"  Detected: {result.is_known}")
    print(f"  Algorithm: {result.algorithm_name}")
    print(f"  Confidence: {result.confidence:.0%}")
    print(f"  Penalty: {result.penalty:.0%}")

    # Test 2: Experience Replay code
    print("\n" + "-" * 60)
    print("Test 2: Experience Replay code")
    print("-" * 60)

    replay_code = """
class ReplayOptimizer:
    def __init__(self, params, buffer_size=1000):
        self.replay_buffer = []  # Store old samples
        self.memory_bank = {}

    def store_sample(self, x, y):
        self.replay_buffer.append((x, y))

    def step(self):
        # Sample from replay buffer for rehearsal
        old_samples = self.sample_from_buffer(batch_size=32)
        for x, y in old_samples:
            loss = self.compute_loss(x, y)
            self.backward(loss)
"""
    result = detector.detect(replay_code, confidence_threshold=config.confidence_threshold)
    print(f"  Detected: {result.is_known}")
    print(f"  Algorithm: {result.algorithm_name}")
    print(f"  Confidence: {result.confidence:.0%}")

    # Test 3: Standard Adam (should be detected)
    print("\n" + "-" * 60)
    print("Test 3: Standard Adam/SGD")
    print("-" * 60)

    adam_code = """
import torch.optim

optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)
"""
    result = detector.detect(adam_code, confidence_threshold=config.confidence_threshold)
    print(f"  Detected: {result.is_known}")
    print(f"  Algorithm: {result.algorithm_name}")
    print(f"  Confidence: {result.confidence:.0%}")

    # Test 4: Novel approach (should NOT be detected)
    print("\n" + "-" * 60)
    print("Test 4: Novel approach (should NOT be detected)")
    print("-" * 60)

    novel_code = """
class NovelContinualOptimizer:
    def __init__(self, params, lr=0.01):
        # Track gradient direction consistency
        self.direction_history = {}
        self.update_frequency = {}

    def step(self):
        for name, param in self.params.items():
            grad = self.grads[name]

            # Novel idea: only update if gradient direction is consistent
            # with historical direction (preserves old knowledge)
            current_dir = grad / (np.linalg.norm(grad) + 1e-8)
            historical_dir = self.direction_history.get(name, current_dir)

            consistency = np.dot(current_dir.flatten(), historical_dir.flatten())

            # Adaptive learning rate based on consistency
            effective_lr = self.lr * (0.5 + 0.5 * consistency)

            param -= effective_lr * grad

            # Update direction history with exponential moving average
            self.direction_history[name] = 0.9 * historical_dir + 0.1 * current_dir
"""
    result = detector.detect(novel_code, confidence_threshold=config.confidence_threshold)
    print(f"  Detected: {result.is_known}")
    print(f"  Confidence: {result.confidence:.0%}")

    print("\n" + "=" * 60)
    print("Detection test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
