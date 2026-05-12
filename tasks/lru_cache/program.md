# LRU Cache

Implement `LRUCache` class with `get(key: int) -> int` and
`put(key: int, value: int) -> None` in O(1) average time. When the cache
reaches capacity, evict the least-recently-used item. `get` marks a key
as recently used. `put` on an existing key updates its value AND recency.

The evaluator runs 12 correctness tests covering basic eviction, capacity
boundaries (0, 1, large), update semantics, negative keys, and mixed
access patterns. All must pass. Then it benchmarks throughput against a
reference `OrderedDict`-based implementation across 20,000 random ops.

Score is `ref_time / user_time`, capped at 1.0.

## Optimization ladder (approx scores)
- dict + list (O(n) eviction): ~0.1–0.3
- OrderedDict (move_to_end): ~0.4–0.6
- dict + doubly linked list: ~0.6–0.9
- dict + linked list + sentinel node: ~0.9–1.0
