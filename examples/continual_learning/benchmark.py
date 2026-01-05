#!/usr/bin/env python3
"""
Benchmark for Continual Learning Optimizer.

Measures:
1. Forward Transfer: How quickly does the model learn new tasks?
2. Backward Transfer: How well does it retain old tasks?
3. Memory Usage: Does memory grow with number of tasks?
4. Overall CL Score: Combined metric

The benchmark uses synthetic classification tasks to enable fast iteration.
Each task is a different random linear transformation of the input.
"""

import gc
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

# Seed for reproducibility
np.random.seed(42)


class SimpleModel:
    """Simple 2-layer MLP for testing optimizers."""

    def __init__(self, input_dim=20, hidden_dim=64, output_dim=5):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim

        # Initialize weights
        scale1 = np.sqrt(2.0 / input_dim)
        scale2 = np.sqrt(2.0 / hidden_dim)

        self.w1 = np.random.randn(input_dim, hidden_dim) * scale1
        self.b1 = np.zeros(hidden_dim)
        self.w2 = np.random.randn(hidden_dim, output_dim) * scale2
        self.b2 = np.zeros(output_dim)

        # Gradients
        self.w1_grad = np.zeros_like(self.w1)
        self.b1_grad = np.zeros_like(self.b1)
        self.w2_grad = np.zeros_like(self.w2)
        self.b2_grad = np.zeros_like(self.b2)

    def parameters(self):
        """Return list of (param, grad) tuples."""
        return [
            (self.w1, self.w1_grad, "w1"),
            (self.b1, self.b1_grad, "b1"),
            (self.w2, self.w2_grad, "w2"),
            (self.b2, self.b2_grad, "b2"),
        ]

    def zero_grad(self):
        """Zero all gradients."""
        self.w1_grad.fill(0)
        self.b1_grad.fill(0)
        self.w2_grad.fill(0)
        self.b2_grad.fill(0)

    def forward(self, x):
        """Forward pass."""
        self.x = x
        self.h = np.maximum(0, x @ self.w1 + self.b1)  # ReLU
        self.logits = self.h @ self.w2 + self.b2
        return self.logits

    def backward(self, y_true):
        """Backward pass with cross-entropy loss."""
        batch_size = y_true.shape[0]

        # Softmax
        exp_logits = np.exp(self.logits - self.logits.max(axis=1, keepdims=True))
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

        # Cross-entropy gradient
        d_logits = probs.copy()
        d_logits[np.arange(batch_size), y_true] -= 1
        d_logits /= batch_size

        # Backprop through layer 2
        self.w2_grad = self.h.T @ d_logits
        self.b2_grad = d_logits.sum(axis=0)

        # Backprop through ReLU and layer 1
        d_h = d_logits @ self.w2.T
        d_h = d_h * (self.h > 0)  # ReLU gradient

        self.w1_grad = self.x.T @ d_h
        self.b1_grad = d_h.sum(axis=0)

        # Return loss
        log_probs = np.log(probs[np.arange(batch_size), y_true] + 1e-10)
        return -log_probs.mean()

    def predict(self, x):
        """Predict class labels."""
        logits = self.forward(x)
        return logits.argmax(axis=1)

    def accuracy(self, x, y):
        """Compute accuracy."""
        preds = self.predict(x)
        return (preds == y).mean()


class TaskGenerator:
    """Generate synthetic classification tasks."""

    def __init__(self, input_dim=20, n_classes=5, n_samples=500):
        self.input_dim = input_dim
        self.n_classes = n_classes
        self.n_samples = n_samples
        self.tasks = []

    def create_task(self, task_id):
        """Create a task with random transformation."""
        np.random.seed(1000 + task_id)  # Reproducible per task

        # Random transformation matrix for this task
        transform = np.random.randn(self.input_dim, self.input_dim) * 0.5
        transform += np.eye(self.input_dim)  # Keep some identity

        # Class centers
        centers = np.random.randn(self.n_classes, self.input_dim) * 2

        # Generate data
        x_list, y_list = [], []
        for c in range(self.n_classes):
            n_per_class = self.n_samples // self.n_classes
            x_c = centers[c] + np.random.randn(n_per_class, self.input_dim) * 0.5
            x_c = x_c @ transform  # Apply task-specific transform
            x_list.append(x_c)
            y_list.append(np.full(n_per_class, c))

        x = np.vstack(x_list).astype(np.float32)
        y = np.concatenate(y_list).astype(np.int32)

        # Shuffle
        perm = np.random.permutation(len(y))
        x, y = x[perm], y[perm]

        # Split train/test
        split = int(0.8 * len(y))
        task = {
            "id": task_id,
            "x_train": x[:split],
            "y_train": y[:split],
            "x_test": x[split:],
            "y_test": y[split:],
        }
        self.tasks.append(task)
        return task

    def get_task(self, task_id):
        """Get task by ID."""
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return self.create_task(task_id)


def get_memory_usage():
    """Estimate memory usage of optimizer state."""
    gc.collect()
    # This is a rough estimate - actual implementation would track allocations
    return 0  # Placeholder


def train_on_task(model, optimizer, task, n_epochs=50, batch_size=32):
    """Train model on a single task."""
    x_train, y_train = task["x_train"], task["y_train"]
    n_samples = len(y_train)

    losses = []
    for epoch in range(n_epochs):
        # Shuffle
        perm = np.random.permutation(n_samples)
        x_shuffled, y_shuffled = x_train[perm], y_train[perm]

        epoch_loss = 0
        n_batches = 0

        for i in range(0, n_samples, batch_size):
            x_batch = x_shuffled[i:i+batch_size]
            y_batch = y_shuffled[i:i+batch_size]

            # Forward
            model.zero_grad()
            model.forward(x_batch)
            loss = model.backward(y_batch)

            # Copy model gradients to optimizer's grad dict
            for param, grad, name in model.parameters():
                if name in optimizer.grads:
                    np.copyto(optimizer.grads[name], grad)

            # Optimizer step (updates params in-place via optimizer.params dict)
            optimizer.step(loss)

            epoch_loss += loss
            n_batches += 1

        losses.append(epoch_loss / n_batches)

    return losses


def evaluate_on_all_tasks(model, tasks):
    """Evaluate model on all tasks."""
    accuracies = {}
    for task in tasks:
        acc = model.accuracy(task["x_test"], task["y_test"])
        accuracies[task["id"]] = acc
    return accuracies


def run_benchmark(optimizer_class, n_tasks=5, n_epochs=30):
    """Run the full continual learning benchmark."""
    results = {
        "tasks": [],
        "forward_transfer": [],
        "backward_transfer": [],
        "final_accuracies": {},
        "memory_usage": [],
    }

    # Create model and optimizer
    model = SimpleModel(input_dim=20, hidden_dim=64, output_dim=5)

    # Link optimizer to model's actual parameter arrays (not copies!)
    param_dict = {}
    grad_dict = {}
    for param, grad, name in model.parameters():
        param_dict[name] = param  # Reference to actual param array
        grad_dict[name] = grad    # Reference to actual grad array

    try:
        optimizer = optimizer_class(param_dict, grad_dict, lr=0.05)
    except TypeError:
        # Fallback if optimizer has different signature
        optimizer = optimizer_class(param_dict, lr=0.05)

    task_gen = TaskGenerator(input_dim=20, n_classes=5, n_samples=500)

    # Train on each task sequentially
    for task_id in range(n_tasks):
        # Notify optimizer of task switch
        if hasattr(optimizer, 'task_switch'):
            optimizer.task_switch(task_id)

        # Create and train on task
        task = task_gen.create_task(task_id)
        losses = train_on_task(model, optimizer, task, n_epochs=n_epochs)

        # Measure forward transfer (final accuracy on current task)
        current_acc = model.accuracy(task["x_test"], task["y_test"])
        results["forward_transfer"].append(current_acc)

        # Measure backward transfer (accuracy on all previous tasks)
        if task_id > 0:
            prev_accs = []
            for prev_id in range(task_id):
                prev_task = task_gen.get_task(prev_id)
                prev_acc = model.accuracy(prev_task["x_test"], prev_task["y_test"])
                prev_accs.append(prev_acc)
            avg_retention = np.mean(prev_accs)
            results["backward_transfer"].append(avg_retention)

        # Track memory
        mem = get_memory_usage()
        results["memory_usage"].append(mem)

        results["tasks"].append({
            "id": task_id,
            "final_loss": losses[-1] if losses else 0,
            "accuracy": current_acc,
        })

    # Final evaluation on all tasks
    results["final_accuracies"] = evaluate_on_all_tasks(model, task_gen.tasks)

    return results


def compute_cl_score(results):
    """Compute overall continual learning score."""
    # Average forward transfer (how well we learn new tasks)
    avg_forward = np.mean(results["forward_transfer"]) if results["forward_transfer"] else 0

    # Average backward transfer (how well we retain old tasks)
    avg_backward = np.mean(results["backward_transfer"]) if results["backward_transfer"] else 0

    # Final average accuracy across all tasks
    final_accs = list(results["final_accuracies"].values())
    avg_final = np.mean(final_accs) if final_accs else 0

    # Combined score (weighted average)
    # High weight on backward transfer (retention) since that's the hard part
    score = 0.3 * avg_forward + 0.5 * avg_backward + 0.2 * avg_final

    return {
        "score": score,
        "forward_transfer": avg_forward,
        "backward_transfer": avg_backward,
        "final_accuracy": avg_final,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No solution file provided", "score": 0}))
        sys.exit(1)

    solution_path = Path(sys.argv[1])
    if not solution_path.exists():
        print(json.dumps({"error": f"File not found: {solution_path}", "score": 0}))
        sys.exit(1)

    # Load the optimizer
    try:
        spec = importlib.util.spec_from_file_location("solution", solution_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        optimizer_class = getattr(module, "ContinualOptimizer", None)
        if optimizer_class is None:
            print(json.dumps({
                "error": "ContinualOptimizer class not found",
                "score": 0
            }))
            sys.exit(1)

    except Exception as e:
        print(json.dumps({
            "error": f"Failed to load solution: {str(e)}",
            "traceback": traceback.format_exc(),
            "score": 0
        }))
        sys.exit(1)

    # Run benchmark
    try:
        start_time = time.time()
        results = run_benchmark(optimizer_class, n_tasks=5, n_epochs=30)
        elapsed = time.time() - start_time

        # Compute score
        metrics = compute_cl_score(results)

        output = {
            "score": metrics["score"],
            "metrics": {
                "forward_transfer": metrics["forward_transfer"],
                "backward_transfer": metrics["backward_transfer"],
                "final_accuracy": metrics["final_accuracy"],
                "n_tasks": len(results["tasks"]),
            },
            "per_task": results["tasks"],
            "final_accuracies": results["final_accuracies"],
            "execution_time_s": elapsed,
        }

        print(json.dumps(output))

    except Exception as e:
        print(json.dumps({
            "error": f"Benchmark failed: {str(e)}",
            "traceback": traceback.format_exc(),
            "score": 0
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
