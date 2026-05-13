# Extract defined names from Python source via AST

Implement `find_defined_names(code: str) -> Set[str]` that returns the set
of all function, class, and async function names defined in the given Python
source code. Must find definitions at any nesting level (top-level functions,
methods inside classes, nested functions, etc.).

This is used by verigen's own static analysis pre-filter to verify that
LLM-generated code defines the expected symbol. It's called on every
candidate during evolution, so speed matters.

The reference implementation uses `ast.walk(tree)` which visits EVERY node
in the AST (thousands for large generated programs). A faster approach
avoids visiting the entire tree since we only need function/class definition
nodes.

## Requirements
- Return a `Set[str]` of all defined names
- Include: functions, classes, async functions, methods, nested functions
- Handle empty code (return empty set)
- Handle code with only expressions (no definitions)
- Must match the reference implementation's output exactly
- **Target Python 3.9 runtime** — do NOT use `ast.TryStar` (3.11+), `ast.Match` (3.10+), or any attribute that doesn't exist in Python 3.9's `ast` module. Stick to `ast.FunctionDef`, `ast.AsyncFunctionDef`, `ast.ClassDef`, and `ast.Module` which are available on all versions.

## Optimization ladder (approximate scores)
- ast.walk (visits all nodes): ~0.5 (equal to reference)
- ast.iter_child_nodes (top-level only, misses nested): ~0.3 (WRONG — incorrect)
- ast.iter_child_nodes + manual recursion into classes: ~0.7–0.9
- Manual recursion that skips function bodies: ~0.8–1.0
