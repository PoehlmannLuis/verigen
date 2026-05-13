"""VerifiableCodeGen: DSPy-native module for evolutionary code optimization.

Supports greedy (default), beam search, and focused mutation strategies.
"""

import difflib
import random
import time
from typing import Callable, Optional

import dspy
from dspy.utils.exceptions import AdapterParseError

from verigen.core.signatures import GenerateInitialBlock, ImproveBlockMutation, FocusedBlockMutation
from verigen.core.evaluator import EvaluationResult
from verigen.core.trace import TraceEntry, TraceLogger
from verigen.task.evolve_block import extract_block, replace_block_content
from verigen.task.loader import TaskSpec


_DSPY_LEAK_PATTERNS = [
    "Respond with the corresponding output fields",
    "[[ ## reasoning ## ]]",
    "[[ ## generated_code ## ]]",
    "[[ ## completed ## ]]",
]


def _clean_dspy_output(code: str) -> str:
    """Strip DSPy chain-of-thought format markers that sometimes leak into code."""
    for marker in _DSPY_LEAK_PATTERNS:
        idx = code.find(marker)
        if idx != -1:
            code = code[:idx]
    return code.strip()


class VerifiableCodeGen(dspy.Module):
    """A DSPy module that generates and evolutionarily improves code to satisfy
    hard constraints (tests pass) and optimize continuous metrics (latency, score, etc.).

    Supports multiple strategies:
    - 'greedy' (default): single best candidate, hill-climbing
    - 'beam': keep top-K candidates, weighted selection

    And multiple mutation modes:
    - 'full': LLM rewrites the entire program
    - 'focused': LLM only rewrites the EVOLVE-BLOCK region

    Usage:
        gen = VerifiableCodeGen(max_iterations=30, strategy='beam', beam_width=3)
        result = gen(task)
        print(result.best_code)
    """

    def __init__(
        self,
        max_iterations: int = 50,
        score_threshold: Optional[float] = None,
        on_iteration: Optional[Callable] = None,
        strategy: str = "greedy",
        beam_width: int = 3,
        mutation_mode: str = "full",
    ):
        super().__init__()
        self.max_iterations = max_iterations
        self.score_threshold = score_threshold
        self.on_iteration = on_iteration
        self.strategy = strategy
        self.beam_width = max(1, beam_width)
        self.mutation_mode = mutation_mode
        self.trace = TraceLogger()

        # Sub-modules
        self.generator = dspy.ChainOfThought(GenerateInitialBlock)
        self.improver = dspy.ChainOfThought(ImproveBlockMutation)
        self.focused_improver = dspy.ChainOfThought(FocusedBlockMutation)

    def forward(self, task: TaskSpec) -> dspy.Prediction:
        """Run the verifiable code generation pipeline.

        Args:
            task: A TaskSpec with description, template (initial.py content),
                  evaluate_fn, and expected_name (for static pre-filter).

        Returns:
            dspy.Prediction with fields:
                best_code, best_score, best_feedback, trace, status, strategy
        """
        self.trace = TraceLogger()
        template = task.template

        # ── Phase 1: Initial generation ──────────────────────────────
        t0 = time.perf_counter()
        try:
            output = self.generator(
                task_description=task.description,
                task_context=task.program_context,
                program_template=template,
            )
            best_code = _clean_dspy_output(output.generated_code)
        except AdapterParseError:
            best_code = template
        elapsed = (time.perf_counter() - t0) * 1000

        best_result = task.evaluate_fn(best_code)

        initial_entry = TraceEntry(
            iteration=0, phase="initial",
            block_code=best_code,
            score=best_result.score,
            passed=best_result.passed,
            feedback=best_result.feedback,
            metrics=best_result.metrics,
            change_rationale=None,
            elapsed_ms=elapsed,
            diff_from_previous=_compute_diff(template, best_code),
        )
        self.trace.record(initial_entry)

        self._notify(iteration=0, phase="initial", score=best_result.score,
                     passed=best_result.passed, elapsed_ms=elapsed, is_best=True)

        if not best_result.passed:
            return self._result(best_code, best_result, "initial_failed")

        # ── Phase 2: Evolutionary improvement ────────────────────────
        if self.strategy == "beam":
            return self._run_beam(task, template, best_code, best_result)
        else:
            return self._run_greedy(task, template, best_code, best_result)

    # ── Greedy Hill-Climbing ──────────────────────────────────────────────

    def _run_greedy(self, task: TaskSpec, template: str,
                    best_code: str, best_result: EvaluationResult) -> dspy.Prediction:
        """Standard single-best hill-climbing."""
        last_improvement_iter = 0
        change_history = _ChangeHistory()

        for i in range(self.max_iterations):
            t0 = time.perf_counter()

            candidate_code, candidate_rationale = self._mutate(
                task, template, best_code, best_result,
                change_history.format(),
            )

            candidate_result = task.evaluate_fn(candidate_code)
            elapsed = (time.perf_counter() - t0) * 1000

            change_history.record(candidate_rationale, candidate_result.score, candidate_result.passed)

            self._record_trace(
                i + 1, phase="mutate", code=candidate_code,
                result=candidate_result, rationale=candidate_rationale,
                elapsed=elapsed, is_best=False,
            )

            improved = False
            if candidate_result.passed and candidate_result.score > best_result.score:
                improved = True
                best_code = candidate_code
                best_result = candidate_result
                last_improvement_iter = i + 1
                self.trace.entries[-1].diff_from_previous = _compute_diff(
                    self.trace.entries[-2].block_code if len(self.trace.entries) >= 2 else template,
                    candidate_code,
                )

            self._notify(iteration=i + 1, phase="mutate",
                         score=candidate_result.score, passed=candidate_result.passed,
                         elapsed_ms=elapsed, is_best=improved)

            if self.score_threshold is not None and best_result.score >= self.score_threshold:
                break

        status = _detect_status(self.trace, self.score_threshold,
                                last_improvement_iter, self.max_iterations)
        return self._result(best_code, best_result, status)

    # ── Beam Search ──────────────────────────────────────────────────────

    def _run_beam(self, task: TaskSpec, template: str,
                  initial_code: str, initial_result: EvaluationResult) -> dspy.Prediction:
        """Beam search: keeps top-K candidates, selects parents weighted by score."""
        beam: list = [(initial_code, initial_result, _ChangeHistory())]
        last_improvement_iter = 0

        for i in range(self.max_iterations):
            # Select parent weighted by score
            parent_code, parent_result, parent_history = _select_parent(beam)

            t0 = time.perf_counter()

            candidate_code, candidate_rationale = self._mutate(
                task, template, parent_code, parent_result,
                parent_history.format(),
            )

            candidate_result = task.evaluate_fn(candidate_code)
            elapsed = (time.perf_counter() - t0) * 1000

            self._record_trace(
                i + 1, phase="mutate", code=candidate_code,
                result=candidate_result, rationale=candidate_rationale,
                elapsed=elapsed, is_best=False,
            )

            improved = False
            if candidate_result.passed:
                beam.append((candidate_code, candidate_result, _ChangeHistory()))
                beam.sort(key=lambda x: x[1].score, reverse=True)
                beam = beam[:self.beam_width]

                if candidate_result.score > beam[0][1].score:
                    improved = True
                    last_improvement_iter = i + 1

            self._notify(iteration=i + 1, phase="mutate",
                         score=candidate_result.score, passed=candidate_result.passed,
                         elapsed_ms=elapsed, is_best=improved)

            if self.score_threshold is not None and beam[0][1].score >= self.score_threshold:
                break

        best_code, best_result, _ = beam[0]
        status = _detect_status(self.trace, self.score_threshold,
                                last_improvement_iter, self.max_iterations)
        return self._result(best_code, best_result, status)

    # ── Mutation (shared between strategies) ─────────────────────────────

    def _mutate(self, task: TaskSpec, template: str,
                code: str, result: EvaluationResult,
                change_history: str) -> tuple[str, str]:
        """Produce a candidate by mutating the given code.

        Returns (candidate_code, candidate_rationale).
        Handles AdapterParseError by falling back to the original code.
        """
        feedback = _format_feedback(result)

        if self.mutation_mode == "focused":
            return self._mutate_focused(task, template, code, feedback, change_history)
        else:
            return self._mutate_full(task, template, code, feedback, change_history)

    def _mutate_full(self, task: TaskSpec, template: str,
                     code: str, feedback: str,
                     change_history: str) -> tuple[str, str]:
        """Full-program mutation: LLM rewrites the entire program."""
        try:
            mutation = self.improver(
                task_description=task.description,
                task_context=task.program_context,
                program_template=template,
                current_code=code,
                evaluation_feedback=feedback,
                change_history=change_history,
            )
            candidate = _clean_dspy_output(mutation.generated_code)
            rationale = mutation.change_rationale.strip()
            return candidate or code, rationale
        except AdapterParseError:
            return code, ""

    def _mutate_focused(self, task: TaskSpec, template: str,
                        code: str, feedback: str,
                        change_history: str) -> tuple[str, str]:
        """Focused mutation: LLM rewrites only the EVOLVE-BLOCK region."""
        current_block = extract_block(code)
        if current_block is None:
            return code, ""

        try:
            output = self.focused_improver(
                task_description=task.description,
                task_context=task.program_context,
                surrounding_context=code,
                current_block=current_block,
                evaluation_feedback=feedback,
                change_history=change_history,
            )
            new_block = _clean_dspy_output(output.new_block)
            candidate = replace_block_content(code, new_block)
            # Validate: if the focused mutation produces broken syntax,
            # fall back to the original code
            if candidate != code:
                try:
                    compile(candidate, "<focused>", "exec")
                except SyntaxError:
                    return code, ""
            rationale = output.change_rationale.strip()
            return candidate or code, rationale
        except AdapterParseError:
            return code, ""

    # ── Helpers ──────────────────────────────────────────────────────────

    def _record_trace(self, iteration: int, phase: str,
                      code: str, result: EvaluationResult,
                      rationale: str, elapsed: float, is_best: bool):
        self.trace.record(TraceEntry(
            iteration=iteration, phase=phase,
            block_code=code,
            score=result.score,
            passed=result.passed,
            feedback=result.feedback,
            metrics=result.metrics,
            change_rationale=rationale,
            elapsed_ms=elapsed,
        ))

    def _notify(self, iteration, phase, score, passed, elapsed_ms, is_best):
        if self.on_iteration:
            self.on_iteration(
                iteration=iteration, phase=phase,
                score=score, passed=passed,
                elapsed_ms=elapsed_ms, is_best=is_best,
            )

    def _result(self, code: str, result: EvaluationResult, status: str) -> dspy.Prediction:
        return dspy.Prediction(
            best_code=code,
            best_score=result.score,
            best_feedback=result.feedback,
            best_metrics=result.metrics,
            n_iterations=len(self.trace.entries),
            trace=self.trace,
            status=status,
            strategy=self.strategy,
        )


# ── Change History (multi-turn context) ────────────────────────────────────

class _ChangeHistory:
    """Tracks the last N (rationale, score, passed) tuples for multi-turn context."""

    def __init__(self, max_len: int = 3):
        self._entries: list[tuple[str, float, bool]] = []
        self._max_len = max_len

    def record(self, rationale: str, score: float, passed: bool):
        if rationale:
            self._entries.append((rationale, score, passed))
            self._entries = self._entries[-self._max_len:]

    def format(self) -> str:
        if not self._entries:
            return "No previous changes yet."
        parts = ["Previous changes and their outcomes:"]
        for i, (rationale, score, passed) in enumerate(self._entries):
            status = "passed ✓" if passed else "FAILED ✗"
            truncated = rationale[:300] if rationale else "(no rationale)"
            parts.append(f"  {i+1}. [{status}, score={score:.4f}] {truncated}")
        return "\n".join(parts)


# ── Beam Selection ─────────────────────────────────────────────────────────

def _select_parent(beam: list) -> tuple:
    """Weighted random selection from the beam. Higher score = higher weight."""
    scores = [r.score for _, r, _ in beam]
    # Ensure all positive for weights
    min_s = min(scores)
    weights = [s - min_s + 0.01 for s in scores]
    total = sum(weights)
    if total <= 0:
        weights = [1.0 / len(beam)] * len(beam)
    else:
        weights = [w / total for w in weights]
    return random.choices(beam, weights=weights, k=1)[0]


# ── Feedback Formatting ────────────────────────────────────────────────────

def _format_feedback(result: EvaluationResult) -> str:
    """Format an EvaluationResult into a concise feedback string for the improver."""
    lines = [f"Passed: {result.passed}", f"Score:  {result.score:.4f}"]
    if result.feedback:
        lines.append(f"Feedback: {result.feedback[:1000]}")
    if result.metrics:
        metrics_str = ", ".join(f"{k}={v:.4f}" for k, v in result.metrics.items())
        lines.append(f"Metrics: {metrics_str}")
    return "\n".join(lines)


# ── Diff Computation ───────────────────────────────────────────────────────

def _compute_diff(old_code: str, new_code: str) -> str:
    """Compute a compact unified diff between two code strings."""
    if old_code == new_code:
        return ""
    diff = difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile="previous", tofile="current", n=3,
    )
    return "".join(diff)


# ── Status Detection ───────────────────────────────────────────────────────

def _detect_status(
    trace: TraceLogger,
    threshold: Optional[float],
    last_improvement_iter: int,
    max_iters: int,
) -> str:
    """Detect the run status based on the trace history."""
    if not trace.entries:
        return "empty"
    if trace.entries[0].phase == "initial" and not trace.entries[0].passed:
        return "initial_failed"
    if threshold is not None and trace.best_score >= threshold:
        return "threshold_reached"
    if trace.best_score >= 0.85:
        return "completed"
    if len(trace.entries) >= 4 and last_improvement_iter < len(trace.entries) - 2:
        return "plateau"
    return "completed"
