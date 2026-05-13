"""Evaluator for the palindrome task.

Exports evaluate(code_str) -> dict that maps to EvaluationResult fields.
"""

import time
import string


_REFERENCE_PALINDROME = """
def is_palindrome(s):
    s = ''.join(c.lower() for c in s if c.isalnum())
    return s == s[::-1]
"""

_ref_ns = {}
exec(_REFERENCE_PALINDROME, _ref_ns)
_REF_FN = _ref_ns["is_palindrome"]


def evaluate(code_str: str) -> dict:
    """Test the is_palindrome function and measure its performance.

    Returns a dict with keys: score, passed, feedback, metrics, artifacts.
    """
    namespace = {}
    try:
        exec(code_str, namespace)
    except Exception as e:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": f"Syntax error or import error: {type(e).__name__}: {e}",
            "metrics": {},
            "artifacts": {},
        }

    if "is_palindrome" not in namespace:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": "Function is_palindrome is not defined in the generated code.",
            "metrics": {},
            "artifacts": {},
        }

    is_palindrome = namespace["is_palindrome"]

    if not callable(is_palindrome):
        return {
            "score": 0.0,
            "passed": False,
            "feedback": "is_palindrome is not callable.",
            "metrics": {},
            "artifacts": {},
        }

    # ── Correctness tests ──────────────────────────────────────────────
    test_cases = [
        ("", True),
        ("a", True),
        ("racecar", True),
        ("A man a plan a canal Panama", True),
        ("No 'x' in Nixon", True),
        ("Was it a car or a cat I saw", True),
        ("hello", False),
        ("world", False),
        ("Python", False),
        ("Madam, in Eden, I'm Adam", True),
    ]

    errors = []
    for s, expected in test_cases:
        try:
            result = is_palindrome(s)
            if result != expected:
                errors.append(f"is_palindrome({s!r}) returned {result}, expected {expected}")
        except Exception as e:
            errors.append(f"is_palindrome({s!r}) raised {type(e).__name__}: {e}")

    if errors:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": "Test failures:\n" + "\n".join(errors),
            "metrics": {"n_errors": len(errors)},
            "artifacts": {},
        }

    # ── Performance benchmark ──────────────────────────────────────────
    benchmark_strings = [
        "A man a plan a canal Panama",
        "No 'x' in Nixon",
        "Was it a car or a cat I saw",
        "Madam, in Eden, I'm Adam",
        "hello",
        "python",
    ]

    n_trials = 3000
    start = time.perf_counter()
    for _ in range(n_trials):
        for t in benchmark_strings:
            is_palindrome(t)
    calls = n_trials * len(benchmark_strings)
    user_elapsed = time.perf_counter() - start

    # Reference
    start = time.perf_counter()
    for _ in range(n_trials):
        for t in benchmark_strings:
            _REF_FN(t)
    ref_elapsed = time.perf_counter() - start

    speedup = ref_elapsed / user_elapsed if user_elapsed > 0 else 0
    # Score: sigmoid normalization. 0.5 = equal to reference, no hard ceiling.
    score = round(speedup / (speedup + 1.0), 6)

    return {
        "score": score,
        "passed": True,
        "feedback": (
            f"All {len(test_cases)} tests passed. "
            f"Speed: {calls/user_elapsed/1000000:.1f}M calls/sec "
            f"(ref: {calls/ref_elapsed/1000000:.1f}M, ratio: {speedup:.3f}). "
            f"Score: {score:.4f}"
        ),
        "metrics": {
            "calls_per_sec": round(calls / user_elapsed, 2),
            "ref_calls_per_sec": round(calls / ref_elapsed, 2),
            "speed_ratio": round(speedup, 4),
            "n_tests": len(test_cases),
        },
        "artifacts": {},
    }
