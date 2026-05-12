"""Smoke test for verigen core components (no LLM required)."""

import json
import tempfile
import warnings
from pathlib import Path

import pytest

from verigen.task.evolve_block import extract_block, replace_block
from verigen.core.evaluator import EvaluationResult, evaluate_in_sandbox
from verigen.core.trace import TraceLogger, TraceEntry
from verigen.task.loader import TaskSpec, make_task, load_task


SAMPLE_TEMPLATE = """def is_palindrome(s: str) -> bool:
    # EVOLVE-BLOCK-START
    # Write your implementation
    raise NotImplementedError()
    # EVOLVE-BLOCK-END
"""

SAMPLE_EVALUATOR = """
def evaluate(code_str: str) -> dict:
    ns = {}
    exec(code_str, ns)
    fn = ns.get("is_palindrome")
    if fn is None:
        return {"score": 0.0, "passed": False, "feedback": "missing fn", "metrics": {}, "artifacts": {}}
    passed = fn("racecar") == True and fn("hello") == False
    return {
        "score": 1.0 if passed else 0.0,
        "passed": passed,
        "feedback": "ok" if passed else "failed",
        "metrics": {},
        "artifacts": {},
    }
"""


def test_extract_block():
    """Extract code between EVOLVE-BLOCK markers."""
    block = extract_block(SAMPLE_TEMPLATE)
    assert block is not None
    assert "Write your implementation" in block
    assert "raise NotImplementedError" in block


def test_replace_block_deprecated():
    """replace_block is deprecated; it emits a warning and returns new_code as-is."""
    new_code = "def foo(): return 42"
    with pytest.warns(DeprecationWarning):
        result = replace_block("irrelevant", new_code)
    assert result == new_code


def test_taskspec_program_context():
    """TaskSpec now carries program_context as a required field."""
    spec = TaskSpec(
        description="Test task",
        program_context="# Test\n\nSome detailed instructions.",
        template=SAMPLE_TEMPLATE,
        eval_module_path="/fake/evaluate.py",
        evaluate_fn=lambda code: EvaluationResult(score=1.0, passed=True),
    )
    assert spec.description == "Test task"
    assert "detailed instructions" in spec.program_context


def test_make_task_with_program_context():
    """make_task accepts and forwards program_context."""
    spec = make_task(
        description="Foo",
        template=SAMPLE_TEMPLATE,
        eval_code=SAMPLE_EVALUATOR,
        program_context="# Custom task\n\nExtra context.",
    )
    assert spec.program_context == "# Custom task\n\nExtra context."


def test_taskspec_requires_program_context():
    """TaskSpec fields match load_task output — program_context is mandatory."""
    spec = TaskSpec(
        description="d",
        program_context="ctx",
        template=SAMPLE_TEMPLATE,
        eval_module_path="/fake",
        evaluate_fn=lambda c: EvaluationResult(),
    )
    # All fields present; no extract_block/replace_block methods
    assert not hasattr(spec, "extract_block")
    assert not hasattr(spec, "replace_block")


def test_evaluation_result_construction():
    """EvaluationResult can be constructed and its fields accessed."""
    r = EvaluationResult(score=0.95, passed=True, feedback="ok", metrics={"x": 1.0})
    assert r.score == 0.95
    assert r.passed is True
    assert r.feedback == "ok"
    assert r.metrics["x"] == 1.0


def test_evaluate_in_sandbox():
    """Run a simple evaluator in a subprocess and get results."""
    with tempfile.TemporaryDirectory() as tmp:
        eval_path = Path(tmp) / "evaluate.py"
        eval_path.write_text(SAMPLE_EVALUATOR)

        # First test: correct implementation
        correct_code = """def is_palindrome(s):
    s = ''.join(c.lower() for c in s if c.isalnum())
    return s == s[::-1]
"""
        result = evaluate_in_sandbox(str(eval_path), correct_code, timeout=10)
        assert result.passed is True, f"Expected passed=True, got {result}"
        assert result.score > 0

        # Second test: incorrect implementation
        wrong_code = "def is_palindrome(s): return False"
        result = evaluate_in_sandbox(str(eval_path), wrong_code, timeout=10)
        assert result.passed is False, f"Expected passed=False, got {result}"


def test_trace_logger_save_no_double_newline():
    """save() writes exactly one trailing newline, not two."""
    logger = TraceLogger()
    logger.record(TraceEntry(
        iteration=0, phase="initial", block_code="x", score=1.0,
        passed=True, feedback="ok",
    ))
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        logger.save(path)
        content = Path(path).read_text()
        # Should end with a single newline, not double
        lines = content.rstrip("\n").split("\n")
        assert len(lines) == 1
        # Parse the JSON line
        entry = json.loads(lines[0])
        assert entry["iteration"] == 0
        assert entry["phase"] == "initial"
    finally:
        Path(path).unlink(missing_ok=True)


def test_trace_logger_to_jsonl():
    """to_jsonl returns a single trailing newline."""
    logger = TraceLogger()
    logger.record(TraceEntry(
        iteration=0, phase="initial", block_code="x", score=1.0,
        passed=True, feedback="ok",
    ))
    logger.record(TraceEntry(
        iteration=1, phase="mutate", block_code="y", score=0.8,
        passed=True, feedback="ok2",
    ))
    result = logger.to_jsonl()
    # For 2 entries: join produces "line1\nline2" — 1 newline between, 0 trailing
    assert result.count("\n") == 1
    assert not result.endswith("\n\n")
