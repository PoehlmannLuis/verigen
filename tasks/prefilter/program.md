# Extract defined names from Python source via AST

Implement `find_defined_names(code: str) -> Set[str]` that returns the set
of all function, class, and async function names defined in the given Python
source code. Must find definitions at any nesting level.

Used by verigen's static analysis pre-filter on every candidate during
evolution. Called thousands of times per run. Must be CORRECT before fast.

## Correctness rules (hard constraints)
1. Empty/blank code → `set()`
2. Expressions only → `set()`
3. Syntax errors → `try/except SyntaxError`, `set()`
4. Find ALL definitions: functions, classes, async functions, methods at any depth
5. Return type must be `Set[str]`
6. Must match reference's output EXACTLY for every test case

## The optimization insight

The reference uses `ast.walk(tree)` which is implemented in C. It visits
EVERY node in the AST — identifiers, literals, operators, type params,
decorators, etc. For typical generated code (200+ lines), that's thousands
of nodes, 95%+ of which can't possibly contain function/class definitions.

To beat `ast.walk`, you must visit FEWER nodes. The key: **only recurse
into fields that can contain statement-level nodes** — specifically `.body`,
`.orelse`, `.finalbody`, `.handlers`, and `.cases`.

## The correct approach (what worked, score ~0.64)

Use `hasattr(node, field_name)` to check for statement-containing fields,
then iterate into each. Do NOT use `ast.iter_child_nodes(node)` — it visits
ALL children including expressions, same as `ast.walk`.

```python
# For the current node, only walk into statement containers:
for field in ('body', 'orelse', 'finalbody'):
    items = getattr(node, field, None)
    if isinstance(items, list):
        for child in items:
            ...
# Also handle handlers (Try) and cases (Match):
handlers = getattr(node, 'handlers', None)
if handlers:
    for handler in handlers:
        ...  # handler.body is another list
```

## Micro-optimizations (push score beyond 0.65)
1. Localize hot functions: `is_def = isinstance`, `names_add = names.add`
2. Use `while` stack instead of recursion (avoids Python call overhead)
3. Use `for child in items:` directly (fastest iteration)
4. Avoid `ast.iter_fields()`, `ast.iter_child_nodes()` — these are slower

## Score reference
- `ast.walk` (C, visits everything): ~0.49-0.50
- `iter_child_nodes` + stack: ~0.49-0.50 (same nodes visited)
- **Statement-only traversal** (body/orelse/finalbody): **0.62-0.66**
- Statement-only + micro-optimizations: 0.70+

Expected function signature:
```python
def find_defined_names(code: str) -> Set[str]:
```
