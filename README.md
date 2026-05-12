# verigen

**verigen** — verifiable code generation through evolutionary optimization.

Write a task spec → run evolution → get correct, optimized code.

verigen is also a **[pi](https://pi.dev) Skill**: the agent reads `SKILL.md` to understand how to orchestrate the CLI for code generation tasks.

---

## Quickstart (CLI)

```bash
pip install verigen
# or: cd verigen && pip install -e .

# Configure an LLM (DSPy handles the rest)
export OPENAI_API_KEY="sk-..."

# Run evolution on a task
verigen run examples/palindrome/
```

Output:
```
examples/palindrome/output/
├── best_program.py      # Best code found
├── summary.json         # Score, metrics, paths
└── trace.jsonl          # Full evolution history
```

---

## Quickstart (pi Agent)

If you're using [pi](https://pi.dev), the `verigen` Skill is auto-discovered in this repo. The agent can:

1. **Ask the agent** to create a task from your description
2. **Run evolution** with `verigen run <task-dir/>`
3. **Get optimized code** with score and iteration history

Example:
```
> Generate a fast palindrome checker and optimize it
```
The agent creates a task, runs evolution, and returns the optimized code.

---

## How It Works

You provide two files per task:

| File | Purpose |
|---|---|
| `initial.py` | Seed code with `# EVOLVE-BLOCK` markers around the editable region |
| `evaluate.py` | Exports `evaluate(code_str) -> dict` with keys: `score`, `passed`, `feedback`, `metrics`, `artifacts` |
| `program.md` | Markdown instructions for the LLM. First heading = task description. |

**The loop:**

```
        ┌──────────────────────────────────────────────────┐
        │  DSPy Module: VerifiableCodeGen                  │
        │                                                  │
initial  │  1. Generate initial code (fills EVOLVE-BLOCK)   │
   │     │  2. Evaluate in subprocess                       │
   ▼     │  3. If initial fails → stop                      │
 mutate  │  4. LM suggests improvement (guided by feedback)  │
   │     │  5. Evaluate → keep if score improves             │
   ▼     │  6. Repeat up to --max-iterations                 │
 result  │  7. Return best code + trace                      │
        └──────────────────────────────────────────────────┘
```

- **Hard constraints**: If `passed=False`, candidate is rejected.
- **Continuous metrics**: Higher `score` wins. Latency, accuracy, throughput — your `evaluate()` decides.
- **Sandbox**: Generated code runs in a subprocess with timeout.

---

## Creating a Task

```bash
mkdir -p my-task && cd my-task

cat > initial.py << 'EOF'
def solve(n: int) -> int:
    """Return n * 2."""
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this!")
    # EVOLVE-BLOCK-END
EOF

cat > evaluate.py << 'EVALEOF'
import time

def evaluate(code: str) -> dict:
    ns = {}
    exec(code, ns)
    fn = ns["solve"]

    # Correctness
    assert fn(5) == 10
    assert fn(0) == 0

    # Performance
    t0 = time.perf_counter()
    for _ in range(1000): fn(100)
    avg_us = (time.perf_counter() - t0) / 1000 * 1e6
    score = max(0.0, 1.0 - avg_us / 100.0)

    return {"score": score, "passed": True,
            "feedback": f"avg {avg_us:.1f}us", "metrics": {"us": avg_us}, "artifacts": {}}
EVALEOF

echo "# Double it: return n * 2" > program.md

verigen run ./
```

---

## CLI Reference

```bash
verigen run <task-dir> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--max-iterations, -n` | 30 | Maximum evolution iterations |
| `--score-threshold, -t` | — | Early stop when score >= threshold (e.g. 0.95) |
| `--model` | auto-detect | DSPy LM model string: `openai/gpt-4o`, `ollama_chat/qwen3.6`, etc. |
| `--api-base` | — | Custom API base URL for the model |
| `--output, -o` | `<task-dir>/output/` | Output directory |
| `--timeout` | 30 | Evaluation subprocess timeout (seconds) |

### Output

```
<output-dir>/
├── best_program.py      # Final generated code
├── summary.json         # Score, iteration count, feedback, metrics
└── trace.jsonl          # One JSON line per iteration
```

### Configuration

- **LLM**: DSPy handles it. `dspy.configure(lm=...)` or CLI flags.
  Works with OpenAI, Anthropic, Google, Ollama, vLLM, llama.cpp.
- **Local default**: Auto-detects `http://localhost:8080/v1` for llama-server.

---

## Example Tasks

| Task | Pattern | Difficulty |
|------|---------|-----------|
| `examples/palindrome/` | String processing | Easy |
| `tasks/game_of_life/` | Matrix computation | Medium |
| `tasks/levenshtein/` | DP algorithm | Medium |
| `tasks/lru_cache/` | Data structure | Medium |
| `tasks/regex_match/` | Recursive → DP | Hard |
| `tasks/topological_sort/` | Graph algorithm | Medium |

---

## Python API

```python
from verigen import VerifiableCodeGen, load_task

# Load and run
task = load_task("tasks/palindrome/")
gen = VerifiableCodeGen(max_iterations=50, score_threshold=0.95)
result = gen(task)

# Use the best code
exec(compile(result.best_code, "<gen>", "exec"))
print(is_palindrome("racecar"))  # True

# Inspect trace
for entry in result.trace.entries:
    print(f"[{entry.iteration:3d}] {entry.phase:7s} score={entry.score:.4f}  {entry.feedback[:60]}")
```

---

## Skill for pi

This repo ships as a [pi Skill](https://pi.dev). The agent reads `SKILL.md` to understand the tool and orchestrate the CLI.

### Discovery

- **Project-local**: pi discovers `SKILL.md` at the repo root when you're in the project directory
- **Global install**: symlink to `~/.pi/agent/skills/verigen/SKILL.md` (coming soon)
- **Manual load**: `/skill:./SKILL.md` from within the repo

### Agent Workflow

When you ask the pi agent to generate optimized code:

1. Agent reads `SKILL.md` and understands the tool
2. Analyzes your requirements (function signature, constraints, performance needs)
3. Creates a task directory with `initial.py`, `evaluate.py`, `program.md`
4. Runs `verigen run <task-dir/>` with appropriate options
5. Presents results: code, score, iteration history, improvement trajectory

---

## Test

```bash
# Unit tests (no LLM needed)
python -m pytest tests/ -v

# Integration tests (needs LLM)
VERIGEN_TEST_LLM=1 python -m pytest tests/test_integration.py -v
```

---

## Project Status

v0.1 — MVP. Single-thread evolution, Python + subprocess sandbox, DSPy deep integration.

**Planned**: Population-based evolution, Docker sandboxing, DSPy prompt-space meta-optimization (MIPROv2), parallel evaluation.
