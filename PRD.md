# PRD: dspy_verifiable_codegen

**Status:** Draft v0.1  
**Date:** 2026-05-12  
**Author:** luis + pi

---

## 1. Problem Statement

LLMs can generate code, but the code is rarely correct or performant on the first try. Current workflows require manual cycles of "generate → test → fix → retest". We need a **programmatic, self-verifying code generation loop** where an LLM generates code, an automated evaluator scores it, and the system iterates until the code satisfies hard constraints (tests pass) and/or optimizes continuous targets (latency, accuracy, throughput).

Existing solutions (AlphaEvolve, ShinkaEvolve, CodeEvolve) prove the concept but are either closed-source or not DSPy-native. We want a **DSPy-first framework** that combines the expressiveness of DSPy modules, signatures, assertions, and optimizers with an evolutionary code-improvement loop.

---

## 2. Use Cases

### UC1 (MVP): Optimize a Python function for correctness and speed
> "Generate a Python function `fast_matrix_mult(A, B) -> C` that returns correct results (verified against numpy) and minimizes wall-clock time."

The user provides:
- A **task skeleton** (`initial.py` with EVOLVE-BLOCK markers)
- An **evaluator** (`evaluate.py`) that runs tests and measures latency
- Natural language description of what to build

The system produces:
- A correct, performant Python function
- Full DSPy trace of the evolution
- A reusable DSPy module for this class of problem

### UC2: Pass a test suite (hard constraint)
> "Generate a Python function that passes these 3 pytest tests."

Evaluator returns pass/fail. No iteration beyond "all tests green."

### UC3: Optimize a continuous metric (future)
> "Generate a llama-server config that maximizes Qwen3.6 inference throughput while keeping perplexity < 8."

Evaluator returns a float metric. System searches config space.

---

## 3. MVP Scope (v0.1)

### In scope
- **Single-threaded evolution**: one candidate at a time, keep if better
- **Python code generation** via DSPy modules
- **Two optimization levels**:
  - *Primary*: Code-space optimization (evolutionary mutation of generated code)
  - *Secondary*: Prompt/module-space optimization (DSPy optimizers tune the codegen module)
- **Task format**: ShinkaEvolve-inspired `initial.py` (with EVOLVE-BLOCK markers) + `evaluate.py`
- **Sandbox**: subprocess execution with timeout
- **Evaluation schema**: `EvaluationResult(score, passed, feedback, metrics, artifacts)`
- **Outputs**: generated code + DSPy module + DSPy trace/log
- **CLI entry point** for running tasks
- **Example task**: matrix multiplication with correctness + latency optimization

### Not in scope (v0.1)
- UI / dashboard
- Deployment pipeline / CI integration
- Population-based evolution (noted for v0.2)
- Docker sandboxing (noted for v0.2)
- Multi-language support
- Distributed / parallel evaluation

---

## 4. Core Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        verifiable_codegen                           │
│                                                                     │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────────────┐ │
│  │ Task Spec   │   │ DSPy CodeGen │   │ DSPy Mutator             │ │
│  │ initial.py  │──▶│ Module       │──▶│ (ChainOfThought → diff)  │ │
│  │ evaluate.py │   │              │   │                          │ │
│  └─────────────┘   └──────────────┘   └──────────────┬───────────┘ │
│                                                       │             │
│                                                       ▼             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                 Optimizer Loop                                │   │
│  │                                                               │   │
│  │  ┌──────────┐    ┌────────────┐    ┌─────────┐               │   │
│  │  │ Sandbox  │───▶│ Evaluator  │───▶│ Score   │── keep/reject │   │
│  │  │ subproc  │    │ (DSPy)     │    │ Compare  │               │   │
│  │  └──────────┘    └────────────┘    └─────────┘               │   │
│  │                                                               │   │
│  │  ┌──────────────────────────┐                                 │   │
│  │  │ Trace Logger / Archive   │                                 │   │
│  │  └──────────────────────────┘                                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────┐                                   │
│  │ DSPy Optimizer (MIPROv2/etc) │── meta-optimizes codegen modules  │
│  └──────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Technology | Role |
|---|---|---|
| **CodeGenerator** | `dspy.Module` + `dspy.ChainOfThought` | Generate initial program from task spec |
| **CodeMutator** | `dspy.Module` + `dspy.ChainOfThought` | Suggest code diffs given current code + score history |
| **Sandbox** | `subprocess` + `timeout` | Execute generated code in isolation |
| **Evaluator** | Python fn + optional `dspy.Module` | Run tests/metrics, return `EvaluationResult` |
| **Optimizer** | Custom evolutionary loop | Manage code-space search, keep/reject, trace |
| **Meta-Optimizer** | `dspy.MIPROv2` / `BootstrapFewShotWithRandomSearch` | Tune prompts/modules for the codegen pipeline |
| **Trace Logger** | `dspy.Settings` + structured logging | Record every gen, mutation, eval, decision |

---

## 5. EvaluationResult Schema

```python
@dataclass
class EvaluationResult:
    score: float                # 0.0-1.0 or unbounded, higher = better
    passed: bool                # hard constraint gate (e.g., all tests green)
    feedback: str               # LLM-friendly description of what's wrong/right
    metrics: dict[str, float]   # structured metrics for traceability & analysis
    artifacts: dict[str, str]   # generated outputs, logs, stdout/stderr
```

---

## 6. Success Criteria (v0.1)

1. **End-to-end run**: `uv run verigen examples/fast_matrix_mult/` generates a correct, optimized function
2. **DSPy trace**: Full history of generations, mutations, scores, and outcomes is recorded
3. **Reusable module**: `from verigen import VerifiableCodeGen` works as a DSPy module
4. **Hard constraints respected**: If `passed=False`, the candidate is rejected regardless of score
5. **Metric improvement**: Over N iterations, the best score monotonically improves (or plateaus)
6. **Example task**: Matrix multiplication with numpy correctness check + `time.perf_counter` latency

---

## 7. Future Vision (v0.2+)

| Feature | Priority | Notes |
|---|---|---|
| Population-based evolution | High | Archive DB, parent selection, diversity scoring |
| Docker sandboxing | High | For untrusted code execution |
| Parallel evaluation | Medium | Speed up population-based search |
| LLM-as-judge evaluator | Medium | When no programmatic metric exists |
| Web UI for monitoring | Low | Real-time evolution visualization (Shinka-style) |
| Multi-language support | Low | Shell scripts, SQL, configs |
| CI integration | Low | GitHub Actions runner |
| Task registry / hub | Low | Share tasks across users |

---

## 8. Constraints & Risks

| Risk | Mitigation |
|---|---|
| LLM cost for evolutionary loop | Track per-run costs; cap iterations |
| Infinite loops / stagnation | Max iterations, early stopping on plateau |
| Sandbox escape | subprocess timeout + resource limits; Docker in v0.2 |
| Non-deterministic evaluation | Run multiple trials, aggregate metrics |
| DSPy optimizer slow with inner loops | Outer DSPy optimization is offline/batch, not per-evolution-step |
