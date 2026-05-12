# Topological sort

Implement `topological_sort(graph: dict[int, list[int]]) -> list[int]`
returning a valid topological ordering of the directed graph.

The graph maps `node -> list[neighbour]`. If the graph contains a cycle,
raise `ValueError`. Nodes may appear as targets without being keys in
the dict (i.e., nodes with no outgoing edges).

The evaluator runs 15 tests covering empty graphs, linear chains, diamonds,
disconnected components, large DAGs, cycles (simple, self-loop, complex),
and branch-merge topologies. All must pass.

Score is `ref_sorts_per_sec / user_sorts_per_sec`, capped at 1.0.

## Optimization ladder (approx scores)
- List-based (parents tracked, O(n²)): ~0.1–0.3
- Kahn's with in-degree dict + deque: ~0.5–0.8
- DFS with explicit stack (no recursion): ~0.6–0.9
- Optimized DFS with adjacency sets: ~0.8–1.0
