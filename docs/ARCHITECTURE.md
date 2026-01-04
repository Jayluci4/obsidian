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
