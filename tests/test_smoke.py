"""Smoke test for verigen core components (no LLM required)."""

import tempfile
from pathlib import Path

from verigen.task.evolve_block import extract_block, replace_block
from verigen.core.evaluator import EvaluationResult, evaluate_in_sandbox


SAMPLE_TEMPLATE = """def is_palindrome(s: str) -> bool:
    # EVOLVE-BLOCK-START
    # Write your implementation
    raise NotImplementedError()
    # EVOLVE-BLOCK-END
"""

SAMPLE_IMPL = """def is_palindrome(s: str) -> bool:
    # EVOLVE-BLOCK-START
    cleaned = ""
    for c in s.lower():
        if c.isalnum():
            cleaned += c
    return cleaned == cleaned[::-1]
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


def test_replace_block():
    """Replace code between EVOLVE-BLOCK markers."""
    new_block = '''cleaned = ""
    for c in s.lower():
        if c.isalnum():
            cleaned += c
    return cleaned == cleaned[::-1]'''
    result = replace_block(SAMPLE_TEMPLATE, new_block)
    assert "# EVOLVE-BLOCK-START" in result
    assert "# EVOLVE-BLOCK-END" in result
    assert "cleaned = \"\"" in result
    assert "raise NotImplementedError()" not in result


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
        wrong_code = """def is_palindrome(s):
    return False
"""
        result = evaluate_in_sandbox(str(eval_path), wrong_code, timeout=10)
        assert result.passed is False, f"Expected passed=False, got {result}"


def test_replace_block_preserves_indentation():
    """The replaced block should match the original indentation level."""
    template = """def foo():
    # EVOLVE-BLOCK-START
    pass
    # EVOLVE-BLOCK-END
"""
    new_block = "return 42"
    result = replace_block(template, new_block)
    lines = result.splitlines()
    # The return statement should be indented
    assert "    return 42" in result, f"Expected indented return, got:\n{result}"
