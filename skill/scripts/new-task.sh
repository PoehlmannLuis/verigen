#!/usr/bin/env bash
# Scaffold a new verigen task in the current directory or given path.
#
# Usage:
#   ./skill/scripts/new-task.sh my-task
#   ./skill/scripts/new-task.sh tasks/custom-optimizer
#
# Creates:
#   <task-dir>/
#   ├── initial.py        # Template with EVOLVE-BLOCK markers
#   ├── evaluate.py       # Skeleton evaluator
#   └── program.md        # Task description placeholder

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

Must export evaluate(code_str: str) -> dict with keys:
    score, passed, feedback, metrics, artifacts
"""

import time


def evaluate(code_str: str) -> dict:
    """Test correctness and benchmark performance.

    Edit this to match the function signature and requirements in program.md.
    """
    ns = {}
    try:
        exec(code_str, ns)
    except Exception as e:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": f"Execution error: {type(e).__name__}: {e}",
            "metrics": {},
            "artifacts": {},
        }

    fn = ns.get("solve")
    if fn is None:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": "Function 'solve' not found in generated code.",
            "metrics": {},
            "artifacts": {},
        }

    if not callable(fn):
        return {
            "score": 0.0,
            "passed": False,
            "feedback": "'solve' is not callable.",
            "metrics": {},
            "artifacts": {},
        }

    # ── Correctness tests ──────────────────────────────────────────────
    # Example: assert fn(0) == 0, fn(1) == 2, fn(-1) == -2
    # Replace with actual test cases for this task.
    try:
        # assert fn(0) == 0, "Test case 1 failed"
        # assert fn(5) == 10, "Test case 2 failed"
        pass  # Remove this when you add tests
    except AssertionError as e:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": f"Test failed: {e}",
            "metrics": {},
            "artifacts": {},
        }
    except Exception as e:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": f"Test raised {type(e).__name__}: {e}",
            "metrics": {},
            "artifacts": {},
        }

    # ── Performance benchmark ──────────────────────────────────────────
    # Example: time 1000 calls and compute score based on latency
    n_trials = 1000
    t0 = time.perf_counter()
    for _ in range(n_trials):
        fn(42)  # Use representative input
    elapsed = time.perf_counter() - t0
    avg_us = (elapsed / n_trials) * 1_000_000

    # Score: 1.0 at 0µs, 0.0 at >= 1000µs — tune the denominator to your task
    score = max(0.0, min(1.0, 1.0 - avg_us / 1000.0))

    return {
        "score": round(score, 6),
        "passed": True,
        "feedback": (
            f"All tests passed. "
            f"Avg {avg_us:.1f}µs per call over {n_trials} trials. "
            f"Score: {score:.4f}"
        ),
        "metrics": {
            "avg_latency_us": round(avg_us, 2),
            "n_trials": n_trials,
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

## Tips
- What algorithm or approach to consider
- Edge cases to handle
- Performance targets

## Score ladder (approximate)
- Naive approach: ~0.2–0.4
- Optimized approach: ~0.5–0.8
- Expert approach: ~0.8–1.0
EOF

echo "✓ Created task in $TASK_DIR/"
echo "  Edit $TASK_DIR/program.md  — set the task description"
echo "  Edit $TASK_DIR/evaluate.py — wire up tests + benchmarks"
echo "  Run:  verigen run $TASK_DIR/"
