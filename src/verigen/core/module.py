"""VerifiableCodeGen: a DSPy-native module for evolutionary code optimization."""

import difflib
import time
from typing import Callable, Optional

import dspy
from dspy.utils.exceptions import AdapterParseError

from verigen.core.signatures import GenerateInitialBlock, ImproveBlockMutation
from verigen.core.evaluator import EvaluationResult
from verigen.core.trace import TraceEntry, TraceLogger
from verigen.task.evolve_block import extract_block
from verigen.task.loader import TaskSpec


class VerifiableCodeGen(dspy.Module):
    """A DSPy module that generates and evolutionarily improves code to satisfy
    hard constraints (tests pass) and optimize continuous metrics (latency, score, etc.).

    The module expects a TaskSpec and uses two internal ChainOfThought sub-modules:
    - generator: fills the EVOLVE-BLOCK region for the first time
    - improver: mutates the EVOLVE-BLOCK region guided by evaluation feedback

    Usage:
        gen = VerifiableCodeGen(max_iterations=30)
        result = gen(task)          # task is a TaskSpec
        print(result.best_code)
    """

    def __init__(
        self,
        max_iterations: int = 50,
        score_threshold: Optional[float] = None,
        on_iteration: Optional[Callable] = None,
    ):
        super().__init__()
        self.max_iterations = max_iterations
        self.score_threshold = score_threshold
        self.on_iteration = on_iteration
        self.generator = dspy.ChainOfThought(GenerateInitialBlock)
        self.improver = dspy.ChainOfThought(ImproveBlockMutation)
        self.trace = TraceLogger()

    def forward(self, task: TaskSpec) -> dspy.Prediction:
        """Run the verifiable code generation pipeline.

        Args:
            task: A TaskSpec with description, template (initial.py content),
                  and evaluate_fn (a callable that takes code_str -> EvaluationResult).

        Returns:
            dspy.Prediction with fields:
                best_code: The best program found
                best_score: Its score
                best_feedback: Evaluation feedback for the best program
                trace: TraceLogger with full history
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
            best_code = output.generated_code.strip()
        except AdapterParseError as e:
            best_code = template  # fall back to template if parsing fails
        elapsed = (time.perf_counter() - t0) * 1000

        best_result = task.evaluate_fn(best_code)

        prev_code_for_diff = template

        initial_entry = TraceEntry(
            iteration=0,
            phase="initial",
            block_code=best_code,
            score=best_result.score,
            passed=best_result.passed,
            feedback=best_result.feedback,
            metrics=best_result.metrics,
            change_rationale=None,
            elapsed_ms=elapsed,
            diff_from_previous=_compute_diff(prev_code_for_diff, best_code),
        )
        self.trace.record(initial_entry)
        prev_code_for_diff = best_code

        if self.on_iteration:
            self.on_iteration(
                iteration=0, phase="initial", score=best_result.score,
                passed=best_result.passed, elapsed_ms=elapsed,
                is_best=True,
            )

        # Early exit: if the initial generation fails to pass constraints,
        # mutating from it rarely produces working code. Stop immediately.
        if not best_result.passed:
            return dspy.Prediction(
                best_code=best_code,
                best_score=best_result.score,
                best_feedback=best_result.feedback,
                best_metrics=best_result.metrics,
                n_iterations=len(self.trace.entries),
                trace=self.trace,
                status="initial_failed",
            )

        # ── Phase 2: Evolutionary improvement ────────────────────────
        last_improvement_iter = 0
        previous_rationale = ""

        for i in range(self.max_iterations):
            t0 = time.perf_counter()

            try:
                mutation = self.improver(
                    task_description=task.description,
                    task_context=task.program_context,
                    program_template=template,
                    current_code=best_code,
                    evaluation_feedback=_format_feedback(best_result, i),
                    change_history=previous_rationale,
                )
                candidate_code = mutation.generated_code.strip()
                candidate_rationale = mutation.change_rationale.strip()
            except AdapterParseError:
                # Skip this iteration if the LLM response couldn't be parsed
                candidate_code = best_code
                candidate_rationale = previous_rationale

            if not candidate_code:
                candidate_code = best_code

            candidate_result = task.evaluate_fn(candidate_code)
            elapsed = (time.perf_counter() - t0) * 1000

            # Build the trace entry with diff from previous best
            entry_diff = _compute_diff(prev_code_for_diff, candidate_code)
            self.trace.record(TraceEntry(
                iteration=i + 1,
                phase="mutate",
                block_code=candidate_code,
                score=candidate_result.score,
                passed=candidate_result.passed,
                feedback=candidate_result.feedback,
                metrics=candidate_result.metrics,
                change_rationale=candidate_rationale,
                elapsed_ms=elapsed,
                diff_from_previous=entry_diff,
            ))

            # Keep candidate if it passes and improves score
            improved = False
            if candidate_result.passed and candidate_result.score > best_result.score:
                improved = True
                best_code = candidate_code
                best_result = candidate_result
                last_improvement_iter = i + 1
                prev_code_for_diff = best_code

            previous_rationale = candidate_rationale

            if self.on_iteration:
                self.on_iteration(
                    iteration=i + 1, phase="mutate",
                    score=candidate_result.score,
                    passed=candidate_result.passed,
                    elapsed_ms=elapsed,
                    is_best=improved,
                )

            # Early stop at threshold
            if self.score_threshold is not None and best_result.score >= self.score_threshold:
                break

        # Determine status
        status = _detect_status(
            self.trace, self.score_threshold, last_improvement_iter, self.max_iterations
        )

        return dspy.Prediction(
            best_code=best_code,
            best_score=best_result.score,
            best_feedback=best_result.feedback,
            best_metrics=best_result.metrics,
            n_iterations=len(self.trace.entries),
            trace=self.trace,
            status=status,
        )


def _format_feedback(result: EvaluationResult, iteration: int) -> str:
    """Format an EvaluationResult into a concise feedback string for the improver."""
    lines = [f"Iteration {iteration} evaluation:", f"  Passed: {result.passed}", f"  Score:  {result.score:.4f}"]
    if result.feedback:
        lines.append(f"  Feedback: {result.feedback[:1000]}")
    if result.metrics:
        metrics_str = ", ".join(f"{k}={v:.4f}" for k, v in result.metrics.items())
        lines.append(f"  Metrics: {metrics_str}")
    return "\n".join(lines)


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
    # Near-optimal: score >= 0.85 means ~6x faster than reference — not a plateau
    if trace.best_score >= 0.85:
        return "completed"
    # Plateau: no improvement in the last half of iterations (need ≥ 4 entries)
    if len(trace.entries) >= 4 and last_improvement_iter < len(trace.entries) - 2:
        return "plateau"
    return "completed"
