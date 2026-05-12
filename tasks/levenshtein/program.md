# Levenshtein edit distance

Implement `levenshtein(a: str, b: str) -> int` returning the Levenshtein
edit distance (minimum number of single-character insertions, deletions, or
substitutions) to transform string `a` into string `b`.

The evaluator runs 25 correctness test cases covering empty strings, full
matches, single-char differences, reversals, and longer strings. All must
pass. Then it benchmarks speed against a reference DP implementation across
5 string pairs (5000 iterations each).

Score is `calls/sec ÷ reference_calls/sec`, capped at 1.0. A score of 0.5
means half the reference speed; 1.0 means equal or faster.

## Optimization ladder (approx scores)
- Naive recursive: ~0.0 (fails on long strings or times out)
- Standard DP (2D list): ~0.3–0.5
- Single-row DP (1D list): ~0.6–0.9
- Single-row + micro-optimizations: ~0.9–1.0
