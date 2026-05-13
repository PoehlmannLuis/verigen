#!/usr/bin/env bash
# Scaffold a new verigen task with smarter defaults.
#
# Usage:
#   ./skill/scripts/new-task.sh my-task
#   ./skill/scripts/new-task.sh tasks/custom-optimizer
#
# Creates:
#   <task-dir>/
#   ├── initial.py        # Template with EVOLVE-BLOCK markers
#   ├── evaluate.py       # Evaluator with reference impl + sigmoid scoring
#   └── program.md        # Task description with optimization ladder

set -euo pipefail

TASK_DIR="${1:-}"

if [ -z "$TASK_DIR" ]; then
    echo "Usage: $0 <task-dir>"
    exit 1
fi

if [ -d "$TASK_DIR" ]; then
    echo "Error: $TASK_DIR already exists"
    exit 1
fi

mkdir -p "$TASK_DIR"

# ── initial.py ──────────────────────────────────────────────────────────
cat > "$TASK_DIR/initial.py" << 'EOF'
def solve(input_data):
    """Implement this function. The EVOLVE-BLOCK markers define the editable region."""
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this code!")
    # EVOLVE-BLOCK-END
EOF

# ── evaluate.py ─────────────────────────────────────────────────────────
cat > "$TASK_DIR/evaluate.py" << 'EVALEOF'
"""Evaluator for the generated code.

Score: sigmoid-normalized throughput ratio vs a reference implementation.
0.5 = equal to reference, 0.75 = 3x faster, 0.9 = 9x faster.
No hard ceiling — the evolution loop can always detect improvement.

Edit the REFERENCE and benchmark sections to match your task.
"""

import time

# ── Reference implementation (edit to match your function signature) ───
_REFERENCE_SOURCE = """
def solve(input_data):
    # A simple, correct implementation. Replace with your own reference.
    return input_data
"""

_ref_ns = {}
exec(compile(_REFERENCE_SOURCE, "<reference>", "exec"), _ref_ns)
REF_FN = _ref_ns["solve"]


def evaluate(code_str: str) -> dict:
    ns = {}
    try:
        exec(compile(code_str, "<eval>", "exec"), ns)
    except Exception as e:
        return {
            "score": 0.0, "passed": False,
            "feedback": f"Syntax error: {type(e).__name__}: {e}",
            "metrics": {}, "artifacts": {},
        }

    fn = ns.get("solve")
    if fn is None:
        return {
            "score": 0.0, "passed": False,
            "feedback": "Function 'solve' not found in generated code.",
            "metrics": {}, "artifacts": {},
        }
    if not callable(fn):
        return {
            "score": 0.0, "passed": False,
            "feedback": "'solve' is not callable.",
            "metrics": {}, "artifacts": {},
        }

    # ── Correctness tests ──────────────────────────────────────────
    # Replace with real test cases:
    #   assert fn(0) == 0, "test case 1"
    #   assert fn(5) == 10, "test case 2"
    test_passed = True
    test_feedback = "All tests passed."
    try:
        # Example: remove this and add real tests
        pass
    except AssertionError as e:
        return {
            "score": 0.0, "passed": False,
            "feedback": f"Test failed: {e}",
            "metrics": {}, "artifacts": {},
        }
    except Exception as e:
        return {
            "score": 0.0, "passed": False,
            "feedback": f"Test raised {type(e).__name__}: {e}",
            "metrics": {}, "artifacts": {},
        }

    # ── Performance benchmark ──────────────────────────────────────
    # Edit the benchmark inputs and iterations for your task.
    n_warmup = 100
    n_trials = 2000

    # User code benchmark
    for _ in range(n_warmup):
        fn(42)
    t0 = time.perf_counter()
    for _ in range(n_trials):
        fn(42)
    user_elapsed = time.perf_counter() - t0

    # Reference benchmark
    for _ in range(n_warmup):
        REF_FN(42)
    t0 = time.perf_counter()
    for _ in range(n_trials):
        REF_FN(42)
    ref_elapsed = time.perf_counter() - t0

    speedup = ref_elapsed / user_elapsed if user_elapsed > 0 else 0
    # Sigmoid normalization: 0.5 = equal to reference, no ceiling
    score = round(speedup / (speedup + 1.0), 6)

    return {
        "score": score,
        "passed": True,
        "feedback": (
            f"{test_feedback} "
            f"Speed: {n_trials/user_elapsed:,.0f} calls/sec "
            f"(ref: {n_trials/ref_elapsed:,.0f}, ratio: {speedup:.3f}). "
            f"Score: {score:.4f}"
        ),
        "metrics": {
            "calls_per_sec": round(n_trials / user_elapsed, 2),
            "ref_calls_per_sec": round(n_trials / ref_elapsed, 2),
            "speed_ratio": round(speedup, 4),
        },
        "artifacts": {},
    }
EVALEOF

# ── program.md ──────────────────────────────────────────────────────────
cat > "$TASK_DIR/program.md" << 'EOF'
# Task: Replace this heading with a description

Describe what the function should do, its inputs/outputs, and any
performance considerations. The first `# Heading` is used as the
task description for the LLM.

## Requirements
- Edge cases to handle
- Performance targets
- Any constraints (e.g., O(n) time, no imports)

## Optimization ladder (approximate scores)
A score of 0.5 = equal to the reference implementation.
Higher is better and there is no upper ceiling on improvement.

- Naive approach: ~0.2–0.4
- Optimized approach: ~0.5–0.8
- Expert approach: ~0.8–0.95
- State-of-the-art: >0.95

## Tips
- Start with a correct implementation, then optimize
- Consider algorithmic improvements before micro-optimizations
- Use Python's built-in functions and libraries where possible
EOF

echo "✓ Created task in $TASK_DIR/"
echo "  Edit $TASK_DIR/program.md        — set the task description"
echo "  Edit $TASK_DIR/evaluate.py       — wire up reference, tests, benchmarks"
echo "  Run:  verigen run $TASK_DIR/"
echo ""
echo "  Advanced options:"
echo "    --strategy beam    (explore top-K candidates)"
echo "    --mutation-mode focused  (mutate only the EVOLVE-BLOCK region)"
echo "    -q                 (quiet mode, suppress live progress)"
