---
description: Initialize a new research problem for algorithm discovery
---

# Initialize Research Problem

Parse the user's arguments to extract:
- **prompt**: The research task/problem description (in quotes)
- **--max-loops**: Maximum iterations (default: 100)
- **--target**: Target score to achieve (default: 0.9)
- **--template**: Problem template - algorithm, ml_model, optimization, custom (default: algorithm)

Arguments: $ARGUMENTS

## Example Usage

```
/obsidian:research-init "Discover a 2x2 matrix multiplication using fewer than 8 multiplications" --max-loops 50 --target 0.95
```

## Instructions

1. Parse the arguments to extract the prompt and options
2. Create a `problem.yaml` file with:
   - The prompt as the problem description
   - max_iterations set to --max-loops value
   - target_score set to --target value

3. Create a `solution.py` skeleton file with:
   - Function signature based on the problem type
   - TODO comment with the task

4. Create a `tests/` directory with basic test structure

5. Create a `benchmark.py` that outputs JSON with score

6. After creating files, immediately start working on the problem:
   - Read the problem description
   - Implement an initial solution
   - The Obsidian hooks will automatically evaluate and provide feedback

## Problem YAML Template

```yaml
problem:
  name: "Research Problem"
  description: |
    [PROMPT FROM USER]
  solution_file: "solution.py"

evaluator:
  correctness:
    command: "python -m pytest tests/ -x -q"
    timeout: 60
  benchmark:
    command: "python benchmark.py solution.py"
    timeout: 120
    direction: "maximize"
    baseline_score: 0.0
    target_score: [TARGET]
    weight: 0.8
  novelty:
    enabled: true
    weight: 0.2

archive:
  type: "map_elites"
  niches:
    - name: "approach"
      values: ["method_a", "method_b", "method_c", "other"]
  max_solutions: 100

loop:
  max_iterations: [MAX_LOOPS]
  checkpoint_interval: 10
  early_stop_iterations: 20
```

IMPORTANT: After creating the files, immediately begin implementing the solution. Do not wait for user confirmation. The learning loop will guide improvements through feedback.
