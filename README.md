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
└── trace.jsonl          # Full evolution history (one JSON line per iteration)
```

---

## Quickstart (pi Agent)

If you're using [pi](https://pi.dev), the `verigen` Skill is auto-discovered in this repo. The agent can:

1. **Create a task** from your description (writes `initial.py`, `evaluate.py`, `program.md`)
2. **Run evolution** with `verigen run <task-dir/>`
3. **Return optimized code** with score and iteration history

Example interaction:
```
> Generate a fast palindrome checker and optimize it
```
The agent scaffolds the task, runs evolution, and returns the best code found.

---

## How It Works

You provide three files per task:

| File | Purpose |
|---|---|
| `initial.py` | Seed code with `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` markers around the editable region |
| `evaluate.py` | Exports `evaluate(code_str) -> dict` with keys: `score`, `passed`, `feedback`, `metrics`, `artifacts` |
| `program.md` | Task description + rich instructions. First `# Heading` = short description; full content = context for the LLM. |

**The loop:**

```
        ┌──────────────────────────────────────────────────┐
        │  DSPy Module: VerifiableCodeGen                  │
        │                                                  │
initial  │  1. Generate initial code (full program)         │
   │     │  2. Evaluate in subprocess                       │
   ▼     │  3. If initial fails hard constraints → stop     │
 mutate  │  4. LM suggests improvement (guided by feedback)  │
   │     │  5. Evaluate → keep if passed AND score improves  │
   ▼     │  6. Repeat up to --max-iterations                 │
 result  │  7. Return best code + trace                      │
        └──────────────────────────────────────────────────┘
```

- **Hard constraints**: If `passed=False`, candidate is rejected. If the initial generation fails hard constraints, the loop stops immediately — no point mutating fundamentally broken code.
- **Continuous metrics**: Higher `score` wins. Latency, accuracy, throughput — your `evaluate()` decides.
- **Sandbox**: Generated code runs in a subprocess with timeout. Process-level isolation (not a security container — see [Caveats](#caveats)).

---

## Creating a Task

### Step 1 — `initial.py`

The seed code. The LLM generates the **complete program**; EVOLVE-BLOCK markers are guidance, not splicing points.

```python
def solve(n: int) -> int:
    """Return n * 2."""
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this!")
    # EVOLVE-BLOCK-END
```

### Step 2 — `evaluate.py`

Must export `evaluate(code_str: str) -> dict`:

```python
import time

def evaluate(code: str) -> dict:
    ns = {}
    exec(code, ns)
    fn = ns["solve"]

    # Correctness tests
    assert fn(5) == 10, "basic case"
    assert fn(0) == 0, "zero"
    assert fn(-3) == -6, "negative"

    # Performance benchmark
    t0 = time.perf_counter()
    for _ in range(1000):
        fn(100)
    avg_us = (time.perf_counter() - t0) / 1000 * 1e6

    # Score: ratio vs reference, normalized via sigmoid.
    # 0.5 = equal to reference, 0.75 = 3× faster, 0.9 = 9× faster.
    speedup = ref_elapsed / avg_us if avg_us > 0 else 0
    score = speedup / (speedup + 1.0)

    return {
        "score": score,
        "passed": True,
        "feedback": f"All tests passed. Avg {avg_us:.1f}µs/call",
        "metrics": {"avg_us": avg_us},
        "artifacts": {},
    }
```

### Step 3 — `program.md`

```markdown
# Double it: return n * 2

Return the input integer multiplied by 2. Include a handle for zero and negatives.
```

Then run:

```bash
verigen run ./
```

Or scaffold automatically:

```bash
./skill/scripts/new-task.sh my-task
cd my-task
# Edit program.md and evaluate.py, then:
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
| `--score-threshold, -t` | — | Early stop when score ≥ threshold (e.g. 0.70 = ~2.3× reference) |
| `--model` | auto: local→env→abort | DSPy LM: `openai/gpt-4o`, `ollama_chat/qwen3.6`, `google/gemini-3-pro`, etc. |
| `--api-base` | — | API base URL (e.g., `http://localhost:8080/v1`) |
| `--output, -o` | `<task-dir>/output/` | Output directory |
| `--timeout` | 30 | Evaluation subprocess timeout (seconds) |

### Live progress

During evolution, the CLI shows per-iteration progress with timing:
```
  [  0] initial  ✓ score=0.8463    17614ms  ★
  [  1] mutate   ✓ score=0.8589    29373ms  ★
  [  2] mutate   ✓ score=0.6394    31704ms
  [  3] mutate   ✓ score=0.9528    46124ms  ★
```
A `★` marks a new best. Final status is one of:
- `completed` — all iterations ran
- `threshold_reached` — hit score threshold
- `plateau` — no improvement in recent iterations (try refining `program.md`)
- `initial_failed` — initial generation failed tests

### Output artifacts

```
<output-dir>/
├── best_program.py      # Final generated code
├── summary.json          # score, status, n_iterations, metrics, feedback
└── trace.jsonl          # One JSON object per iteration (includes diff_from_previous)
```

### LLM Configuration

DSPy handles all providers. The CLI auto-detects in this order:
1. `--model` / `--api-base` flags
2. Local `llama-server` at `http://localhost:8080/v1`
3. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` env vars

```bash
verigen run . --model openai/gpt-4o
verigen run . --model openai/qwen3.6 --api-base http://localhost:8080/v1
export OPENAI_API_KEY="sk-..." && verigen run .
```

Works with OpenAI, Anthropic, Google, Ollama, llama.cpp, vLLM.

---

## Example Tasks

| Task | Pattern | Difficulty | Notes |
|------|---------|-----------|-------|
| `examples/palindrome/` | String processing | Easy | Simple correctness + speed |
| `tasks/game_of_life/` | Matrix computation | Medium | Padding vs vectorized |
| `tasks/levenshtein/` | DP algorithm | Medium | 2D → 1D row optimization |
| `tasks/lru_cache/` | Data structure | Medium | OrderedDict → doubly-linked list |
| `tasks/topological_sort/` | Graph algorithm | Medium | Kahn's vs DFS optimization |

---

## Python API

```python
from verigen import VerifiableCodeGen, load_task

# Load a task
task = load_task("tasks/palindrome/")

# Run evolution
gen = VerifiableCodeGen(max_iterations=50, score_threshold=0.95)
result = gen(task)

# Best code + score
print(f"Score: {result.best_score:.4f}")
print(result.best_code)

# Full iteration history
for entry in result.trace.entries:
    badge = "✓" if entry.passed else "✗"
    print(f"  [{entry.iteration:3d}] {entry.phase:7s} {badge} score={entry.score:.4f}")
```

---

## Skill for pi

The repo ships as a [pi Skill](https://pi.dev). pi auto-discovers `SKILL.md` at the project root.

### Discovery locations

| Location | How |
|----------|-----|
| Project root | `SKILL.md` at repo root |
| Global | `~/.pi/agent/skills/verigen/SKILL.md` (symlink or copy) |
| Manual | `/skill:./SKILL.md` from within the repo |

### Agent workflow

1. Read `SKILL.md` → understand the tool
2. Analyze requirements (signature, constraints, performance target)
3. Scaffold task: `initial.py` + `evaluate.py` + `program.md`
4. Run `verigen run <task-dir/>`
5. Return code, score, and iteration history

---

## Caveats

**Sandbox is process-level, not a security container.** The subprocess runs in the same environment with full access to the filesystem and environment variables. A malicious `evaluate.py` can call `os.system()`. This is fine for trusted local tasks; it is **not** suitable for untrusted third-party tasks. Docker sandboxing is planned for v0.2.

**Evolution is single-threaded.** The loop maintains one candidate at a time (greedy hill-climbing). Population-based evolution with archive and diversity scoring is planned for v0.2.

---

## Test

```bash
# Unit tests (no LLM needed)
python -m pytest tests/ -v

# Integration tests (needs an LLM)
VERIGEN_TEST_LLM=1 python -m pytest tests/test_integration.py -v
```

---

## Project Status

**v0.2.0** — program.md context now reaches the LLM, sigmoid score normalization, live progress, plateau detection, diff-in-trace, env-var auto-detect.

| Area | Status |
|------|--------|
| Single-thread evolution | ✅ |
| Python subprocess sandbox | ✅ (process isolation, not container) |
| Full program.md context passed to LLM | ✅ |
| Change history feedback loop | ✅ |
| Live progress during evolution | ✅ |
| Plateau detection + actionable tips | ✅ |
| Diff in trace entries | ✅ |
| Sigmoid score normalization (no ceiling) | ✅ |
| Env var auto-detect (OpenAI/Anthropic/Google) | ✅ |
| CLI | ✅ |
| pi Skill | ✅ |
| Population/parallel evaluation | 🔜 v0.3 |
| Docker sandboxing | 🔜 v0.3 |
| DSPy MIPROv2 meta-optimization | 🔜 v0.3 |