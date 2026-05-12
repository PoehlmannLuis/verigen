"""Regular expression matcher — correctness tests + latency benchmark.

Pattern supports `.` (any char), `*` (zero or more of preceding),
`?` (zero or one of preceding). Score: throughput vs a reference DP-based
matcher. Tests cover basic matching, quantifiers, edge cases, and
pathological patterns that would be slow with backtracking.
"""

import time
import re as _re


def _reference_match(pattern, string):
    """Convert our simple regex to Python re and match the full string.

    Pattern supports: `.` (any char), `*` (zero+ preceding), `?` (0-1 preceding).
    """
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == '.':
            out.append('[^]')   # any char including newline
        elif c == '*' or c == '?':
            out.append(c)
        elif c == '\\' and i + 1 < len(pattern):
            out.append(_re.escape(pattern[i + 1]))
            i += 1
        else:
            out.append(_re.escape(c))
        i += 1
    return bool(_re.match('^' + ''.join(out) + '$', string))


def evaluate(code_str: str) -> dict:
    ns = {}
    try:
        exec(compile(code_str, "<eval>", "exec"), ns)
    except Exception as e:
        return {"score": 0.0, "passed": False, "feedback": f"Syntax error: {e}", "metrics": {}, "artifacts": {}}

    fn = ns.get("regex_match")
    if fn is None:
        return {"score": 0.0, "passed": False, "feedback": "regex_match not defined", "metrics": {}, "artifacts": {}}

    # ── Correctness tests ──────────────────────────────────────────
    tests = [
        # (pattern, string, expected)
        # Basic literal
        ("abc", "abc", True),
        ("abc", "ab", False),
        ("abc", "abcd", False),
        ("", "", True),
        ("", "a", False),

        # Dot
        ("a.c", "abc", True),
        ("a.c", "ac", False),
        (".", "x", True),
        (".", "", False),
        ("...", "abc", True),
        ("...", "ab", False),

        # Star
        ("a*", "", True),
        ("a*", "a", True),
        ("a*", "aaaa", True),
        ("a*", "b", False),
        ("ab*c", "ac", True),
        ("ab*c", "abc", True),
        ("ab*c", "abbbbc", True),
        ("ab*c", "abdc", False),

        # Question mark
        ("a?", "", True),
        ("a?", "a", True),
        ("a?", "aa", False),
        ("ab?c", "ac", True),
        ("ab?c", "abc", True),
        ("ab?c", "abbc", False),

        # Combinations
        (".*", "", True),
        (".*", "anything", True),
        ("a.*b", "axxxb", True),
        ("a.*b", "ab", True),
        ("a.*b", "axb", True),

        # Mixed quantifiers
        ("a*b*c*", "aabbcc", True),
        ("a*b*c*", "abc", True),
        ("a*b*c*", "", True),
        ("a*b*c*", "def", False),

        # Dot with star
        (".*abc.*", "xxxabcyyy", True),
        (".*abc.*", "xxxab", False),

        # Question mark before star
        ("ab?c*", "a", True),
        ("ab?c*", "abc", True),
        ("ab?c*", "abccc", True),
        ("ab?c*", "accc", True),

        # Multiple dots
        ("a..b", "aXXb", True),
        ("a..b", "aXb", False),

        # Star with no preceding char
        ("*abc", "abc", False),  # * at start invalid, should not crash
        ("abc*def", "abcdeff", False),

        # Edge: pattern longer than string
        ("abcde", "abc", False),

        # Edge: string longer than pattern
        ("abc", "abcdef", False),

        # Complex alternation-like (via .*)
        ("a.*b.*c", "aXXXbXXXc", True),
        ("a.*b.*c", "aXXXc", False),

        # Quantifiers on dot
        (".*", "any length string at all", True),
        (".?", "a", True),
        (".?", "", True),
        (".?", "ab", False),

        # Consecutive quantifiers
        ("a?b?c?", "", True),
        ("a?b?c?", "a", True),
        ("a?b?c?", "ab", True),
        ("a?b?c?", "abc", True),
        ("a?b?c?", "ac", True),
        ("a?b?c?", "bc", True),
        ("a?b?c?", "abb", False),

        # Multiple stars
        ("a*a*", "aaaa", True),
        ("a*a*", "", True),
        ("a*a*", "b", False),

        # Alternating star patterns (pathological for backtracking)
        ("a*a*a*a*a*b", "aaaaaaaaaaaaaaaaac", False),
        ("a*a*a*a*a*b", "aaaaaaaaaaaaaaaaab", True),
    ]

    failed = []
    for pat, s, expected in tests:
        try:
            result = fn(pat, s)
            if result != expected:
                failed.append(f"match({pat!r}, {s!r}) = {result}, expected {expected}")
        except Exception as e:
            # If it crashes on invalid patterns like "*abc", that's acceptable
            if expected is not False:
                failed.append(f"match({pat!r}, {s!r}) raised {e}")

    if failed:
        msg = "; ".join(failed[:5])
        return {"score": 0.0, "passed": False, "feedback": f"{len(failed)} failures: {msg}", "metrics": {}, "artifacts": {}}

    # ── Latency benchmark ──────────────────────────────────────────
    bench_cases = [
        ("abc", "abc"),
        ("a.b.c", "axbxc"),
        ("a*", "aaaaaaa"),
        (".*", "some random string here"),
        ("a*b*c*", "aaabbbccc"),
        ("a.*b.*c", "aXbYc"),
        ("a?b?c?", "abc"),
        ("ab*c*d*e*", "abbbcccde"),
        (".*a.*b.*c.*", "xxxxaxxxbxxxcxxx"),
        # Pathological for backtracking
        ("a*a*a*a*a*b", "aaaaaaaaaaaaaaaaab"),
    ]

    # Warmup
    N_PER = 2000
    for _ in range(100):
        for pat, s in bench_cases:
            fn(pat, s)

    t0 = time.perf_counter()
    for _ in range(N_PER):
        for pat, s in bench_cases:
            fn(pat, s)
    user_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(N_PER):
        for pat, s in bench_cases:
            _reference_match(pat, s)
    ref_elapsed = time.perf_counter() - t0

    speedup = ref_elapsed / user_elapsed if user_elapsed > 0 else 0
    score = min(speedup, 1.0)

    feedback = (
        f"All {len(tests)} tests passed. "
        f"Speed: {N_PER*len(bench_cases)/user_elapsed:,.0f} matches/sec "
        f"(ref: {N_PER*len(bench_cases)/ref_elapsed:,.0f}, ratio: {speedup:.3f}). "
        f"Score: {score:.4f}"
    )

    return {
        "score": score,
        "passed": True,
        "feedback": feedback,
        "metrics": {
            "matches_per_sec": N_PER * len(bench_cases) / user_elapsed,
            "ref_matches_per_sec": N_PER * len(bench_cases) / ref_elapsed,
            "speed_ratio": speedup,
        },
        "artifacts": {},
    }
