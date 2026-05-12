---
name: verigen
description: >
  DSPy-native verifiable code generation through evolutionary optimization.
  Creates correct, performant Python code by evolving implementations against
  an automated evaluator. Use when the user needs a Python function optimized
  for correctness AND speed, or when iterating on generated code is the
  workflow. Handles arbitrary Python tasks: data processing, algorithms,
  data structures, regex, simulations, etc.
---

# Verigen Skill

**verigen** generates and optimizes Python code by running an evolutionary loop. You provide a task spec (template + evaluator), and verigen iterates: generate → evaluate → mutate → evaluate → keep if better.

## Setup

```bash
# Install from source (editable, recommended for dev)
cd /path/to/verigen && pip install -e .

# Or install from PyPI
pip install verigen

# Verify
verigen --help
```

### LLM Provider Setup

verigen uses DSPy under the hood — configure your LLM before running:

```bash
# Remote (OpenAI, Anthropic, etc.)
export OPENAI_API_KEY="sk-..."
verigen run tasks/palindrome/ --model "openai/gpt-4o"

# Local (Ollama, llama-server, vLLM, etc.)
verigen run tasks/palindrome/ \
  --model "openai/qwen3.6" \
  --api-base "http://localhost:8080/v1"

# If no --model is given, verigen auto-detects local llama-server
# at http://localhost:8080/v1
```

> **Tip for pi agents**: If the user hasn't configured an LLM, default to detecting a local server. Check `http://localhost:8080/v1/models` first, then fall back to asking the user.

---

## Task Format

Every task is a directory with three files:

```
my-task/
├── initial.py        # Seed code with # EVOLVE-BLOCK markers
├── evaluate.py       # Exports evaluate(code_str) -> dict
└── program.md        # Task description + hints (markdown)
```

### `initial.py` — Seed Code

The editable region is marked with `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END`. Everything outside is immutable context.

```python
def solve(data: list[int]) -> int:
    """Process data and return result."""
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this code!")
    # EVOLVE-BLOCK-END
```

The mutator can change anything in the file, but the markers guide it to focus on the critical section.

### `program.md` — Task Description

First `# Heading` becomes the task description. Full content is available as context for the mutator.

```markdown
# Solve: multiply each element by 2

Return a list where every input element is doubled.
```

### `evaluate.py` — The Evaluator

Must export `evaluate(code_str: str) -> dict`. Runs in a subprocess sandbox.

```python
import time

def evaluate(code_str: str) -> dict:
    """Run tests + benchmark. Return dict matching EvaluationResult schema."""
    ns = {}
    try:
        exec(code_str, ns)
    except Exception as e:
        return {"score": 0.0, "passed": False, "feedback": str(e),
                "metrics": {}, "artifacts": {}}

    fn = ns.get("solve")
    if not fn:
        return {"score": 0.0, "passed": False, "feedback": "Missing function",
                "metrics": {}, "artifacts": {}}

    # ── Correctness ──
    assert fn([1, 2, 3]) == [2, 4, 6], "Basic case"

    # ── Performance ──
    t0 = time.perf_counter()
    for _ in range(1000):
        fn(list(range(100)))
    avg_ms = (time.perf_counter() - t0) / 1000 * 1000

    score = max(0.0, 1.0 - avg_ms / 10.0)  # 1.0 at 0ms, 0.0 at >=10ms

    return {
        "score": score,
        "passed": True,
        "feedback": f"All tests passed, avg {avg_ms:.3f}ms per call",
        "metrics": {"avg_ms": avg_ms},
        "artifacts": {},
    }
```

**Schema** (return dict keys):

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `score` | `float` | ✅ | Higher = better. Continuous metric (latency, accuracy, etc.) |
| `passed` | `bool` | ✅ | Hard constraint gate. If `False`, candidate is rejected |
| `feedback` | `str` | ✅ | Description of results, errors, suggestions for the mutator |
| `metrics` | `dict` | ✅ | Structured metrics for traceability (may be empty) |
| `artifacts` | `dict` | ✅ | Free-form outputs (stdout, logs, plots) |

---

## CLI Commands

### Run evolution on a task

```bash
verigen run tasks/palindrome/

# With options
verigen run tasks/palindrome/ \
  --max-iterations 50 \
  --score-threshold 0.95 \
  --timeout 30 \
  --model "openai/gpt-4o" \
  --output ./results/
```

### Output artifacts

```
output/
├── best_program.py      # Final generated code
├── summary.json         # Score, iteration count, metrics
└── trace.jsonl          # Full evolution history (one JSON line per iteration)
```

---

## Agent Workflow

When a user asks for code that needs to be correct AND performant:

1. **Understand the task** — what's the function signature? what's the I/O? what are the performance requirements?
2. **Create the task directory** — write `initial.py`, `evaluate.py`, and `program.md` based on user requirements
3. **Run evolution** — `verigen run <task-dir/> --max-iterations 30`
4. **Present results** — show the generated code, score, and iteration history
5. **Iterate** — if results aren't satisfactory, tweak the evaluator (harder tests, different scoring) or increase iterations

### Task Types by Difficulty

| Task Type | What to do |
|-----------|-----------|
| **Simple function** (single pass, well-known algorithm) | Create task, run 15-30 iterations, show result |
| **Complex algorithm** (regex engine, LRU cache, Game of Life) | Create task with comprehensive tests + performance ladder hints in `program.md`, run 30-50 iterations |
| **Optimization from existing code** | Take user's existing code, wrap with EVOLVE-BLOCK markers, write evaluator with latency benchmark |
| **Class-based data structure** | Write `initial.py` with class skeleton + EVOLVE-BLOCK inside methods. The mutator handles multi-method edits |

### Evaluator Design Tips

- **Start strict but not too strict**: A single failing test that should be easy should not fail the entire evaluation. Use `passed=False` only for hard blockers.
- **Benchmark realistically**: Use enough iterations to get stable latency measurements (1000+ calls).
- **Feedback is key**: The LLM mutator reads `feedback` to decide what to change. Be descriptive about what went wrong.
- **Optimization ladders**: Include approximate expected scores in `program.md` for different approaches (helps the agent set expectations).

---

## Examples

The repo includes several tasks covering different patterns:

| Task | Pattern | Difficulty | Concepts |
|------|---------|-----------|----------|
| `examples/palindrome/` | Single function, string processing | Easy | Clean vs fast, regex vs manual |
| `tasks/game_of_life/` | Matrix computation | Medium | Padding, vectorization, sparse |
| `tasks/levenshtein/` | DP algorithm | Medium | 2D DP → 1D DP optimizations |
| `tasks/lru_cache/` | Class + data structure | Medium | Dict + linked list, O(1) ops |
| `tasks/regex_match/` | Recursive → DP | Hard | Backtracking traps, DP tables |
| `tasks/topological_sort/` | Graph algorithm | Medium | Kahn's, DFS, adjacency sets |

---

## Python API (for programmatic use)

```python
from verigen import VerifiableCodeGen, load_task, EvaluationResult

# Load a task
task = load_task("tasks/palindrome/", timeout=30)

# Run evolution
gen = VerifiableCodeGen(max_iterations=50, score_threshold=0.95)
result = gen(task)
print(f"Best score: {result.best_score:.4f}")
print(result.best_code)

# Inspect trace
for entry in result.trace.entries:
    badge = "✓" if entry.passed else "✗"
    print(f"  [{entry.iteration:3d}] {entry.phase:7s} {badge} score={entry.score:.4f}")

# Evaluate custom code
task = load_task("tasks/palindrome/")
eval_result = task.evaluate_fn("def is_palindrome(s): return s == s[::-1]")
print(f"passed={eval_result.passed} score={eval_result.score}")
```

---

## Common Pitfalls

1. **No EVOLVE-BLOCK markers**: The task won't load. Every `initial.py` must have `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END`.
2. **Evaluator crashes**: If `evaluate()` raises an unhandled exception, the sandbox catches it and returns `passed=False`. Check stderr.
3. **Slow first iteration**: The initial generation + evaluation can take 10-60s depending on LLM speed.
4. **Overly strict evaluator**: If `passed=False` is too easy to trigger, the mutator can never find improvements. Make it pass for any reasonable implementation, then use `score` to discriminate.
5. **Timeout**: Default eval timeout is 30s. Increase with `--timeout` for heavy benchmarks.

---

## Quick Reference

```bash
# Create new task
mkdir -p my-task && cd my-task
cat > initial.py << 'EOF'
def solve(n: int) -> int:
    """Return n * 2."""
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this!")
    # EVOLVE-BLOCK-END
EOF

cat > evaluate.py << 'EVALEOF'
def evaluate(code: str) -> dict:
    ns = {}
    exec(code, ns)
    fn = ns.get("solve")
    passed = fn(5) == 10 and fn(0) == 0 and fn(-3) == -6
    return {"score": 1.0 if passed else 0.0, "passed": passed,
            "feedback": "all good" if passed else "tests failed",
            "metrics": {}, "artifacts": {}}
EVALEOF

echo "# Double it: return n * 2" > program.md

# Run
verigen run ./
```
