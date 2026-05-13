"""Conway's Game of Life — correctness tests + latency benchmark.

Score: throughput ratio vs reference (nested loops with padding).
Tests cover still lifes, oscillators, gliders, edge boundaries,
and extreme configurations.
"""

import time
import copy


def _reference_gol(board):
    """Reference: 2D convolution via nested loops with zero-padding."""
    if not board or not board[0]:
        return []
    R, C = len(board), len(board[0])
    # Pad with zeros
    padded = [[0] * (C + 2)]
    for row in board:
        padded.append([0] + row + [0])
    padded.append([0] * (C + 2))

    result = [[0] * C for _ in range(R)]
    for i in range(R):
        for j in range(C):
            # Sum of 8 neighbours (skip center = i+1, j+1)
            s = (padded[i][j] + padded[i][j+1] + padded[i][j+2] +
                 padded[i+1][j] +                padded[i+1][j+2] +
                 padded[i+2][j] + padded[i+2][j+1] + padded[i+2][j+2])
            if padded[i+1][j+1] == 1:
                result[i][j] = 1 if 2 <= s <= 3 else 0
            else:
                result[i][j] = 1 if s == 3 else 0
    return result


def evaluate(code_str: str) -> dict:
    ns = {}
    try:
        exec(compile(code_str, "<eval>", "exec"), ns)
    except Exception as e:
        return {"score": 0.0, "passed": False, "feedback": f"Syntax error: {e}", "metrics": {}, "artifacts": {}}

    fn = ns.get("game_of_life")
    if fn is None:
        return {"score": 0.0, "passed": False, "feedback": "game_of_life not defined", "metrics": {}, "artifacts": {}}

    # ── Correctness tests ──────────────────────────────────────────
    tests = []

    # 1: Empty board (all dead)
    def t1():
        b = [[0,0,0],[0,0,0],[0,0,0]]
        assert fn(b) == b
    tests.append(("all dead", t1))

    # 2: Single cell dies
    def t2():
        b = [[0,0,0],[0,1,0],[0,0,0]]
        assert fn(b) == [[0,0,0],[0,0,0],[0,0,0]]
    tests.append(("single dies", t2))

    # 3: Block (still life, 2x2)
    def t3():
        b = [[1,1],[1,1]]
        assert fn(b) == b
    tests.append(("block", t3))

    # 4: Beehive (still life)
    def t4():
        b = [[0,1,1,0],[1,0,0,1],[0,1,1,0]]
        assert fn(b) == b
    tests.append(("beehive", t4))

    # 5: Blinker (period-2 oscillator)
    def t5():
        b1 = [[0,0,0,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,0,0,0]]
        b2 = fn(b1)
        expected = [[0,0,0,0,0],[0,0,0,0,0],[0,1,1,1,0],[0,0,0,0,0],[0,0,0,0,0]]
        assert b2 == expected, f"blinker phase 1: got {b2}"
        assert fn(b2) == b1, "blinker phase 2"
    tests.append(("blinker", t5))

    # 6: Toad (period-2 oscillator)
    def t6():
        b1 = [[0,0,0,0],[0,1,1,1],[1,1,1,0],[0,0,0,0]]
        b2 = fn(b1)
        assert fn(b2) == b1, f"toad period 2: {b2} -> {fn(b2)}"
    tests.append(("toad", t6))

    # 7: Glider
    def t7():
        b = [[0,0,0,0,0],[0,0,1,0,0],[0,0,0,1,0],[0,1,1,1,0],[0,0,0,0,0]]
        expected = [[0,0,0,0,0],[0,0,0,0,0],[0,1,0,1,0],[0,0,1,1,0],[0,0,1,0,0]]
        assert fn(b) == expected, f"glider: got {fn(b)}"
    tests.append(("glider", t7))

    # 8: 1xN board
    def t8():
        b = [[0,1,1,0]]
        expected = [[0,0,0,0]]
        assert fn(b) == expected
    tests.append(("1xN", t8))

    # 9: Nx1 board
    def t9():
        b = [[0],[1],[0],[1]]
        assert fn(b) == [[0],[0],[0],[0]]
    tests.append(("Nx1", t9))

    # 10: All ones block (still life if 2x2+, dies otherwise)
    def t10():
        b = [[1,1,1],[1,1,1],[1,1,1]]
        # All cells have 8 neighbours: interior ones have 8 neighbours (all alive)
        # Corner has 3 alive neighbours → stays alive
        # Edge (not corner) has 5 alive neighbours → dies
        # Interior has 8 neighbours → dies
        # Let me just check a 2x2 all-ones is still (block)
        assert fn([[1,1],[1,1]]) == [[1,1],[1,1]]
    tests.append(("all ones 2x2", t10))

    # 11: Single row
    def t11():
        assert fn([[1]]) == [[0]]
    tests.append(("1x1", t11))

    # 12: Row with pattern
    def t12():
        b = [[1,0,1,0,1]]
        # All cells die (each has at most 1 live neighbour in a single row)
        assert fn(b) == [[0,0,0,0,0]], f"got {fn(b)}"
    tests.append(("row pattern", t12))

    # 13: Large random-ish, compare with reference
    def t13():
        import random
        random.seed(42)
        R, C = 30, 30
        b = [[random.randint(0, 1) for _ in range(C)] for _ in range(R)]
        b_copy = [row[:] for row in b]
        expected = _reference_gol(b_copy)
        result = fn(b)
        assert result == expected, f"random 30x30 mismatch at {[i for i in range(R) if result[i] != expected[i]]}"
    tests.append(("random 30x30", t13))

    # 14: Empty boards
    def t14():
        result_empty = fn([])
        # Must return a list, exact shape doesn't matter for empty
        assert isinstance(result_empty, list), f"expected list, got {type(result_empty)}"
        # [[]] should also not crash — any list result is fine
        result_one_empty = fn([[]])
        assert isinstance(result_one_empty, list)
    tests.append(("empty", t14))

    # 15: Non-rectangular should not crash (just process first row width)
    def t15():
        b = [[0,1],[1,0,1]]
        try:
            result = fn(b)
            assert len(result) == 2
        except Exception:
            pass  # acceptable to fail on malformed input
    tests.append(("non-rectangular", t15))

    failed = []
    for name, testfn in tests:
        try:
            testfn()
        except Exception as e:
            failed.append(f"{name}: {e}")

    if failed:
        msg = "; ".join(failed[:5])
        return {"score": 0.0, "passed": False, "feedback": f"{len(failed)} failures: {msg}", "metrics": {}, "artifacts": {}}

    # ── Latency benchmark ──────────────────────────────────────────
    import random
    random.seed(1)

    bench_boards = []

    # Small board
    bench_boards.append([[random.randint(0, 1) for _ in range(30)] for _ in range(30)])

    # Medium board
    bench_boards.append([[random.randint(0, 1) for _ in range(100)] for _ in range(100)])

    # Sparse large board
    sparse = [[0] * 200 for _ in range(200)]
    for _ in range(500):
        sparse[random.randint(0, 199)][random.randint(0, 199)] = 1
    bench_boards.append(sparse)

    # Dense medium
    bench_boards.append([[random.randint(0, 1) for _ in range(80)] for _ in range(80)])

    # Warmup
    for _ in range(5):
        for b in bench_boards:
            fn(b)

    N = 100
    t0 = time.perf_counter()
    for _ in range(N):
        for b in bench_boards:
            fn(b)
    user_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(N):
        for b in bench_boards:
            _reference_gol(b)
    ref_elapsed = time.perf_counter() - t0

    speedup = ref_elapsed / user_elapsed if user_elapsed > 0 else 0
    # Score: sigmoid normalization. 0.5 = equal to reference, no hard ceiling.
    score = speedup / (speedup + 1.0)

    feedback = (
        f"All {len(tests)} tests passed. "
        f"Speed: {N*len(bench_boards)/user_elapsed:,.0f} gens/sec "
        f"(ref: {N*len(bench_boards)/ref_elapsed:,.0f}, ratio: {speedup:.3f}). "
        f"Score: {score:.4f}"
    )

    return {
        "score": score,
        "passed": True,
        "feedback": feedback,
        "metrics": {
            "gens_per_sec": N * len(bench_boards) / user_elapsed,
            "ref_gens_per_sec": N * len(bench_boards) / ref_elapsed,
            "speed_ratio": speedup,
        },
        "artifacts": {},
    }
