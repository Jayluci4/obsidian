# Architecture Overview

## System Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLAUDE CODE                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         User Request                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    SessionStart Hook                                 │    │
│  │              (Inject ICRL context from memory)                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Claude Response                                 │    │
│  │                   (Code changes, fixes)                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        Stop Hook                                     │    │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │    │
│  │   │   Circuit    │  │  Evaluators  │  │   Strategy   │              │    │
│  │   │   Breaker    │  │   (pytest,   │  │  Controller  │              │    │
│  │   │              │  │   coverage)  │  │              │              │    │
│  │   └──────────────┘  └──────────────┘  └──────────────┘              │    │
│  │          │                  │                  │                     │    │
│  │          └──────────────────┼──────────────────┘                     │    │
│  │                             ▼                                        │    │
│  │   ┌─────────────────────────────────────────────────────────────┐   │    │
│  │   │                    Decision Engine                           │   │    │
│  │   │  • Target achieved? → Stop (exit 0)                          │   │    │
│  │   │  • Circuit open? → Stop (exit 0)                             │   │    │
│  │   │  • Max attempts? → Stop (exit 0)                             │   │    │
│  │   │  • Otherwise → Continue (exit 2) + Inject Feedback           │   │    │
│  │   └─────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Memory System                                    │    │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │    │
│  │   │   Episodic   │  │   Semantic   │  │  Procedural  │              │    │
│  │   │   (attempts) │  │   (facts)    │  │  (strategies)│              │    │
│  │   └──────────────┘  └──────────────┘  └──────────────┘              │    │
│  │                         SQLite                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Stop Hook (`scripts/stop_hook.py`)

The main learning loop controller. Executes after each Claude response.

**Flow:**
```python
1. Check circuit breaker → If OPEN, halt
2. Check max attempts → If exceeded, halt
3. Run evaluators → Get composite reward
4. Compute delta from baseline
5. Update circuit breaker state
6. Store episode in memory
7. Determine strategy mode
8. Check termination conditions
9. If continuing: Build feedback, exit code 2
```

**Exit Codes:**
- `0`: Allow stop (target achieved, circuit open, max attempts)
- `2`: Block stop, inject feedback (continue learning)

### 2. Session Start Hook (`scripts/session_start.py`)

Injects ICRL context at session start.

**Flow:**
```python
1. Load session history from memory
2. Build experience buffer (top-K episodes)
3. Determine strategy mode
4. Format meta-instruction
5. Inject as system message
```

### 3. Evaluator System (`src/obsidian/evaluator/`)

Multi-objective code quality measurement.

```
┌─────────────────────────────────────────────────┐
│              CompositeEvaluator                 │
│                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │  Pytest  │ │ Coverage │ │   Ruff   │  ...   │
│  │  weight  │ │  weight  │ │  weight  │        │
│  │   0.6    │ │   0.4    │ │   0.0    │        │
│  └──────────┘ └──────────┘ └──────────┘        │
│                                                 │
│  Composite Reward = Σ(weight_i × score_i)      │
└─────────────────────────────────────────────────┘
```

**Evaluators:**
- `PytestEvaluator`: Test pass rate
- `CoverageEvaluator`: Code coverage percentage
- `RuffEvaluator`: Lint error count (inverted)
- `PyrightEvaluator`: Type error count (inverted)
- `DeltaTracker`: Tracks improvement from baseline

### 4. Memory System (`src/obsidian/memory/`)

SQLite-backed persistent storage.

**Tables:**
```sql
episodes (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    attempt_number INTEGER,
    timestamp TEXT,
    reward REAL,
    metrics TEXT,  -- JSON
    action_summary TEXT,
    failures TEXT  -- JSON
)

session_state (
    session_id TEXT PRIMARY KEY,
    attempt_count INTEGER,
    best_reward REAL,
    reward_history TEXT,  -- JSON
    current_strategy TEXT
)
```

**Memory Types:**
- **Episodic**: Individual attempt records with rewards
- **Semantic**: Learned facts about the codebase
- **Procedural**: Strategy effectiveness tracking

### 5. Strategy System (`src/obsidian/strategy/`)

Adaptive mode selection and stuck detection.

**Circuit Breaker States:**
```
CLOSED ──(no progress)──► HALF_OPEN ──(no recovery)──► OPEN
   ▲                           │
   └────────(progress)─────────┘
```

**Strategy Modes:**
- `EXPLOIT`: Refine current approach (reward trending up)
- `EXPLORE`: Try different approach (reward trending down or stuck)
- `AUTONOMOUS`: Let Claude decide (stable or early session)

### 6. ICRL System (`src/obsidian/icrl/`)

In-Context Reinforcement Learning context building.

**Episode Selection:**
```python
# Quality-Diversity Filter
selected = []
selected += top_k_by_reward(60%)      # Best performers
selected += informative_failures(20%)  # What to avoid
selected += diverse_approaches(20%)    # Alternative strategies
```

**Context Format:**
```xml
<experience_buffer>
<attempt id="3" reward="0.85" best="true">
Action: Fixed parser bug
Metrics: pytest=0.95, coverage=0.75
</attempt>
<attempt id="2" reward="0.45">
Action: Added caching
Issues: Coverage dropped
</attempt>
</experience_buffer>

<meta_instruction>
Mode: EXPLOIT
Build on attempt 3 which showed promise.
Recent trend: +0.15
</meta_instruction>
```

### 7. Logging System (`src/obsidian/logging.py`)

Structured logging with rotation.

**Log Events:**
- Evaluations (pass/fail, score, duration)
- State changes (circuit breaker, strategy)
- Episodes (reward, metrics)
- Errors (with stack traces)

### 8. Error Handling (`src/obsidian/errors.py`)

Typed exceptions with retry logic.

**Error Types:**
- `EvaluatorError`: Evaluation failures
- `MemoryError`: Database errors
- `ConfigurationError`: Invalid config
- `TimeoutError`: Operation timeouts
- `HookError`: Hook execution failures

**Retry Pattern:**
```python
@with_retry(RetryConfig(max_attempts=3, delay_seconds=1.0))
def run_evaluation():
    ...
```

## Data Flow

### Learning Loop Iteration

```
1. Claude Response
       │
       ▼
2. Stop Hook Triggered
       │
       ├──► Circuit Breaker Check ──► OPEN? → Halt
       │
       ▼
3. Run Evaluators (parallel)
       │
       ├──► pytest → score
       ├──► coverage → score
       │
       ▼
4. Compute Composite Reward
       │
       ▼
5. Store Episode
       │
       ├──► episodes table
       ├──► update session_state
       │
       ▼
6. Update Circuit Breaker
       │
       ├──► Record progress/errors
       ├──► Check state transitions
       │
       ▼
7. Check Termination
       │
       ├──► reward >= threshold? → Stop
       ├──► all passed? → Stop
       │
       ▼
8. Build Feedback
       │
       ├──► Format metrics
       ├──► Add strategy guidance
       │
       ▼
9. Exit Code 2 (Continue)
```

### Session Start

```
1. SessionStart Hook Triggered
       │
       ▼
2. Load Memory
       │
       ├──► Get session state
       ├──► Get top-K episodes
       │
       ▼
3. Build Context
       │
       ├──► Format experience buffer
       ├──► Determine mode
       ├──► Add meta-instruction
       │
       ▼
4. Inject System Message
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | SQLite | Simple, no dependencies, concurrent reads |
| Hook type | Stop | Exit code 2 forces continuation |
| Reward | Weighted sum | Configurable, interpretable |
| Memory | Episodic + Semantic | Different retention needs |
| Strategy | 3 modes | Simple but effective |
| Circuit breaker | 3 states | Matches industry patterns |

## Extension Points

1. **New Evaluator**: Implement `BaseEvaluator` interface
2. **Custom Strategy**: Extend `StrategyController`
3. **Memory Type**: Add table to `MemoryStore`
4. **Episode Filter**: Implement new filter strategy

---

# Research Mode Architecture

Research Mode enables long-running algorithm discovery using MAP-Elites quality-diversity.

## System Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESEARCH MODE                                        │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Unified Stop Hook                                  │   │
│  │          (Auto-detects problem.yaml vs obsidian.yaml)                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Universal Evaluator                                │   │
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │   │ Correctness  │  │  Benchmark   │  │   Novelty    │               │   │
│  │   │  (pytest)    │  │  (user cmd)  │  │   (archive)  │               │   │
│  │   └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  │                             │                                         │   │
│  │                             ▼                                         │   │
│  │                   Weighted Score Computation                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    MAP-Elites Archive                                 │   │
│  │   ┌─────────────────────────────────────────────────────────────┐    │   │
│  │   │  Niche Grid (approach × complexity)                          │    │   │
│  │   │  ┌─────┬─────┬─────┬─────┬─────┐                            │    │   │
│  │   │  │ 0.85│ 0.72│     │ 0.91│     │  ← Best per niche          │    │   │
│  │   │  ├─────┼─────┼─────┼─────┼─────┤                            │    │   │
│  │   │  │     │ 0.65│ 0.78│     │ 0.69│                            │    │   │
│  │   │  └─────┴─────┴─────┴─────┴─────┘                            │    │   │
│  │   └─────────────────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Evolution Controller                               │   │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │
│  │   │  Mutate  │  │ Crossover│  │  Explore │  │  Exploit │            │   │
│  │   │   40%    │  │   30%    │  │   20%    │  │   10%    │            │   │
│  │   └──────────┘  └──────────┘  └──────────┘  └──────────┘            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Prompt Builder                                     │   │
│  │          (Assembles context + operation instruction)                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Problem Specification (`src/obsidian/research/problem.py`)

Loads and validates `problem.yaml` configuration.

```python
@dataclass
class ProblemSpec:
    name: str
    description: str
    solution_file: str
    correctness: CorrectnessConfig
    benchmark: BenchmarkConfig
    novelty: NoveltyConfig
    archive: ArchiveConfig
    evolution: EvolutionConfig
    loop: LoopConfig
```

### 2. Universal Evaluator (`src/obsidian/research/universal_evaluator.py`)

Domain-agnostic evaluation framework.

**Flow:**
```
1. Run correctness check (e.g., pytest)
   └── If failed → score = 0, stop
2. Run benchmark command
   └── Parse JSON output for score
3. Compute novelty vs archive
   └── Based on code similarity
4. Combine weighted scores
   └── final_score = benchmark_weight × benchmark + novelty_weight × novelty
```

**Benchmark Output Format:**
```json
{
  "score": 0.85,
  "metrics": {
    "time_ms": 12.5,
    "memory_mb": 1.2
  },
  "niche": {
    "approach": "divide_conquer",
    "complexity": "linearithmic"
  }
}
```

### 3. MAP-Elites Archive (`src/obsidian/research/archive.py`)

Quality-diversity solution storage.

**Key Operations:**
- `add(solution)`: Store if best in niche or creates new niche
- `get_top_k(k)`: Get K best solutions overall
- `get_diverse_sample(n)`: Sample across niches
- `get_parents_for_crossover()`: Select compatible parents
- `compute_novelty(code)`: Measure distance to archive

**Niche Grid:**
Each solution occupies a cell based on its niche values (e.g., approach=greedy, complexity=quadratic).

### 4. Evolution Controller (`src/obsidian/research/evolution.py`)

Selects evolutionary operations based on iteration and archive state.

**Operations:**
| Operation | Probability | Description |
|-----------|-------------|-------------|
| Mutate | 40% | Modify single solution |
| Crossover | 30% | Combine two solutions |
| Explore | 20% | Try new approach |
| Exploit | 10% | Refine best solution |

**Temperature Schedule:**
- Starts at 1.0 (high exploration)
- Decays by 0.995 per iteration
- Minimum 0.1 (some exploration always)

### 5. Prompt Builder (`src/obsidian/research/prompt_builder.py`)

Assembles evolutionary prompts for Claude.

**Prompt Structure:**
```xml
<problem>
Name: Novel Sorting Algorithm
Description: Discover an efficient sorting algorithm...
Solution file: solution.py
</problem>

<archive_summary>
Total solutions: 15
Best score: 0.91 (divide_conquer approach)
Coverage: 60% of niches filled
</archive_summary>

<operation type="crossover">
Combine these two solutions:
Parent 1 (score 0.85): [code]
Parent 2 (score 0.78): [code]
</operation>

<iteration_info>
Iteration: 47/1000
Recent trend: +0.05
Target: 0.90
</iteration_info>
```

### 6. Research Hook (`scripts/research_hook.py`)

Stop hook for research mode.

**Flow:**
```python
1. Load problem specification
2. Load/create archive
3. Evaluate current solution
4. Add to archive if valid
5. Check termination:
   - Target achieved? → Stop
   - Max iterations? → Stop
   - Early stop triggered? → Stop
6. Select next operation
7. Build feedback prompt
8. Exit code 2 (continue)
```

## Data Flow

### Research Loop Iteration

```
1. Claude modifies solution.py
       │
       ▼
2. Unified Stop Hook → Detects problem.yaml → Research Mode
       │
       ▼
3. Universal Evaluator
       │
       ├──► Correctness (pytest) → Pass/Fail
       ├──► Benchmark (user command) → Score + Metrics
       ├──► Novelty (vs archive) → Novelty score
       │
       ▼
4. Compute Final Score
       │
       ▼
5. Update Archive
       │
       ├──► Find niche for solution
       ├──► Compare with existing
       ├──► Store if best in niche
       │
       ▼
6. Check Termination
       │
       ├──► score >= target? → Export best, Stop
       ├──► iteration >= max? → Stop
       ├──► no progress for N? → Stop
       │
       ▼
7. Evolution Controller
       │
       ├──► Select operation (mutate/crossover/explore/exploit)
       ├──► Get parent solution(s)
       │
       ▼
8. Prompt Builder
       │
       ├──► Format problem context
       ├──► Add archive summary
       ├──► Add operation instruction
       │
       ▼
9. Exit Code 2 + Feedback
```

## Key Differences: Standard vs Research Mode

| Aspect | Standard Mode | Research Mode |
|--------|---------------|---------------|
| Config file | obsidian.yaml | problem.yaml |
| Goal | Fix tests, improve coverage | Discover algorithms |
| Evaluators | pytest, coverage, ruff, pyright | Correctness, Benchmark, Novelty |
| Memory | Episode history (SQLite) | MAP-Elites archive (JSON) |
| Strategy | Explore/Exploit modes | Evolutionary operations |
| Scale | ~10 iterations | 100-1000+ iterations |
| Output | Passing tests | Best solutions export |

## CLI Commands

```bash
# Initialize a research problem
obsidian research init --template algorithm --name "My Algorithm"

# View current status
obsidian research status

# View archive contents
obsidian research archive

# Export best solutions
obsidian research export --top 5

# Reset research state
obsidian research reset
```

## Templates

| Template | Use Case | Evaluators |
|----------|----------|------------|
| algorithm | Sorting, search, graph algorithms | pytest + benchmark |
| ml_model | Neural network design | pytest + benchmark (accuracy/loss) |
| optimization | Mathematical optimization | pytest + benchmark (objective) |
| custom | Custom problems | User-defined |
