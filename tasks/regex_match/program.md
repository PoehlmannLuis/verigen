# Regular expression matcher

Implement `regex_match(pattern: str, string: str) -> bool` that returns
True if the pattern matches the **entire** string.

Supported operators:
- `.` — any single character (including newline)
- `*` — zero or more of the preceding character
- `?` — zero or one of the preceding character

No anchors, no character classes, no groups, no escaping. `*` and `?`
at the start of the pattern (valid syntax) should match literally.

The evaluator runs 60+ test cases covering basic matching, quantifiers,
edge cases, and pathological patterns (e.g., `a*a*a*a*a*b` against long
strings). All must pass. Score is throughput ratio against a reference
Python `re`-based matcher.

This is the hardest task in the set. The recursive backtracking approach
is straightforward but catastrophically slow on pathological patterns.
A DP-based matcher (O(mn)) is much more consistent.

## Optimization ladder (approx scores)
- Recursive backtracking: ~0.1–0.4 (fails/crashes on pathological patterns)
- Memoized recursion: ~0.2–0.6
- Bottom-up DP (2D table): ~0.5–0.8
- Optimized DP (single row + early exit): ~0.8–1.0
