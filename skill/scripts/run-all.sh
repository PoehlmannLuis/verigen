#!/usr/bin/env bash
# Run verigen evolution on all examples/tasks, or a subset.
# Useful for smoke-testing after changes, or batch running.
#
# Usage:
#   ./skill/scripts/run-all.sh                           # Run all tasks
#   ./skill/scripts/run-all.sh examples/ tasks/palindrome  # Run specific tasks
#   MODELS="openai/gpt-4o,ollama_chat/qwen3.6" ./skill/scripts/run-all.sh
#

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_DIR="$(cd "$SKILL_DIR/.." && pwd)"

DEFAULT_TASKS=(
    "examples/palindrome"
    "tasks/game_of_life"
    "tasks/levenshtein"
    "tasks/lru_cache"
    "tasks/regex_match"
    "tasks/topological_sort"
)

MODELS="${MODELS:-auto}"
MAX_ITERATIONS="${MAX_ITERATIONS:-15}"
TIMEOUT="${TIMEOUT:-30}"

if [ $# -gt 0 ]; then
    TASKS=("$@")
else
    TASKS=("${DEFAULT_TASKS[@]}")
fi

echo "=== verigen: running ${#TASKS[@]} tasks ==="
echo "  models:       $MODELS"
echo "  max-iters:    $MAX_ITERATIONS"
echo "  timeout:      ${TIMEOUT}s"
echo ""

for task_dir in "${TASKS[@]}"; do
    abs_task="$REPO_DIR/$task_dir"
    if [ ! -d "$abs_task" ]; then
        echo "⚠ Skip: $task_dir (not found)"
        continue
    fi

    echo "─── $task_dir ────────────────────────────────"

    model_flag=""
    if [ "$MODELS" != "auto" ]; then
        model_flag="--model $MODELS"
    fi

    cd "$REPO_DIR"
    if verigen run "$abs_task" \
        --max-iterations "$MAX_ITERATIONS" \
        --timeout "$TIMEOUT" \
        $model_flag 2>&1; then
        echo "✓ $task_dir: success"
    else
        echo "✗ $task_dir: failed (exit $?)"
    fi
    echo ""
done

echo "=== Done ==="
