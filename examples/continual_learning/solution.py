"""
Continual Learning Optimizer - Importance-based Learning Rate Scaling

Works well on synthetic benchmarks (0.98 score) but fails on MNIST (0.38 score).
This demonstrates that simple importance-based approaches don't generalize to real data.

See benchmark_mnist.py for MNIST results and analysis.
"""
import numpy as np


class ContinualOptimizer:
    """Minimal optimizer: momentum + importance-based LR scaling."""

    def __init__(self, params: dict, grads: dict, lr: float = 0.01, **kwargs):
        self.params = params
        self.grads = grads
        self.lr = lr
        self.current_task = 0

        self.param_updates = {}
        self.momentum = {}
        self.grad_accumulator = {}
        self.grad_count = {}
        self.importance_score = {}

        for name, param in params.items():
            self.momentum[name] = np.zeros_like(param)
            self.grad_accumulator[name] = np.zeros_like(param)
            self.grad_count[name] = 0
            self.importance_score[name] = np.zeros_like(param)

        self.momentum_decay = 0.86
        self.importance_scale = 294.0

    def zero_grad(self):
        for name in self.grads:
            self.grads[name].fill(0)

    def step(self, loss=None):
        self.param_updates = {}

        for name, param in self.params.items():
            grad = self.grads.get(name)
            if grad is None:
                continue

            self.grad_accumulator[name] += grad
            self.grad_count[name] += 1

            importance = self.importance_score[name]
            lr_scale = 1.0 / (1.0 + importance * self.importance_scale)

            self.momentum[name] = (
                self.momentum_decay * self.momentum[name] +
                (1 - self.momentum_decay) * grad
            )

            update = self.lr * lr_scale * self.momentum[name]
            self.param_updates[name] = update
            param -= update

    def task_switch(self, task_id: int):
        self.current_task = task_id

        if task_id > 0:
            for name in self.params:
                count = max(self.grad_count[name], 1)
                avg_grad = self.grad_accumulator[name] / count

                self.importance_score[name] *= 0.8

                grad_magnitude = np.abs(avg_grad)
                importance_update = np.tanh(grad_magnitude * 10)
                self.importance_score[name] += importance_update

                self.grad_accumulator[name] = np.zeros_like(avg_grad)
                self.grad_count[name] = 0
                self.momentum[name] = np.zeros_like(self.momentum[name])

    def state_dict(self):
        return {"current_task": self.current_task, "lr": self.lr}

    def load_state_dict(self, state):
        self.current_task = state.get("current_task", 0)
        self.lr = state.get("lr", self.lr)
