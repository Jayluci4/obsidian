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

2. **Identify Known Algorithms** (Critical for novelty):
   Based on the problem domain, identify ALL known/existing algorithms that solve this problem.
   For each known algorithm, generate:
   - `name`: Short identifier (e.g., "strassen", "dijkstra")
   - `description`: What it does and why it's known
   - `penalty`: 0.7-0.9 (higher = more common/obvious)
   - `keywords`: List of telltale variable names, function names, comments
   - `patterns`: Regex patterns that identify the algorithm's structure

   Example for matrix multiplication:
   - Strassen: keywords=["strassen", "m1", "m2", "m3", "m4", "m5", "m6", "m7"], penalty=0.9
   - Winograd: keywords=["winograd", "s1", "s2", "t1", "t2"], penalty=0.85
   - Naive: keywords=["triple loop", "O(n^3)"], patterns=["for.*for.*for"], penalty=0.7

3. Create a `problem.yaml` file with:
   - The prompt as the problem description
   - max_iterations set to --max-loops value
   - target_score set to --target value
   - **known_algorithms section with all identified algorithms**

4. Create a `solution.py` skeleton file with:
   - Function signature based on the problem type
   - TODO comment with the task

5. Create a `tests/` directory with basic test structure

6. Create a `benchmark.py` that outputs JSON with score

7. After creating files, immediately start working on the problem:
   - Read the problem description
   - Implement an initial solution (that is NOT a known algorithm)
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
  weights:
    correctness: 0.1
    benchmark: 0.5
    novelty: 0.4  # High weight to encourage novel solutions
  novelty:
    enabled: true
    known_algorithms:
      enabled: true
      confidence_threshold: 0.6
      # Claude fills this based on problem domain knowledge:
      definitions:
        - name: "[ALGORITHM_1_NAME]"
          description: "[WHY IT'S KNOWN]"
          penalty: 0.9  # 90% score reduction
          keywords: ["keyword1", "keyword2"]
          patterns: ["regex_pattern1", "regex_pattern2"]
        - name: "[ALGORITHM_2_NAME]"
          description: "[WHY IT'S KNOWN]"
          penalty: 0.8
          keywords: ["keyword1", "keyword2"]
          patterns: ["regex_pattern1"]
        # Add more known algorithms as identified...

archive:
  type: "map_elites"
  niches:
    - name: "approach"
      values: ["novel_1", "novel_2", "novel_3", "other"]
  max_solutions: 100

loop:
  max_iterations: [MAX_LOOPS]
  checkpoint_interval: 10
  early_stop_iterations: 20
```

IMPORTANT: After creating the files, immediately begin implementing the solution. Do not wait for user confirmation. The learning loop will guide improvements through feedback.
