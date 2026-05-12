"""Integration test that runs the full verigen pipeline with the LLM."""

import json
import os
import tempfile
from pathlib import Path

import dspy
import pytest

from verigen import VerifiableCodeGen, load_task, EvaluationResult

# Skip if no LLM is available
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("VERIGEN_TEST_LLM"),
        reason="Set VERIGEN_TEST_LLM=1 to run LLM-dependent integration tests",
    ),
]


SIMPLE_TEMPLATE = """def double(n: int) -> int:
    # EVOLVE-BLOCK-START
    raise NotImplementedError()
    # EVOLVE-BLOCK-END
"""

SIMPLE_EVALUATOR = """
def evaluate(code_str: str) -> dict:
    ns = {}
    exec(code_str, ns)
    fn = ns.get("double")
    if fn is None:
        return {"score": 0.0, "passed": False, "feedback": "double not defined", "metrics": {}, "artifacts": {}}
    passed = fn(5) == 10 and fn(0) == 0 and fn(-3) == -6
    return {
        "score": 1.0 if passed else 0.0,
        "passed": passed,
        "feedback": "ok" if passed else "wrong result",
        "metrics": {},
        "artifacts": {},
    }
"""


@pytest.fixture(scope="module")
def lm():
    """Configure DSPy with local llama-server."""
    lm = dspy.LM(
        model="openai/Qwen3.6-35B-A3B-UD-IQ2_M.gguf",
        api_base="http://localhost:8080/v1",
        api_key="not-needed",
    )
    dspy.configure(lm=lm)
    # Also try to detect if the model is actually reachable
    try:
        lm("ping")
        return lm
    except Exception:
        pytest.skip("LLM not reachable, skipping integration tests")


def test_evolution_finds_correct_solution(tmp_path: Path, lm):
    """Run a full evolution on a simple task and verify the output works."""
    # Create task directory
    task_dir = tmp_path / "double_task"
    task_dir.mkdir()
    (task_dir / "initial.py").write_text(SIMPLE_TEMPLATE)
    (task_dir / "evaluate.py").write_text(SIMPLE_EVALUATOR)
    (task_dir / "program.md").write_text("# Implement double(n) -> int that returns n * 2")

    task = load_task(str(task_dir), timeout=15)
    gen = VerifiableCodeGen(max_iterations=3)

    result = gen(task)

    # The best code should compile and pass tests
    assert result.best_code is not None
    assert result.best_score > 0.0, f"Expected score > 0, got {result.best_score}"
    assert len(result.trace.entries) >= 1

    # Verify the code actually works
    ns = {}
    exec(compile(result.best_code, "<test>", "exec"), ns)
    assert ns.get("double")(5) == 10
    assert ns.get("double")(0) == 0
    assert ns.get("double")(-3) == -6


def test_trace_is_persistent(tmp_path: Path, lm):
    """Run a short evolution and verify trace logging works."""
    task_dir = tmp_path / "trace_test"
    task_dir.mkdir()
    (task_dir / "initial.py").write_text(SIMPLE_TEMPLATE)
    (task_dir / "evaluate.py").write_text(SIMPLE_EVALUATOR)
    (task_dir / "program.md").write_text("# double")

    from verigen import VerifiableCodeGen, load_task

    task = load_task(str(task_dir), timeout=15)
    gen = VerifiableCodeGen(max_iterations=2)
    result = gen(task)

    # Save and reload trace
    trace_path = tmp_path / "trace.jsonl"
    result.trace.save(trace_path)

    from verigen import TraceLogger
    reloaded = TraceLogger.from_jsonl(trace_path)
    assert len(reloaded.entries) == len(result.trace.entries)
    assert reloaded.best_score == result.best_score
