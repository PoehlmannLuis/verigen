# ADR: Architecture Decisions for dspy_verifiable_codegen

**Status:** Draft  
**Date:** 2026-05-12  
**Deciders:** luis, pi  
**Context:** PRD v0.1 defines a DSPy-native framework for verifiable code generation with evolutionary optimization.

---

## ADR-001: DSPy-First Architecture

### Decision
The entire pipeline is implemented as a `dspy.Module` hierarchy. Every operation — initial code generation, code mutation, evaluation analysis — is a DSPy module with typed signatures. The main entry point `VerifiableCodeGen` is itself a `dspy.Module`.

### Rationale
- Full DSPy traceability: every forward pass, every assertion, every score is captured by `dspy.Settings.trace`
- DSPy optimizers (MIPROv2, BootstrapFewShotWithRandomSearch) can directly optimize the codegen modules
- `dspy.Assert` provides native hard-constraint enforcement
- DSPy's provider abstraction means zero lock-in on LLM backend
- The module can be saved, reloaded, and reused across tasks with `dspy.Module.save()` / `load()`

### Consequences
- Positive: traceability, optimizability, provider flexibility, reuse
- Negative: tight coupling to DSPy's API evolution; but DSPy 2.6+ is mature enough
- The evolutionary loop (mutations, keep/reject, archive) is not a standard DSPy pattern — we'll implement it as a custom optimizer or within `forward()`

---

## ADR-002: Two-Level Optimization Strategy (Prompt Space + Code Space)

### Context
The user identified two distinct optimization targets:
1. **Prompt/module space** — DSPy optimizers tune the instructions, few-shot examples, and module structure used for code generation
2. **Code space** — An evolutionary loop mutates the generated program directly, searching the space of implementations

### Decision
**Both, with code-space as the primary loop and prompt-space as a meta-optimizer.**

Architecture:

```
┌────────────────────────────────────────────────────────────────────┐
│  META-OPTIMIZER (DSPy: MIPROv2 / BootstrapFewShotWithRandomSearch) │
│  Runs across task instances or between evolutionary runs          │
│  Target: improve the CodeGenerator and CodeMutator modules        │
│  Frequency: offline / batch                                       │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ produces better modules
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  PRIMARY LOOP: Code-Space Evolution (per task instance)            │
│                                                                    │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌───────────────┐  │
│  │ Generate │──▶│ Mutate   │──▶│ Evaluate │──▶│ Keep if better│  │
│  │ initial  │   │ (diff)   │   │ (subproc)│   │ (score gate)  │  │
│  └──────────┘   └──────────┘   └──────────┘   └───────────────┘  │
│                                                                    │
│  Hard constraints enforced via dspy.Assert at each candidate       │
│  Continuous metrics compared via score threshold                   │
│  Full trace logged to DSPy settings + structured history           │
└────────────────────────────────────────────────────────────────────┘
```

### Pros/Cons of Each Approach

| Aspect | Prompt-Space Only | Code-Space Only | Both (this ADR) |
|---|---|---|---|
| **Direct impact on generated code** | Indirect (better prompts → better first attempts) | Direct (each iteration produces better code) | Direct + indirect |
| **Search space** | Small (prompt variants, few-shot selection) | Large and unbounded (all possible programs) | Two spaces, different dynamics |
| **DSPy-native support** | ✅ First-class (MIPROv2, BootstrapFS, etc.) | ❌ Not natively supported (custom implementation) | Custom for code, native for prompts |
| **Cross-task transfer** | ✅ Better prompting strategies generalize | ❌ Code improvements are task-specific | Both types of transfer |
| **Diminishing returns** | Rapid saturation | Slow saturation (infinite space) | Prompt optimization extends code-space reach |
| **Complexity** | Low | Medium | High |
| **LLM call cost** | Low (few optimization rounds) | High (N iterations × M candidates) | Higher |
| **Attribution** | Easy | Easy | Hard — which level caused improvement? |

### Implications for v0.1

1. **Code-space is the primary loop** because:
   - It directly produces better code for the user's task
   - The matrix multiplication use case benefits from algorithmic mutations (tiling, vectorization, cache-aware ordering) that no prompt tuning can discover
   - This is what AlphaEvolve and ShinkaEvolve proved effective

2. **Prompt-space optimization is a separate offline phase** because:
   - Running MIPROv2 requires multiple task instances as training data
   - Each "evaluation" in DSPy optimizer terms requires a full evolutionary run (expensive)
   - Instead: collect traces from real runs, then apply DSPy optimizer to improve modules for future tasks

3. **Integration pattern:**
   - `CodeGenerator` and `CodeMutator` are `dspy.ChainOfThought` modules with well-defined signatures
   - They can be optimized with DSPy's optimizers *in between* task runs
   - The evolutionary loop itself is inside `VerifiableCodeGen.forward()`, which is a `dspy.Module`
   - This means the entire evolutionary trace is captured by DSPy's trace system

### Future: Lifting Code-Space into a Custom DSPy Optimizer

For v0.2+, we can wrap the evolutionary loop as a `dspy.Optimizer` subclass. This would make `VerifiableCodeGen` optimizable by standard DSPy tools, at the cost of more engineering.

---

## ADR-003: Task Specification Format

### Decision
Adopt the ShinkaEvolve pattern: the user provides two files per task:

```python
# initial.py — seed code with EVOLVE-BLOCK markers around editable regions
def solve_problem(**kwargs):
    # EVOLVE-BLOCK-START
    # This region will be mutated by the system
    result = None
    # EVOLVE-BLOCK-END
    return result
```

```python
# evaluate.py — must export a callable that takes (code_str, **kwargs) → EvaluationResult
from verigen import EvaluationResult

def evaluate(code_str: str, **kwargs) -> EvaluationResult:
    exec(code_str, globals())
    # ... run tests, measure latency ...
    return EvaluationResult(
        score=latency_score,
        passed=all_tests_pass,
        feedback="...",
        metrics={"latency_ms": 42.0},
        artifacts={}
    )
```

### Rationale
- Proven in ShinkaEvolve — clear separation between "what to edit" and "how to score"
- EVOLVE-BLOCK markers give the mutator a focused region, preventing irrelevant changes
- `evaluate.py` is a Python module — maximum flexibility for scoring logic
- Task directories are self-contained and portable

### Consequences
- Users must define EVOLVE-BLOCK boundaries carefully — too narrow limits search, too wide wastes LLM tokens
- `evaluate.py` can call any Python (pytest, time.perf_counter, external APIs) — this is intentional flexibility

---

## ADR-004: Single-Thread Evolution (v0.1)

### Decision
The evolutionary loop maintains exactly **one current best candidate**. Each iteration:
1. Mutates the best candidate to produce one child
2. Evaluates the child
3. If child.score > best.score AND child.passed → replace best
4. Otherwise → discard

No population, no archive, no parent selection.

### Rationale
- Simplest possible implementation — ship v0.1 in days, not weeks
- Single-thread avoids archive DB, diversity scoring, parallel eval infrastructure
- Still demonstrates the core verifiable codegen concept
- AlphaEvolve's population / ShinkaEvolve's archive can be layered on when the single-thread loop plateaus

### Future (ADR-004b)
Population-based evolution with:
- Archive of top-K programs per "island"
- Parent selection: weighted random by score
- Diversity scoring: embedding similarity + LLM novelty judge (ShinkaEvolve pattern)
- Parallel evaluation: subprocess pool or Slurm

---

## ADR-005: Sandboxing Strategy

### Decision
**v0.1:** Python `subprocess` with `timeout` and resource limits (`resource.setrlimit`).

```python
import subprocess, resource, signal

def sandboxed_exec(code: str, timeout_s: int = 30):
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
        f.write(code)
        f.flush()
        proc = subprocess.run(
            ['python3', f.name],
            capture_output=True, text=True,
            timeout=timeout_s,
            preexec_fn=lambda: resource.setrlimit(
                resource.RLIMIT_CPU, (timeout_s, timeout_s)
            )
        )
    return proc.stdout, proc.stderr, proc.returncode
```

### Rationale
- Zero infrastructure dependencies for v0.1
- `subprocess` provides process-level isolation (separate memory, can be killed)
- `resource.setrlimit` prevents CPU abuse
- Timeout prevents infinite loops

### Future (ADR-005b)
Docker-based sandboxing:
- Immutable container with only stdlib + specified dependencies
- Network disabled by default
- Memory and CPU limits via Docker SDK
- Clean filesystem per execution
- No persistent state between runs

---

## ADR-006: Evaluation Model

### Decision
Use the `EvaluationResult` schema as the universal return type for all evaluators:

```python
@dataclass
class EvaluationResult:
    score: float                # 0.0-1.0 or unbounded, higher = better
    passed: bool                # Hard constraint gate
    feedback: str               # LLM-friendly description
    metrics: dict[str, float]   # Structured metrics
    artifacts: dict[str, str]   # Outputs, logs, errors
```

The evaluator is a **pure Python function** (not a DSPy module by default). It:
- Receives the generated code as a string
- Executes it in a sandbox
- Collects stdout/stderr/returncode
- Computes pass/fail and score
- Returns `EvaluationResult`

### Rationale
- `passed` as a separate field from `score` enforces the hard/soft distinction
- `feedback` provides rich signal for the next mutation (the LLM mutator reads this)
- `metrics` enables structured analysis across runs
- Pure Python evaluators keep the interface simple and testable
- Optional: an `LLMEvaluator` module can wrap this pattern for LLM-as-judge use cases

### Consequences
- The mutator's prompt is constructed from `feedback` primarily, `metrics` secondarily
- Non-deterministic evaluators (e.g., latency measurement) should average multiple trials
- `artifacts` is deliberately open-ended — stdout, stderr, plots, intermediate results

---

## ADR-007: Project Outputs

### Decision
Each run produces three output artifacts:

| Artifact | Format | Purpose |
|---|---|---|
| **Generated program** | `.py` file | The best program found, ready to use |
| **VerifiableCodeGen module** | `dspy.Module` (pickled JSON) | Reusable for similar tasks or continued optimization |
| **Run trace** | JSON Lines / DSPy trace | Full history of all attempts, scores, mutations, decisions |

### Rationale
- The generated program is the primary deliverable — the user wants to *use* this code
- The DSPy module captures the learned behavior (prompts, examples, structure) and can be reloaded
- The trace enables debugging, analysis, and transparency — critical for understanding *why* the system made certain choices

### Implementation
```python
# Output structure
run_dir/
├── best_program.py           # Best code found
├── module.json               # dspy.Module state (save/load)
├── trace.jsonl               # One JSON object per iteration
│   ├── { iteration, phase, code_hash, score, passed, feedback, mutation_rationale }
│   └── ...
└── config.json               # Task config, DSPy settings, model info
```

---

## ADR-008: DSPy Providers for LLM Flexibility

### Decision
Use DSPy's `dspy.LM` abstraction exclusively. No direct API calls to any provider.

```python
# User configures once in settings.json or env
dspy.configure(lm=dspy.LM(model="openai/gpt-4o"))
# Or with local models:
dspy.configure(lm=dspy.LM(model="ollama_chat/qwen3.6", api_base="http://localhost:11434"))
# Or llama-server:
dspy.configure(lm=dspy.LM(model="openai/qwen3.6", api_base="http://localhost:8080/v1"))
```

### Rationale
- DSPy's `dspy.LM` supports OpenAI, Anthropic, Google, Ollama, llama.cpp (vLLM-compatible), AWS Bedrock, and more
- Zero provider lock-in
- The same code works with GPT-4o, Claude 4, Gemini 3, Qwen 3.6, etc.
- Different models can be assigned to different modules (e.g., Gemini Flash for breadth, Gemini Pro for depth, as in AlphaEvolve)

### Consequences
- Users need DSPy-compatible provider setup
- Some advanced features (function calling, structured output) may vary by provider
- Local models via llama-server work out of the box with `openai/` prefix

---

## Decisions Log

| ID | Decision | Status |
|---|---|---|
| ADR-001 | DSPy-First Architecture | Accepted |
| ADR-002 | Two-Level Optimization (code primary, prompt meta) | Accepted |
| ADR-003 | ShinkaEvolve task format (initial.py + evaluate.py) | Accepted |
| ADR-004 | Single-thread evolution, population deferred | Accepted |
| ADR-005 | Subprocess sandboxing, Docker deferred | Accepted |
| ADR-006 | EvaluationResult schema as universal return type | Accepted |
| ADR-007 | Three output artifacts: code + module + trace | Accepted |
| ADR-008 | DSPy LM abstraction for provider flexibility | Accepted |
