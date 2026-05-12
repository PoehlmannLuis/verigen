"""Topological sort — correctness tests + latency benchmark.

Score: throughput ratio vs a reference Kahn's algorithm. Tests cover
DAG ordering validity, cycle detection, empty graphs, single node,
and various graph topologies.
"""

import time
from collections import deque


def _reference_kahn(graph):
    """Kahn's algorithm for topological sort. Raises ValueError on cycle."""
    # Collect all nodes (including targets not in keys)
    all_nodes = set(graph)
    for n in graph:
        all_nodes.update(graph[n])
    in_deg = {n: 0 for n in all_nodes}
    for n in graph:
        for m in graph[n]:
            in_deg[m] += 1

    q = deque([n for n, d in in_deg.items() if d == 0])
    result = []
    while q:
        n = q.popleft()
        result.append(n)
        for m in graph.get(n, []):
            in_deg[m] -= 1
            if in_deg[m] == 0:
                q.append(m)
    if len(result) != len(all_nodes):
        raise ValueError("graph contains a cycle")
    return result


def _is_valid_order(graph, order):
    """Check that order is a valid topological sort of graph."""
    # Collect all nodes (including targets not in keys)
    all_nodes = set(graph)
    for n in graph:
        all_nodes.update(graph[n])
    pos = {n: i for i, n in enumerate(order)}
    if set(order) != all_nodes:
        return False
    for n in graph:
        for m in graph[n]:
            if pos[n] > pos[m]:
                return False
    return True


def evaluate(code_str: str) -> dict:
    ns = {}
    try:
        exec(compile(code_str, "<eval>", "exec"), ns)
    except Exception as e:
        return {"score": 0.0, "passed": False, "feedback": f"Syntax error: {e}", "metrics": {}, "artifacts": {}}

    fn = ns.get("topological_sort")
    if fn is None:
        return {"score": 0.0, "passed": False, "feedback": "topological_sort not defined", "metrics": {}, "artifacts": {}}

    # ── Correctness tests ──────────────────────────────────────────
    graphs = []

    # 1: Empty graph
    graphs.append(("empty", {}, False))

    # 2: Single node
    graphs.append(("single node", {0: []}, False))

    # 3: Linear chain
    graphs.append(("linear", {0: [1], 1: [2], 2: []}, False))

    # 4: Diamond
    graphs.append(("diamond", {0: [1, 2], 1: [3], 2: [3], 3: []}, False))

    # 5: Disconnected
    graphs.append(("disconnected", {0: [], 1: [], 2: []}, False))

    # 6: Complex DAG
    graphs.append(("complex", {
        0: [1, 2], 1: [3], 2: [3, 4], 3: [5], 4: [5], 5: []
    }, False))

    # 7: Large linear chain
    large = {i: [i + 1] for i in range(99)}
    large[99] = []
    graphs.append(("large linear", large, False))

    # 8: Single cycle
    graphs.append(("single cycle", {0: [1], 1: [2], 2: [0]}, True))

    # 9: Cycle with a tail
    graphs.append(("cycle with tail",
        {0: [1], 1: [2], 2: [3], 3: [1]}, True))

    # 10: Self-loop
    graphs.append(("self-loop", {0: [0]}, True))

    # 11: Cycle among larger nodes
    graphs.append(("larger cycle",
        {0: [1], 1: [2], 2: [3], 3: [4], 4: [5], 5: [3]}, True))

    # 12: Branching with terminal merge
    graphs.append(("branch merge",
        {0: [1, 2], 1: [3], 2: [3], 3: []}, False))

    # 13: Two separate DAGs
    graphs.append(("two DAGs",
        {0: [1], 1: [], 2: [3], 3: []}, False))

    # 14: Node with no outgoing edges only as target
    graphs.append(("target only", {0: [1], 1: []}, False))

    # 15: Deeply nested
    deeply = {}
    for i in range(50):
        for j in range(i + 1, 50):
            deeply.setdefault(i, []).append(j)
        if i not in deeply:
            deeply[i] = []
    graphs.append(("complete DAG 50", deeply, False))

    failed = []
    for name, g, should_cycle in graphs:
        try:
            result = fn(g)
            if should_cycle:
                failed.append(f"{name}: expected ValueError but got {result}")
            elif not _is_valid_order(g, result):
                failed.append(f"{name}: invalid ordering {result}")
        except ValueError:
            if not should_cycle:
                failed.append(f"{name}: unexpected ValueError")
        except Exception as e:
            failed.append(f"{name}: raised {e}")

    if failed:
        msg = "; ".join(failed[:5])
        return {"score": 0.0, "passed": False, "feedback": f"{len(failed)} failures: {msg}", "metrics": {}, "artifacts": {}}

    # ── Latency benchmark ──────────────────────────────────────────
    def _make_bench1():
        g = {i: list(range(i + 1, 200)) for i in range(199)}
        g[199] = []
        return g

    def _make_bench2():
        return {i: [i + 1] if i < 499 else [] for i in range(500)}

    def _make_bench3():
        g = {i: [j for j in range(i + 1, 500, 3)] for i in range(499)}
        g[499] = []
        return g

    bench_graphs = [_make_bench1(), _make_bench2(), _make_bench3()]

    # Warmup
    for _ in range(10):
        for g in bench_graphs:
            fn(g)

    N = 500
    t0 = time.perf_counter()
    for _ in range(N):
        for g in bench_graphs:
            fn(g)
    user_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(N):
        for g in bench_graphs:
            _reference_kahn(g)
    ref_elapsed = time.perf_counter() - t0

    speedup = ref_elapsed / user_elapsed if user_elapsed > 0 else 0
    score = min(speedup, 1.0)

    feedback = (
        f"All {len(graphs)} tests passed. "
        f"Speed: {(N*len(bench_graphs))/user_elapsed:,.0f} sorts/sec "
        f"(ref: {(N*len(bench_graphs))/ref_elapsed:,.0f}, ratio: {speedup:.3f}). "
        f"Score: {score:.4f}"
    )

    return {
        "score": score,
        "passed": True,
        "feedback": feedback,
        "metrics": {
            "sorts_per_sec": (N * len(bench_graphs)) / user_elapsed,
            "ref_sorts_per_sec": (N * len(bench_graphs)) / ref_elapsed,
            "speed_ratio": speedup,
        },
        "artifacts": {},
    }
