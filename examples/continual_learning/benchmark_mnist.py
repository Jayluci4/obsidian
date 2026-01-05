#!/usr/bin/env python3
"""
Split MNIST Benchmark for Continual Learning.

Tasks:
  Task 0: digits 0, 1
  Task 1: digits 2, 3
  Task 2: digits 4, 5
  Task 3: digits 6, 7
  Task 4: digits 8, 9
"""

import gzip
import os
import struct
import urllib.request
from pathlib import Path

import numpy as np

# MNIST URLs (using mirror since original is down)
MNIST_URL = "https://ossci-datasets.s3.amazonaws.com/mnist/"
MNIST_FILES = {
    "train_images": "train-images-idx3-ubyte.gz",
    "train_labels": "train-labels-idx1-ubyte.gz",
    "test_images": "t10k-images-idx3-ubyte.gz",
    "test_labels": "t10k-labels-idx1-ubyte.gz",
}

DATA_DIR = Path(__file__).parent / "data"


def download_mnist():
    """Download MNIST dataset if not present."""
    DATA_DIR.mkdir(exist_ok=True)

    for name, filename in MNIST_FILES.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"Downloading {filename}...")
            url = MNIST_URL + filename
            urllib.request.urlretrieve(url, filepath)
    print("MNIST downloaded.")


def load_mnist():
    """Load MNIST data."""
    download_mnist()

    def read_images(filename):
        with gzip.open(DATA_DIR / filename, 'rb') as f:
            magic, num, rows, cols = struct.unpack(">IIII", f.read(16))
            data = np.frombuffer(f.read(), dtype=np.uint8)
            return data.reshape(num, rows * cols).astype(np.float32) / 255.0

    def read_labels(filename):
        with gzip.open(DATA_DIR / filename, 'rb') as f:
            magic, num = struct.unpack(">II", f.read(8))
            return np.frombuffer(f.read(), dtype=np.uint8)

    train_x = read_images(MNIST_FILES["train_images"])
    train_y = read_labels(MNIST_FILES["train_labels"])
    test_x = read_images(MNIST_FILES["test_images"])
    test_y = read_labels(MNIST_FILES["test_labels"])

    return train_x, train_y, test_x, test_y


class SimpleModel:
    """Simple MLP for MNIST."""

    def __init__(self, input_dim=784, hidden_dim=256, output_dim=10):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim

        scale1 = np.sqrt(2.0 / input_dim)
        scale2 = np.sqrt(2.0 / hidden_dim)

        self.w1 = np.random.randn(input_dim, hidden_dim).astype(np.float32) * scale1
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)
        self.w2 = np.random.randn(hidden_dim, output_dim).astype(np.float32) * scale2
        self.b2 = np.zeros(output_dim, dtype=np.float32)

        self.w1_grad = np.zeros_like(self.w1)
        self.b1_grad = np.zeros_like(self.b1)
        self.w2_grad = np.zeros_like(self.w2)
        self.b2_grad = np.zeros_like(self.b2)

    def parameters(self):
        return [
            (self.w1, self.w1_grad, "w1"),
            (self.b1, self.b1_grad, "b1"),
            (self.w2, self.w2_grad, "w2"),
            (self.b2, self.b2_grad, "b2"),
        ]

    def zero_grad(self):
        self.w1_grad.fill(0)
        self.b1_grad.fill(0)
        self.w2_grad.fill(0)
        self.b2_grad.fill(0)

    def forward(self, x):
        self.x = x
        self.h = np.maximum(0, x @ self.w1 + self.b1)
        self.logits = self.h @ self.w2 + self.b2
        return self.logits

    def backward(self, y_true):
        batch_size = y_true.shape[0]
        exp_logits = np.exp(self.logits - self.logits.max(axis=1, keepdims=True))
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

        d_logits = probs.copy()
        d_logits[np.arange(batch_size), y_true] -= 1
        d_logits /= batch_size

        self.w2_grad = self.h.T @ d_logits
        self.b2_grad = d_logits.sum(axis=0)

        d_h = d_logits @ self.w2.T
        d_h = d_h * (self.h > 0)

        self.w1_grad = self.x.T @ d_h
        self.b1_grad = d_h.sum(axis=0)

        log_probs = np.log(probs[np.arange(batch_size), y_true] + 1e-10)
        return -log_probs.mean()

    def predict(self, x):
        logits = self.forward(x)
        return logits.argmax(axis=1)

    def accuracy(self, x, y):
        preds = self.predict(x)
        return (preds == y).mean()


def create_split_mnist_tasks():
    """Create 5 tasks from MNIST (2 digits each)."""
    train_x, train_y, test_x, test_y = load_mnist()

    tasks = []
    digit_pairs = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9)]

    for task_id, (d1, d2) in enumerate(digit_pairs):
        # Filter for these digits
        train_mask = (train_y == d1) | (train_y == d2)
        test_mask = (test_y == d1) | (test_y == d2)

        task_train_x = train_x[train_mask]
        task_train_y = train_y[train_mask]
        task_test_x = test_x[test_mask]
        task_test_y = test_y[test_mask]

        # Shuffle training data
        perm = np.random.permutation(len(task_train_y))
        task_train_x = task_train_x[perm]
        task_train_y = task_train_y[perm]

        tasks.append({
            "id": task_id,
            "digits": (d1, d2),
            "x_train": task_train_x,
            "y_train": task_train_y,
            "x_test": task_test_x,
            "y_test": task_test_y,
        })

    return tasks


def train_on_task(model, optimizer, task, n_epochs=5, batch_size=64):
    """Train model on a single task."""
    x_train, y_train = task["x_train"], task["y_train"]
    n_samples = len(y_train)

    for epoch in range(n_epochs):
        perm = np.random.permutation(n_samples)
        x_shuffled, y_shuffled = x_train[perm], y_train[perm]

        for i in range(0, n_samples, batch_size):
            x_batch = x_shuffled[i:i+batch_size]
            y_batch = y_shuffled[i:i+batch_size]

            model.zero_grad()
            model.forward(x_batch)
            model.backward(y_batch)

            for param, grad, name in model.parameters():
                if name in optimizer.grads:
                    np.copyto(optimizer.grads[name], grad)

            optimizer.step()


def run_benchmark(optimizer_class, n_epochs=5):
    """Run Split MNIST benchmark."""
    np.random.seed(42)

    print("Loading MNIST...")
    tasks = create_split_mnist_tasks()

    print("Creating model...")
    model = SimpleModel(input_dim=784, hidden_dim=256, output_dim=10)

    param_dict = {}
    grad_dict = {}
    for param, grad, name in model.parameters():
        param_dict[name] = param
        grad_dict[name] = grad

    optimizer = optimizer_class(param_dict, grad_dict, lr=0.01)

    results = {
        "tasks": [],
        "accuracy_matrix": [],  # accuracy_matrix[i][j] = acc on task j after training task i
    }

    print("\nTraining...")
    for task_id, task in enumerate(tasks):
        if hasattr(optimizer, 'task_switch'):
            optimizer.task_switch(task_id)

        print(f"\n--- Task {task_id}: digits {task['digits']} ---")
        train_on_task(model, optimizer, task, n_epochs=n_epochs)

        # Evaluate on current task
        acc = model.accuracy(task["x_test"], task["y_test"])
        print(f"  Accuracy on task {task_id}: {acc:.2%}")

        # Evaluate on all tasks seen so far
        row = []
        for prev_task in tasks[:task_id + 1]:
            prev_acc = model.accuracy(prev_task["x_test"], prev_task["y_test"])
            row.append(prev_acc)
        results["accuracy_matrix"].append(row)

        results["tasks"].append({
            "id": task_id,
            "digits": task["digits"],
            "accuracy": acc,
        })

    # Final evaluation on all tasks
    print("\n--- Final Evaluation ---")
    final_accs = {}
    for task in tasks:
        acc = model.accuracy(task["x_test"], task["y_test"])
        final_accs[task["id"]] = acc
        print(f"  Task {task['id']} (digits {task['digits']}): {acc:.2%}")

    results["final_accuracies"] = final_accs

    # Compute metrics
    avg_final = np.mean(list(final_accs.values()))

    # Backward transfer: average retention of previous tasks
    backward_scores = []
    for i in range(1, len(tasks)):
        for j in range(i):
            backward_scores.append(results["accuracy_matrix"][i][j])
    avg_backward = np.mean(backward_scores) if backward_scores else 0

    # Forward transfer: accuracy on each task right after training
    forward_scores = [results["accuracy_matrix"][i][i] for i in range(len(tasks))]
    avg_forward = np.mean(forward_scores)

    score = 0.3 * avg_forward + 0.5 * avg_backward + 0.2 * avg_final

    results["metrics"] = {
        "score": score,
        "forward_transfer": avg_forward,
        "backward_transfer": avg_backward,
        "final_accuracy": avg_final,
    }

    print(f"\n--- Metrics ---")
    print(f"  Forward transfer:  {avg_forward:.4f}")
    print(f"  Backward transfer: {avg_backward:.4f}")
    print(f"  Final accuracy:    {avg_final:.4f}")
    print(f"  Score:             {score:.4f}")

    return results


if __name__ == "__main__":
    import sys
    import importlib.util

    if len(sys.argv) < 2:
        print("Usage: python benchmark_mnist.py <solution.py>")
        sys.exit(1)

    solution_path = Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location("solution", solution_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    optimizer_class = getattr(module, "ContinualOptimizer")
    results = run_benchmark(optimizer_class, n_epochs=5)
