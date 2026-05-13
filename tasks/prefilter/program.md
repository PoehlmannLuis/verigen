# Extract defined names from Python source via AST

Implement `find_defined_names(code: str) -> Set[str]` that returns the set
of all function, class, and async function names defined in the given Python
source code. Must find definitions at any nesting level.

Used by verigen's static analysis pre-filter on every candidate during
evolution. Called thousands of times per run. Must be CORRECT before fast.

## Correctness rules (hard constraints)
1. Must handle empty/blank code → return `set()`
2. Must handle code with only expressions → return `set()`
3. Must handle syntax errors → try/except `SyntaxError`, return `set()`
4. Must return the SAME set as the reference (`ast.walk` + isinstance filter)
5. Must find definitions at ANY nesting depth (function inside class inside function...)
6. Return type must be `Set[str]`

## The ONLY correct recursive pattern
Use `ast.iter_child_nodes(node)` to get ALL children of any AST node.
This automatically handles `.body`, `.orelse`, `.handlers`, `.finalbody`,
`.cases`, etc. — everything. Do NOT enumerate AST statement types.

## What NOT to do
- DO NOT enumerate AST node types (no `isinstance(node, ast.If)` chains)
- DO NOT use `ast.TryStar`, `ast.TryExcept`, `ast.Match`, or any
  version-specific attribute by name
- DO NOT use `hasattr(node, 'body')` — misses orelse/handlers/finalbody
- DO NOT write 100+ line functions — the correct solution is <30 lines

## Performance optimization (in order of impact)
1. **Use `ast.iter_child_nodes`** — already avoids visiting terminal nodes
2. **Localize** `isinstance`, `defined_names.add` to avoid attribute lookups
3. **`while` stack instead of recursion** — avoid Python call overhead
4. **Short-circuit** — skip bodies of functions/classes after extracting name?
   (correct only if no nested definitions, but there ARE nested defs)

## Benchmark context
- Reference uses `ast.walk()` on a Module tree — visits ALL AST nodes
  (expressions, literals, identifiers — everything)
- `ast.walk()` is implemented in C — to beat it, avoid visiting nodes
  that can't contain definitions by using controlled `iter_child_nodes`
- Score ~0.65 (1.8×) achievable with a simple recursive approach
- Score ~0.80+ requires reducing Python overhead (iterative, localized)

Expected function signature:
```python
def find_defined_names(code: str) -> Set[str]:
```
