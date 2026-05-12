"""LRU Cache — correctness tests + throughput benchmark.

Score: throughput relative to a reference OrderedDict-based implementation.
Tests standard LRU eviction semantics, capacity boundaries, and update ordering.
"""

import time
from collections import OrderedDict as _OrderedDict


class _RefLRU:
    """Reference implementation using OrderedDict (move_to_end)."""
    def __init__(self, capacity):
        self.cap = capacity
        self._dict = _OrderedDict()

    def get(self, key):
        if key not in self._dict:
            return -1
        self._dict.move_to_end(key)
        return self._dict[key]

    def put(self, key, value):
        if key in self._dict:
            self._dict.move_to_end(key)
        self._dict[key] = value
        if len(self._dict) > self.cap:
            self._dict.popitem(last=False)


def evaluate(code_str: str) -> dict:
    ns = {}
    try:
        exec(compile(code_str, "<eval>", "exec"), ns)
    except Exception as e:
        return {"score": 0.0, "passed": False, "feedback": f"Syntax error: {e}", "metrics": {}, "artifacts": {}}

    if "LRUCache" not in ns:
        return {"score": 0.0, "passed": False, "feedback": "LRUCache not defined", "metrics": {}, "artifacts": {}}
    UserCache = ns["LRUCache"]

    # ── Correctness tests ──────────────────────────────────────────
    tests = []

    # Test 1: basic get/put
    def t1():
        c = UserCache(2)
        c.put(1, 1)
        c.put(2, 2)
        assert c.get(1) == 1, "get(1) after put"
        c.put(3, 3)  # evicts key 2
        assert c.get(2) == -1, "key 2 evicted"
        assert c.get(3) == 3
    tests.append(("basic eviction", t1))

    # Test 2: update existing key
    def t2():
        c = UserCache(2)
        c.put(1, 1)
        c.put(1, 2)
        assert c.get(1) == 2, "update replaces value"
    tests.append(("update value", t2))

    # Test 3: get updates recency
    def t3():
        c = UserCache(3)
        c.put(1, 1); c.put(2, 2); c.put(3, 3)
        c.get(1)      # 1 is now most recent
        c.put(4, 4)   # evicts 2
        assert c.get(2) == -1
        assert c.get(1) == 1
        assert c.get(4) == 4
    tests.append(("get updates recency", t3))

    # Test 4: capacity 1
    def t4():
        c = UserCache(1)
        c.put(1, 1)
        c.put(2, 2)
        assert c.get(1) == -1
        assert c.get(2) == 2
    tests.append(("capacity 1", t4))

    # Test 5: capacity 0
    def t5():
        c = UserCache(0)
        c.put(1, 1)
        assert c.get(1) == -1
    tests.append(("capacity 0", t5))

    # Test 6: get non-existent
    def t6():
        c = UserCache(2)
        assert c.get(42) == -1
    tests.append(("get non-existent", t6))

    # Test 7: put then get same key multiple times
    def t7():
        c = UserCache(5)
        for i in range(5):
            c.put(i, i * 10)
        for i in range(5):
            assert c.get(i) == i * 10
    tests.append(("multiple keys", t7))

    # Test 8: eviction order after mixed ops
    def t8():
        c = UserCache(3)
        c.put(1, 1); c.put(2, 2); c.put(3, 3)
        c.get(1); c.get(2)          # 1,2 recently used, 3 is LRU
        c.put(4, 4)                 # evicts 3
        assert c.get(3) == -1
        assert c.get(1) == 1
        assert c.get(4) == 4
    tests.append(("mixed eviction order", t8))

    # Test 9: put updates value AND recency
    def t9():
        c = UserCache(2)
        c.put(1, 1); c.put(2, 2)
        c.put(1, 100)   # update 1, makes it recent
        c.put(3, 3)     # evicts 2
        assert c.get(2) == -1
        assert c.get(1) == 100
    tests.append(("put updates recency", t9))

    # Test 10: large capacity, sequential access
    def t10():
        c = UserCache(100)
        for i in range(200):
            c.put(i, i)
        # only last 100 should be present
        for i in range(100):
            assert c.get(i) == -1, f"old key {i} should be evicted"
        for i in range(100, 200):
            assert c.get(i) == i, f"recent key {i} should exist"
    tests.append(("large sequential", t10))

    # Test 11: alternating read/write
    def t11():
        c = UserCache(3)
        for i in range(10):
            c.put(i, i)
            assert c.get(i) == i
        # each put evicts the oldest, total capacity 3
        assert c.get(9) == 9
        assert c.get(8) == 8
        assert c.get(7) == 7
    tests.append(("alternating", t11))

    # Test 12: negative keys
    def t12():
        c = UserCache(2)
        c.put(-1, 100)
        c.put(-2, 200)
        assert c.get(-1) == 100
        c.put(-3, 300)
        assert c.get(-2) == -1
    tests.append(("negative keys", t12))

    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            failed.append(f"{name}: {e}")

    if failed:
        msg = "; ".join(failed[:5])
        return {"score": 0.0, "passed": False, "feedback": f"{len(failed)} failures: {msg}", "metrics": {}, "artifacts": {}}

    # ── Throughput benchmark ───────────────────────────────────────
    import random
    random.seed(42)

    ref = _RefLRU(50)
    user = UserCache(50)

    # Warmup
    for _ in range(1000):
        k = random.randint(0, 100)
        if random.random() < 0.5:
            ref.get(k); user.get(k)
        else:
            ref.put(k, k); user.put(k, k)

    N = 20000
    ops = [(random.randint(0, 100), random.random() < 0.5) for _ in range(N)]

    t0 = time.perf_counter()
    for k, is_get in ops:
        if is_get:
            user.get(k)
        else:
            user.put(k, k)
    user_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    for k, is_get in ops:
        if is_get:
            ref.get(k)
        else:
            ref.put(k, k)
    ref_elapsed = time.perf_counter() - t0

    speedup = ref_elapsed / user_elapsed if user_elapsed > 0 else 0
    score = min(speedup, 1.0)

    feedback = (
        f"All {len(tests)} tests passed. "
        f"Speed: {N/user_elapsed/1000000:.1f}M ops/sec "
        f"(ref: {N/ref_elapsed/1000000:.1f}M, ratio: {speedup:.3f}). "
        f"Score: {score:.4f}"
    )

    return {
        "score": score,
        "passed": True,
        "feedback": feedback,
        "metrics": {
            "user_ops_per_sec": N / user_elapsed,
            "ref_ops_per_sec": N / ref_elapsed,
            "speed_ratio": speedup,
        },
        "artifacts": {},
    }
