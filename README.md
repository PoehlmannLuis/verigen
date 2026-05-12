# verigen

**DSPy-native verifiable code generation through evolutionary optimization.**

Write a task spec → run evolution → get correct, optimized code.

---

## Quickstart

```bash
pip install verigen
# or: uv pip install verigen

# Configure an LLM (DSPy uses OPENAI_API_KEY by default)
export OPENAI_API_KEY="..."
# Or use local:
# dspy.configure(lm=dspy.LM(model="openai/qwen3.6", api_base="http://localhost:8080/v1", api_key="not-needed"))

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

## How It Works

You provide two files per task:

| File | Purpose |
|---|---|
| `initial.py` | Seed code with `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` markers around the editable region |
| `evaluate.py` | Exports `evaluate(code_str) -> dict` with keys: `score`, `passed`, `feedback`, `metrics`, `artifacts` |
| `program.md` | Markdown instructions for the agent. First heading = task description. Same format as [autoresearch](https://github.com/karpathy/autoresearch). |

**The loop:**

```
        ┌──────────────────────────────────────────────┐
        │  DSPy Module: VerifiableCodeGen              │
        │                                              │
initial  │  1. Generate initial code (fills EVOLVE-BLOCK) │
   │     │  2. Evaluate in subprocess                    │
   ▼     │  3. If initial fails → stop                   │
 mutate  │  4. LM suggests improvement (guided by feedback)│
   │     │  5. Evaluate → keep if score improves         │
   ▼     │  6. Repeat up to --max-iterations             │
 result  │  7. Return best code + trace                  │
        └──────────────────────────────────────────────┘
```

- **Hard constraints**: If `passed=False`, candidate is rejected.
- **Continuous metrics**: Higher `score` wins. Latency, accuracy, throughput — your `evaluate()` decides.
- **Sandbox**: Generated code runs in a subprocess with timeout.

---

## User Journeys

### 1. "I need a correct, fast Python function"

```bash
cat > tasks/my_fn/initial.py << 'EOF'
def solve(input_data: list[int]) -> int:
    # EVOLVE-BLOCK-START
    raise NotImplementedError("implement me")
    # EVOLVE-BLOCK-END
EOF

cat > tasks/my_fn/evaluate.py << 'EOF'
import time
def evaluate(code: str) -> dict:
    ns = {}
    exec(code, ns)
    fn = ns["solve"]
    # test correctness
    assert fn([1,2,3]) == 6
    # measure speed
    t0 = time.perf_counter()
    for _ in range(1000): fn([1,2,3])
    lat = (time.perf_counter() - t0) / 1000
    score = max(0, 1.0 - lat / 0.001)  # 1.0 at 0ms, 0.0 at >=1ms
    return {"score": score, "passed": True, "feedback": f"latency={lat*1e6:.0f}us", "metrics": {"lat_us": lat*1e6}, "artifacts": {}}
EOF

echo '# solve: multiply input by 2' > tasks/my_fn/program.md

verigen run tasks/my_fn/ --max-iterations 30
cat tasks/my_fn/output/best_program.py
```

### 2. "I want this in my Python pipeline"

```python
from verigen import VerifiableCodeGen, load_task

gen = VerifiableCodeGen(max_iterations=50, score_threshold=0.95)
result = gen(load_task("tasks/my_fn/"))

# Use the generated code
exec(compile(result.best_code, "<gen>", "exec"))
print(solve([1, 2, 3]))

# Inspect the evolution
for entry in result.trace.entries:
    print(f"[{entry.iteration}] score={entry.score:.3f} passed={entry.passed}")
```

### 3. "I'm optimizing inference config, not Python"

Write an `evaluate.py` that writes a config file, runs your benchmark, and parses the metric. Same loop, different artifact format.

---

## Configuration

| What | How |
|---|---|
| **LLM provider** | DSPy handles it. `dspy.configure(lm=...)` or `--model`, `--api-base` flags. Works with OpenAI, Anthropic, Google, Ollama, llama.cpp, vLLM, etc. |
| **Model** | `verigen run ... --model openai/qwen3.6 --api-base http://localhost:8080/v1` |
| **Max iterations** | `--max-iterations 50` (default: 30) |
| **Score threshold** | `--score-threshold 0.95` (early stop) |
| **Eval timeout** | `--timeout 30` (seconds, for the sandbox) |
| **Output dir** | `--output path/` (default: `<task_dir>/output/`) |

---

## Output Artifacts

| File | Content |
|---|---|
| `best_program.py` | Final generated code (ready to use/import) |
| `summary.json` | `{score, n_iterations, feedback, metrics, paths}` |
| `trace.jsonl` | One JSON line per iteration: `{iteration, phase, score, passed, feedback, metrics, change_rationale, elapsed_ms}` |

---

## What to Expect

- **First run**: 10-60s (LLM generates initial code + evaluates)
- **Per mutation**: 10-60s (LLM reads feedback + generates improvement + evaluates)
- **30 iterations**: ~5-30 min depending on LLM speed and evaluation complexity
- **Result quality**: Depends on the LLM. Stronger models (GPT-4o, Claude 4, Gemini 3 Pro) produce better mutations. The evolutionary loop can discover optimizations the LLM wouldn't generate on its first try (e.g., the palindrome example: genexpr → `filter()` → 2.2x faster).

---

## Test

```bash
# Unit tests (no LLM)
python -m pytest tests/ -v

# Integration tests (needs LLM, optional)
VERIGEN_TEST_LLM=1 python -m pytest tests/test_integration.py -v
```

---

## Project Status

v0.1 — MVP. Single-thread evolution, Python + subprocess sandbox, DSPy deep integration.

**Planned**:
- Population-based evolution (archive, diversity scoring, parent selection)
- Docker sandboxing
- DSPy prompt-space meta-optimization (MIPROv2 on the codegen modules)
- Parallel evaluation
