import ast
from typing import Set


def find_defined_names(code: str) -> Set[str]:
    """Extract the set of function/class names defined in Python source code.

    Used by verigen's static analysis pre-filter to verify generated code
    defines the expected symbol. Must be correct AND fast — called on every
    evaluation of generated code.

    Args:
        code: Python source code as a string.

    Returns:
        Set of function, class, and async function names defined at any nesting level.
    """
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this code!")
    # EVOLVE-BLOCK-END
