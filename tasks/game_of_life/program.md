# Conway's Game of Life

Implement `game_of_life(board: list[list[int]]) -> list[list[int]]`
that computes the next state according to Conway's rules:
1. Live cell with <2 neighbours → dies (underpopulation)
2. Live cell with 2–3 neighbours → lives
3. Live cell with >3 neighbours → dies (overpopulation)
4. Dead cell with exactly 3 neighbours → becomes alive

Neighbours are the 8 adjacent cells. Cells outside the board are dead
(no wrap-around). Return a **new** board — do not mutate the input.

The evaluator runs 15 tests covering still lifes (block, beehive),
oscillators (blinker, toad), glider movement, empty/single-cell boards,
edge-only rows/columns, and comparison against a reference on random
30×30 boards. All must pass.

Score is throughput ratio vs reference (nested loops with zero-padding).

## Optimization ladder (approx scores)
- Nested loops with bounds checking: ~0.3–0.5
- Zero-padded board (avoids bounds checks): ~0.5–0.7
- Numpy vectorized (if available): ~0.7–0.9
- Sparse (only track live cells): ~0.5–1.0 (depends on density)
