def game_of_life(board: list[list[int]]) -> list[list[int]]:
    """Compute the next state of Conway's Game of Life.

    board is a rectangular list of lists, each element 0 (dead) or 1 (alive).
    Rules:
        1. Live cell with <2 live neighbours → dies (underpopulation)
        2. Live cell with 2 or 3 live neighbours → lives
        3. Live cell with >3 live neighbours → dies (overpopulation)
        4. Dead cell with exactly 3 live neighbours → becomes alive (reproduction)

    Neighbours are the 8 adjacent cells (horizontal, vertical, diagonal).
    Cells outside the board are treated as dead (no wrap-around).

    Return a new list of lists (do not mutate the input).
    """
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this code!")
    # EVOLVE-BLOCK-END
