"""Levenshtein edit distance — correctness tests + latency benchmark.

Score: throughput-normalized to [0, 1] based on calls/sec relative to a
reference DP implementation. Tests cover empty strings, insertions,
deletions, substitutions, transpositions, and Unicode.
"""

import time
import sys


REFERENCE = """
def levenshtein(a, b):
    m, n = len(a), len(b)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[n]
"""

ns = {}
exec(REFERENCE, ns)
REF_FN = ns["levenshtein"]


def evaluate(code_str: str) -> dict:
    ns = {}
    try:
        exec(compile(code_str, "<eval>", "exec"), ns)
    except Exception as e:
        return {"score": 0.0, "passed": False, "feedback": f"Syntax error: {e}", "metrics": {}, "artifacts": {}}

    fn = ns.get("levenshtein")
    if fn is None:
        return {"score": 0.0, "passed": False, "feedback": "levenshtein function not defined", "metrics": {}, "artifacts": {}}

    # ── Correctness tests (all must pass) ──────────────────────────
    test_cases = [
        # (a, b, expected)
        ("", "", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("abc", "abc", 0),
        ("cat", "car", 1),
        ("sitting", "kitten", 3),
        ("hello", "world", 4),
        ("abcdef", "azced", 3),
        ("flaw", "lawn", 2),
        ("abcdef", "fedcba", 6),
        ("a" * 50, "a" * 50, 0),
        ("a" * 50, "b" * 50, 50),
        ("abcde", "abcd", 1),
        ("abcd", "abcde", 1),
        ("abc", "abcd", 1),
        ("abc", "dbc", 1),
        ("", "a", 1),
        ("a", "", 1),
        ("ab", "ba", 2),
        ("abcde", "edcba", 4),
        ("aaa", "aaa", 0),
        ("abcdefgh", "abcdefgh", 0),
        ("abcdefgh", "abcdefgi", 1),
        ("abc", "def", 3),
        ("aaa", "bbb", 3),
    ]

    failed = []
    for a, b, expected in test_cases:
        try:
            result = fn(a, b)
            if result != expected:
                failed.append(f"levenshtein({a!r}, {b!r}) = {result}, expected {expected}")
        except Exception as e:
            failed.append(f"levenshtein({a!r}, {b!r}) raised {e}")

    if failed:
        msg = "; ".join(failed[:5])
        return {"score": 0.0, "passed": False, "feedback": f"{len(failed)} failures: {msg}", "metrics": {}, "artifacts": {}}

    # ── Latency benchmark ──────────────────────────────────────────
    benchmark_pairs = [
        ("kitten", "sitting"),
        ("abcdefghij", "acbedgfihj"),
        ("hello world", "world hello"),
        ("a" * 100, "b" * 100),
        ("abcde" * 20, "edcba" * 20),    # length 100
    ]

    N = 5000
    # Warmup
    for _ in range(100):
        for a, b in benchmark_pairs:
            fn(a, b)

    t0 = time.perf_counter()
    for _ in range(N):
        for a, b in benchmark_pairs:
            fn(a, b)
    elapsed = time.perf_counter() - t0
    calls_per_sec = (N * len(benchmark_pairs)) / elapsed if elapsed > 0 else float("inf")

    # Reference
    t0 = time.perf_counter()
    for _ in range(N):
        for a, b in benchmark_pairs:
            REF_FN(a, b)
    ref_elapsed = time.perf_counter() - t0
    ref_cps = (N * len(benchmark_pairs)) / ref_elapsed if ref_elapsed > 0 else float("inf")

    # Score: ratio of our calls/sec to reference, capped at [0, 1]
    raw_ratio = calls_per_sec / ref_cps if ref_cps > 0 else 0
    score = min(raw_ratio, 1.0)

    feedback = (
        f"All {len(test_cases)} tests passed. "
        f"Speed: {calls_per_sec/1000000:.1f}M calls/sec "
        f"(ref: {ref_cps/1000000:.1f}M, ratio: {raw_ratio:.3f}). "
        f"Score: {score:.4f}"
    )

    return {
        "score": score,
        "passed": True,
        "feedback": feedback,
        "metrics": {
            "calls_per_sec": calls_per_sec,
            "ref_calls_per_sec": ref_cps,
            "speed_ratio": raw_ratio,
            "n_tests": len(test_cases),
        },
        "artifacts": {},
    }
