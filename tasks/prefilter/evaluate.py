"""Evaluator for find_defined_names — AST definition extraction.

Score: throughput ratio vs ast.walk-based reference, sigmoid-normalized.
0.5 = equal to reference, higher is better, no ceiling.

Reference: `ast.walk(tree)` visits every AST node (thousands for large code).
Better approaches: `ast.iter_child_nodes` only visits top-level, or manual
recursion that stops at function boundaries.
"""

import ast
import time
from typing import Set


# ── Reference: ast.walk-based (current verigen implementation) ──────────

def _reference_find_names(code: str) -> Set[str]:
    """Find defined names using ast.walk (visits ALL nodes)."""
    tree = ast.parse(code)
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
    }


# ── Evaluator ───────────────────────────────────────────────────────────

def evaluate(code_str: str) -> dict:
    ns = {}
    try:
        exec(compile(code_str, "<eval>", "exec"), ns)
    except Exception as e:
        return {"score": 0.0, "passed": False, "feedback": f"Syntax error: {e}", "metrics": {}, "artifacts": {}}

    fn = ns.get("find_defined_names")
    if fn is None:
        return {"score": 0.0, "passed": False, "feedback": "find_defined_names not defined", "metrics": {}, "artifacts": {}}
    if not callable(fn):
        return {"score": 0.0, "passed": False, "feedback": "not callable", "metrics": {}, "artifacts": {}}

    # ── Correctness tests ──────────────────────────────────────────
    test_cases = []

    # Simple function
    test_cases.append(("simple def", "def foo(): pass", {"foo"}))

    # Simple class
    test_cases.append(("simple class", "class Bar: pass", {"Bar"}))

    # Async function
    test_cases.append(("async def", "async def baz(): pass", {"baz"}))

    # Multiple definitions
    test_cases.append(("multiple defs", """
def a(): pass
def b(): pass
class C: pass
""", {"a", "b", "C"}))

    # Nested functions (should be found)
    test_cases.append(("nested defs", """
def outer():
    def inner(): pass
    class Nested: pass
""", {"outer", "inner", "Nested"}))

    # Class with methods
    test_cases.append(("class methods", """
class MyClass:
    def method1(self): pass
    async def method2(self): pass
""", {"MyClass", "method1", "method2"}))

    # Deeply nested classes
    test_cases.append(("deeply nested", """
class Outer:
    class Middle:
        def inner(self): pass
        class Deep:
            def deepest(self): pass
""", {"Outer", "Middle", "inner", "Deep", "deepest"}))

    # Multiple top-level + nested
    test_cases.append(("mixed", """
def top_level(): pass
class Container:
    def method(self): pass
    class Inner:
        def inner_method(self): pass
async def async_top(): pass
""", {"top_level", "Container", "method", "Inner", "inner_method", "async_top"}))

    # Empty code
    test_cases.append(("empty", "", set()))

    # Only expressions, no definitions
    test_cases.append(("no defs", "x = 1\ny = x + 2\nprint(y)", set()))

    # Large generated-style code
    large_code = """
def solve(data):
    result = []
    for i, item in enumerate(data):
        if item > 0:
            result.append(process(item))
    return result

class Helper:
    def transform(self, x):
        return x * 2

class Cache:
    def __init__(self, cap):
        self.cap = cap
    def get(self, key):
        return self._data.get(key, -1)
    def put(self, key, value):
        if key in self._data:
            self._data[key] = value
        else:
            if len(self._data) >= self.cap:
                self._data.pop(next(iter(self._data)))
            self._data[key] = value
"""
    test_cases.append(("large generated", large_code, {"solve", "Helper", "transform", "Cache", "get", "put", "__init__"}))

    failed = []
    for name, code, expected in test_cases:
        try:
            result = fn(code)
            if result != expected:
                failed.append(f"{name}: got {result}, expected {expected}")
        except Exception as e:
            failed.append(f"{name}: raised {type(e).__name__}: {e}")

    if failed:
        msg = "; ".join(failed[:5])
        return {"score": 0.0, "passed": False, "feedback": f"{len(failed)} failures: {msg}", "metrics": {}, "artifacts": {}}

    # ── Performance benchmark ──────────────────────────────────────
    # Use progressively larger code to stress-test the AST walking
    def _build_large_code(n_defs: int) -> str:
        lines = []
        for i in range(n_defs):
            lines.append(f"def func_{i}(x):")
            lines.append(f"    return x + {i}")
        for i in range(n_defs):
            lines.append(f"class Class_{i}:")
            lines.append(f"    def method_{i}(self): pass")
        return "\n".join(lines)

    bench_codes = [
        _build_large_code(10),    # ~20 defs
        _build_large_code(50),    # ~100 defs
        _build_large_code(200),   # ~400 defs
    ]

    # Warmup
    for c in bench_codes:
        fn(c)
        _reference_find_names(c)

    N = 200
    t0 = time.perf_counter()
    for _ in range(N):
        for c in bench_codes:
            fn(c)
    user_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(N):
        for c in bench_codes:
            _reference_find_names(c)
    ref_elapsed = time.perf_counter() - t0

    speedup = ref_elapsed / user_elapsed if user_elapsed > 0 else 0
    # Sigmoid normalization: 0.5 = equal to reference
    score = round(speedup / (speedup + 1.0), 6)

    feedback = (
        f"All {len(test_cases)} tests passed. "
        f"Speed: {N*len(bench_codes)/user_elapsed:,.0f} calls/sec "
        f"(ref: {N*len(bench_codes)/ref_elapsed:,.0f}, ratio: {speedup:.3f}). "
        f"Score: {score:.4f}"
    )

    return {
        "score": score,
        "passed": True,
        "feedback": feedback,
        "metrics": {
            "calls_per_sec": round(N * len(bench_codes) / user_elapsed, 2),
            "ref_calls_per_sec": round(N * len(bench_codes) / ref_elapsed, 2),
            "speed_ratio": round(speedup, 4),
        },
        "artifacts": {},
    }
