# v0.3: Deeper Architecture — What to Tackle Next

*Draft for review. Edit, reorder, or kill items before implementation.*

---

## 1. Subprocess Overhead (Performance)

### Current State

Every evaluation spawns `python3 -c "..."` — imports the evaluator module, reads the temp code file, compiles, runs benchmarks, serializes via stdout. This costs **~300–500ms per evaluation** in Python startup + import, regardless of the actual benchmark (which could be 2ms for fast tasks like Levenshtein).

For a 30-iteration run with 20s per iteration, subprocess overhead accounts for ~75% of the wall time.

### Options

**A. Subprocess Pool (recommended for v0.3)**

Keep 1+ persistent worker processes alive. The worker imports the evaluator module *once*, then receives code strings over a simple stdin/stdout JSON-line protocol.

```
Parent                          Worker
  │                               │
  │─── {"id":1, "code":"..."} ───▶│  evaluate(code)
  │◀── {"id":1, "result":{...}} ─│
  │─── {"id":2, "code":"..."} ───▶│  evaluate(code)
  │◀── {"id":2, "result":{...}} ─│
  │─── {"shutdown": true} ───────▶│
```

**Trade-offs:**
- ~10–50× faster per evaluation (no re-import)
- Worker crash → restart with full import (transparent to caller)
- Worker count matches concurrency: 1 for single-thread, N for population
- Worker lifecycle: lazy spawn, keepalive timeout (configurable)
- Security model unchanged (same subprocess boundary)

**Implementation sketch:**
```python
class EvalWorkerPool:
    def __init__(self, eval_module_path: str, max_workers: int = 1):
        self._workers = [self._spawn(eval_module_path) for _ in range(max_workers)]
        self._next_id = 0

    def evaluate(self, code_str: str, timeout: int = 30) -> EvaluationResult:
        worker = self._workers[self._next_id % len(self._workers)]
        self._next_id += 1
        return worker.send(code_str, timeout)

    def _spawn(self, eval_path) -> _EvalWorker:
        proc = subprocess.Popen([sys.executable, "-c", _WORKER_SCRIPT, eval_path],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        return _EvalWorker(proc)
```

**B. Inline Evaluation (`--no-sandbox`)**

For trusted tasks, run `exec()` in-process with `signal.SIGALRM` for timeout. Eliminates subprocess overhead entirely. Not suitable for untrusted evaluators.

**C. Hybrid: pool by default, inline with flag**

CLI flag `--eval-mode` = `pool` | `inline` | `subprocess` (current).

**Decision:** Pool is the only option that preserves security while solving the problem. Recommend Option A (pool) as default, with `--eval-mode subprocess` as fallback.

### Open Questions
- What happens when the worker's evaluator module is updated between runs? (Checksum or version handshake?)
- Should workers be pre-warmed (spawn at task load) or lazy (spawn on first eval)?
- How to handle `atexit` cleanup in the worker?

---

## 2. Population Evolution (Exploration)

### Current State

Greedy hill-climbing keeps 1 best candidate. The LRU Cache trace is the canonical pathology:

| Iter | Approach | Score | Fate |
|------|----------|-------|------|
| 0 | Doubly-linked list + sentinel | 0.0 | failed capacity-0 |
| 1 | Linked list + capacity guard | **0.32** | kept |
| 2–8 | Dict + pop/re-insert (broken) | 0.0 | rejected ×7 |

The LLM kept trying to replace the linked list with a dict approach, failing the same 2 tests every time. It never tried **OrderedDict** (which would score ~0.5 with the sigmoid formula and is the obvious middle-ground). The system had no way to say "your dict idea is correct in spirit, just use OrderedDict."

### Options

**A. Beam Search (recommended)**

Keep top-K candidates in a beam. Each iteration, select one candidate from the beam (weighted by score or round-robin), mutate it, evaluate, and insert into beam if it beats the weakest beam member.

```
Beam [score 0.32, score 0.28, score 0.25]
  │ mutate candidate at index 1 (score 0.28)
  ▼
Candidate score 0.45 → beam becomes [0.45, 0.32, 0.28]
```

- K=3–5 is cheap, K=10+ starts to cost linearly
- Diversity naturally emerges from different starting points
- Each LLM call is the same price — we just keep more candidates around

**B. Focused Mutation (complement to any strategy)**

The LLM currently rewrites the **entire program** every iteration. This is why small edge cases keep breaking — the LLM has to reproduce the full program correctly each time.

Instead: extract just the EVOLVE-BLOCK region, pass only that to the LLM for editing, and splice the result back into the surrounding context. The ADR moved away from this due to indentation issues, but we can solve that:

1. Pass the full program as context (so the LLM understands the surrounding code)
2. The LLM outputs **only the inner block content** (no class/function wrapper)
3. On the splice, normalize indentation of the block to match the template

**Trade-offs:**
- Smaller mutation surface → fewer regressions
- Less redundant output per LLM call (saves tokens)
- Requires careful indentation normalization
- Can't add new helper methods outside the block

**C. Archive + Diversity Bonus**

Keep an archive of all candidates that ever passed constraints. When selecting a parent for mutation, with probability `diversity_prob`, pick a random archive member instead of the best. This gives a second chance to approaches that scored lower but had different structural properties.

A simple diversity heuristic: **AST structural hash** (hash of the parsed AST, ignoring variable names). If a candidate's AST hash isn't in the archive, it's structurally novel.

**D. Full Population (μ+λ)**

Maintain a population of M candidates. Each generation:
1. Select top-K parents (tournament or rank)
2. Mutate each to produce λ children
3. Evaluate all children
4. Select M survivors from parents + children (μ+λ)

This is the AlphaEvolve/ShinkaEvolve approach. Powerful but expensive (λ evaluations per generation). Best suited for server-side batch runs, not interactive CLI.

### Recommendation for v0.3

Ship **Beam Search (K=3) + Focused Mutation** as the default. This is a modest code change that directly addresses the LRU Cache pathology without the cost of full population evolution.

Add `--strategy beam --beam-width 5` and `--strategy greedy` (current) as CLI options.

### Open Questions
- Beam selection strategy: always mutate the best, or weighted random?
- Focused mutation: how to handle multi-method classes like LRU Cache where the EVOLVE-BLOCK spans multiple methods?
- Should the archive persist across runs (in `output/archive.jsonl`)?

---

## 3. `dspy.Assert` Integration

### Current State

Hard constraints are enforced imperatively:
```python
if not best_result.passed:
    return  # early exit
```

ADR-001 specified `dspy.Assert` for hard constraints, but it was never implemented.

### Analysis

`dspy.Assert` works inside DSPy module `forward()` methods and raises `dspy.AssertionError` on failure. The assertion is recorded in DSPy's trace, enabling `AssertionOptimizer` to learn from constraint violations.

**Why it's tricky here:**
- The evolutionary loop has a fundamentally different control flow than a standard DSPy pipeline
- Hard constraints in evolution mean "reject this candidate", not "abort the whole pipeline"
- `dspy.Assert` raising would terminate the forward pass, losing all progress
- We'd need to catch the assertion and convert it to a soft rejection

### Design Proposal

Don't force `dspy.Assert` into the evolutionary loop. Instead, use **DSPy signature-level constraints**:

```python
class EvaluationFeedback(dspy.Signature):
    """..."""
    hard_constraints = dspy.InputField(
        desc="Constraints that MUST be satisfied. Format: each constraint on a new line."
    )
```

And in `forward()`:
```python
# Generate with constraints
mutation = self.improver(
    ...,
    hard_constraints="All 12 LRU Cache tests must pass.\n"
                     "get() must run in O(1) average time.\n"
                     "put() must run in O(1) average time.",
)
```

The constraints are extracted from `program.md` (or from a new `constraints.txt` file) and injected into the DSPy module's prompt. This is more appropriate for an evolutionary loop than runtime assertions.

For DSPy optimizer compatibility, we can still wrap the candidate rejection in a `dspy.Assert` that converts the rejection into a DSPy trace event without aborting:

```python
try:
    dspy.Assert(candidate_result.passed, "Hard constraints failed")
except dspy.AssertionError:
    pass  # captured in trace, continue loop
```

### Recommendation for v0.3

1. Add a structured `constraints` field to `TaskSpec` (parsed from `program.md` or a new file)
2. Inject constraints into the improver's DSPy signature as an input field
3. Wrap candidate rejection in a `dspy.Assert`/except pattern to get DSPy trace recording without aborting the loop
4. Remove the current imperative `if not passed: return` — let the DSPy assertion mechanism record the failure

### Open Questions
- Where should constraints live? `program.md` section, or separate `constraints.txt`?
- How to handle constraints that are only meaningful to the evaluator (not the LLM)?
- Should the constraints be used for pre-filtering (reject without subprocess) or only for guidance?

---

## 4. Additional Improvement Areas

### 4.1 Evaluation Caching

Same code → same evaluation result. Cache `hash(code) → EvaluationResult` to avoid redundant subprocess calls.

Happens more than you'd think: the LLM outputs identical code across consecutive iterations (especially near convergence), and the subprocess overhead is pure waste.

Implementation: LRU dict with `hashlib.sha256(code.encode()).hexdigest()` as key, max entries = `max_iterations × 2`.

### 4.2 Multi-Turn Mutation Context

Currently, the improver sees only the **last** evaluation's feedback. For the LRU Cache case, iterations 2–8 all failed the same 2 tests, and the LLM had no memory of what it already tried.

Solution: Pass the last K iterations of (change_rationale + score) to the LLM as `change_history`. This is a small change to `_format_feedback`:

```python
def _format_feedback(result: EvaluationResult, iteration: int, history: list[str] = None) -> str:
    lines = [...]
    if history:
        lines.append("  Recent history (tried approaches, outcome):")
        for h in history[-3:]:
            lines.append(f"    - {h[:200]}")
    return "\n".join(lines)
```

K=3 is cheap, K=10 starts to eat context window.

### 4.3 Static Analysis Pre-Filter

Before shipping code to the subprocess, run cheap static checks:

1. **Syntax check**: `compile(code_str, "<eval>", "exec")` — catches unclosed brackets, invalid syntax
2. **AST structural check**: Does the code define the expected function/class? Does it import prohibited modules?
3. **Basic lint**: Does the code reference undefined names?

Rejected-at-static-time costs ~5ms instead of ~500ms subprocess overhead. This makes the "obviously broken" case fast.

### 4.4 Beam Search CLI Options

```bash
verigen run tasks/lru_cache/ --strategy beam --beam-width 5
verigen run tasks/lru_cache/ --strategy greedy     # current default
verigen run tasks/lru_cache/ --strategy anneal     # simulated annealing
```

Annealing variant: sometimes accept worse candidates with probability `exp(-Δscore / temperature)`, decreasing temperature over time. This is the classic simulated annealing escape from local minima.

### 4.5 DSPy Module Save/Load (ADR-007 Debt)

`module.json` was promised but never written. After evolution, serialize the `VerifiableCodeGen` DSPy module state:

```python
# In module.py forward(), before returning:
module_path = out_dir / "module.json"
dspy.save(self, module_path)
```

This enables:
- Load a trained module: `VerifiableCodeGen.load("output/module.json")`
- Continue optimization from a trained state
- Share optimized codegen strategies across tasks

### 4.6 Smarter Scaffold Template

The current `new-task.sh` generates a skeleton with `pass  # Remove this when you add tests`. Replace with a template that:
- Includes a reference implementation for ratio scoring
- Uses the `speedup / (speedup + 1)` sigmoid normalization
- Has a more useful default benchmark loop
- Generates a richer `program.md` with optimization ladder hints

### 4.7 Graceful LLM Error Recovery

Current error handling is binary: `AdapterParseError` → skip iteration. Add:
- **Rate limit / 429**: Backoff and retry with exponential delay (jitter)
- **Connection error**: Retry up to 3 times
- **Context length exceeded**: Retry with truncated history
- **All errors**: Log to trace with structured error codes

### 4.8 Score Interpretation in Output

The user sees `Score: 0.43` and has no idea what it means. Add an interpretation:

```
Score: 0.43 = 75% of reference speed (0.75× ratio).
Interpretation: performance gap is ~25% — consider an OrderedDict-based approach.
```

This requires the evaluator to export a `score_interpretation` field, or the CLI to compute it from known score ranges. A general approach: convert score back to ratio via `ratio = score / (1 - score)` and compare to 1.0.

### 4.9 Task-Specific Test Count in Trace

The trace currently records `metrics.n_tests` but it's inconsistent across tasks (some record it, some don't). Standardize: every evaluator should report `n_tests` and `n_passed` in metrics. The CLI can then show `7/12 tests passed` per iteration.

### 4.10 Quiet Mode (`-q` / `--quiet`)

For CI/CD and scripting, suppress the live progress output (already possible via `on_iteration=None` in the Python API). Add a CLI flag.

---

## Prioritization Matrix

| Item | Impact | Effort | Risk | When |
|------|--------|--------|------|------|
| Subprocess pool | High (10-50× eval speedup) | Medium | Low | v0.3, first |
| Beam search (K=3) | High (escape local minima) | Medium | Medium | v0.3 |
| Focused mutation | Medium (fewer regressions) | Medium | Medium | v0.3 |
| Evaluation caching | Medium (skip redundant evals) | Low | Low | v0.3 |
| Multi-turn context | Medium (learn from history) | Low | Low | v0.3 |
| Static analysis pre-filter | Medium (fast rejection) | Low | Low | v0.3 |
| `dspy.Assert` integration | Low (trace recording only) | Medium | Medium | v0.3 or later |
| DSPy module save/load | Low (ADR debt) | Low | Low | v0.3 |
| Smarter scaffold | Low (DX polish) | Low | Low | v0.3 |
| Graceful LLM recovery | Medium (robustness) | Low | Low | v0.3 |
| Score interpretation | Low (UX polish) | Low | Low | v0.3 or later |
| Quiet mode | Low (CI/CD) | Trivial | None | v0.3 |

---

## Proposed v0.3 Roadmap

### Phase 1 (Core Architecture)
1. Subprocess pool (`--eval-mode pool` becomes default)
2. Evaluation caching (LRU, in-memory)
3. Static analysis pre-filter

### Phase 2 (Exploration)
4. Beam search (`--strategy beam`, K=3 default)
5. Focused mutation (EVOLVE-BLOCK mode as `--mutation-mode focused`)
6. Multi-turn mutation context (last 3 iterations)

### Phase 3 (Polish)
7. Smarter scaffold template
8. DSPy module save/load
9. Graceful LLM error recovery
10. Quiet mode

### Deferred
- Full population evolution (μ+λ) — v0.4
- Inline `--no-sandbox` eval — v0.4
- `dspy.Assert` for trace recording — v0.4
- CI/CD integration — v0.5
