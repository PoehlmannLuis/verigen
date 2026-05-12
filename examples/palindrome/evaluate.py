"""Evaluator for the palindrome task.

Exports evaluate(code_str) -> dict that maps to EvaluationResult fields.
"""

import time
import string


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
    elapsed = time.perf_counter() - start
    calls = n_trials * len(benchmark_strings)
    avg_ns = (elapsed / calls) * 1e9  # nanoseconds per call

    # Score: 1.0 at 0ns, 0.0 at >=5000ns
    score = max(0.0, min(1.0, 1.0 - avg_ns / 5000.0))

    return {
        "score": round(score, 6),
        "passed": True,
        "feedback": (
            f"All {len(test_cases)} tests passed. "
            f"Avg {avg_ns:.1f}ns per call over {calls:,} calls. "
            f"Score: {score:.4f}"
        ),
        "metrics": {
            "avg_latency_ns": round(avg_ns, 2),
            "n_tests": len(test_cases),
        },
        "artifacts": {},
    }
