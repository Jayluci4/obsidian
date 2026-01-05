"""
Tests for Continual Learning Optimizer.

These tests verify the optimizer interface works correctly.
The benchmark measures actual continual learning performance.
"""

import sys
sys.path.insert(0, "..")

import numpy as np
import pytest

from solution import ContinualOptimizer


class TestOptimizerInterface:
    """Test that the optimizer implements the required interface."""

    def create_simple_params(self):
        """Create simple test parameters."""
        params = {
            "w1": np.random.randn(10, 5).astype(np.float32),
            "b1": np.zeros(5, dtype=np.float32),
        }
        grads = {
            "w1": np.zeros_like(params["w1"]),
            "b1": np.zeros_like(params["b1"]),
        }
        return params, grads

    def test_initialization(self):
        """Test optimizer can be initialized."""
        params, grads = self.create_simple_params()
        optimizer = ContinualOptimizer(params, grads, lr=0.01)
        assert optimizer is not None
        assert optimizer.lr == 0.01

    def test_zero_grad(self):
        """Test zero_grad clears gradients."""
        params, grads = self.create_simple_params()
        grads["w1"] = np.ones_like(grads["w1"])
        grads["b1"] = np.ones_like(grads["b1"])

        optimizer = ContinualOptimizer(params, grads, lr=0.01)
        optimizer.zero_grad()

        assert np.allclose(grads["w1"], 0)
        assert np.allclose(grads["b1"], 0)

    def test_step_updates_params(self):
        """Test that step() updates parameters."""
        params, grads = self.create_simple_params()
        original_w1 = params["w1"].copy()

        # Set non-zero gradients
        grads["w1"] = np.ones_like(grads["w1"]) * 0.1
        grads["b1"] = np.ones_like(grads["b1"]) * 0.1

        optimizer = ContinualOptimizer(params, grads, lr=0.1)
        optimizer.step()

        # Parameters should have changed
        assert not np.allclose(params["w1"], original_w1)

    def test_task_switch(self):
        """Test task_switch method exists and runs."""
        params, grads = self.create_simple_params()
        optimizer = ContinualOptimizer(params, grads, lr=0.01)

        # Should not raise
        optimizer.task_switch(0)
        optimizer.task_switch(1)
        optimizer.task_switch(2)

    def test_state_dict(self):
        """Test state can be saved and loaded."""
        params, grads = self.create_simple_params()
        optimizer = ContinualOptimizer(params, grads, lr=0.01)

        optimizer.task_switch(5)
        state = optimizer.state_dict()

        assert "current_task" in state or "lr" in state

        # Create new optimizer and load state
        optimizer2 = ContinualOptimizer(params, grads, lr=0.01)
        optimizer2.load_state_dict(state)

    def test_multiple_steps(self):
        """Test optimizer handles multiple steps."""
        params, grads = self.create_simple_params()
        optimizer = ContinualOptimizer(params, grads, lr=0.01)

        for _ in range(100):
            grads["w1"] = np.random.randn(*grads["w1"].shape) * 0.1
            grads["b1"] = np.random.randn(*grads["b1"].shape) * 0.1
            optimizer.step()

        # Should not crash, params should be finite
        assert np.all(np.isfinite(params["w1"]))
        assert np.all(np.isfinite(params["b1"]))


class TestOptimizerBehavior:
    """Test optimizer behavior characteristics."""

    def test_gradient_descent_direction(self):
        """Test that updates move in gradient descent direction."""
        params = {"w": np.array([1.0, 2.0, 3.0])}
        grads = {"w": np.array([0.1, 0.2, 0.3])}

        original = params["w"].copy()
        optimizer = ContinualOptimizer(params, grads, lr=0.1)
        optimizer.step()

        # For standard gradient descent, params should decrease
        # (unless the optimizer does something clever)
        # This test just verifies something happened
        assert not np.allclose(params["w"], original)

    def test_zero_gradient_no_change(self):
        """Test that zero gradients cause no parameter change."""
        params = {"w": np.array([1.0, 2.0, 3.0])}
        grads = {"w": np.zeros(3)}

        original = params["w"].copy()
        optimizer = ContinualOptimizer(params, grads, lr=0.1)
        optimizer.step()

        # With zero gradients, params shouldn't change (much)
        # Allow small epsilon for numerical stability tricks
        assert np.allclose(params["w"], original, atol=1e-6)

    def test_memory_doesnt_explode(self):
        """Test that memory usage stays bounded across tasks."""
        params = {"w": np.random.randn(100, 100)}
        grads = {"w": np.zeros((100, 100))}

        optimizer = ContinualOptimizer(params, grads, lr=0.01)

        # Simulate many task switches
        for task_id in range(100):
            optimizer.task_switch(task_id)
            for _ in range(10):
                grads["w"] = np.random.randn(100, 100) * 0.01
                optimizer.step()

        # If we got here without memory error, that's good
        # A proper test would measure actual memory usage
        assert True
