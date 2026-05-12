"""VerifiableCodeGen: a DSPy-native module for evolutionary code optimization."""

import time
from typing import Callable, Optional

import dspy

from verigen.core.signatures import GenerateInitialBlock, ImproveBlockMutation
from verigen.core.evaluator import EvaluationResult
from verigen.core.trace import TraceEntry, TraceLogger
from verigen.task.evolve_block import extract_block, replace_block
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
    ):
        super().__init__()
        self.max_iterations = max_iterations
        self.score_threshold = score_threshold
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
        output = self.generator(
            task_description=task.description,
            program_template=template,
        )
        initial_block = output.block_implementation.strip()
        initial_code = replace_block(template, initial_block)
        elapsed = (time.perf_counter() - t0) * 1000

        best_block = initial_block
        best_code = initial_code
        best_result = task.evaluate_fn(best_code)

        self.trace.record(TraceEntry(
            iteration=0,
            phase="initial",
            block_code=best_block,
            score=best_result.score,
            passed=best_result.passed,
            feedback=best_result.feedback,
            metrics=best_result.metrics,
            elapsed_ms=elapsed,
        ))

        # ── Phase 2: Evolutionary improvement ────────────────────────
        for i in range(self.max_iterations):
            t0 = time.perf_counter()

            mutation = self.improver(
                task_description=task.description,
                program_context=template,
                current_block_code=best_block,
                evaluation_feedback=_format_feedback(best_result, i),
            )

            candidate_block = mutation.improved_block_code.strip()
            candidate_rationale = mutation.change_rationale.strip()

            if not candidate_block:
                candidate_block = best_block  # skip empty mutations

            candidate_code = replace_block(template, candidate_block)
            candidate_result = task.evaluate_fn(candidate_code)

            elapsed = (time.perf_counter() - t0) * 1000

            self.trace.record(TraceEntry(
                iteration=i + 1,
                phase="mutate",
                block_code=candidate_block,
                score=candidate_result.score,
                passed=candidate_result.passed,
                feedback=candidate_result.feedback,
                metrics=candidate_result.metrics,
                change_rationale=candidate_rationale,
                elapsed_ms=elapsed,
            ))

            # Keep candidate if it passes and improves score
            if candidate_result.passed and candidate_result.score > best_result.score:
                best_block = candidate_block
                best_code = candidate_code
                best_result = candidate_result

            # Early stop at threshold
            if self.score_threshold is not None and best_result.score >= self.score_threshold:
                break

        return dspy.Prediction(
            best_code=best_code,
            best_score=best_result.score,
            best_feedback=best_result.feedback,
            best_metrics=best_result.metrics,
            n_iterations=len(self.trace.entries),
            trace=self.trace,
        )


def _format_feedback(result: EvaluationResult, iteration: int) -> str:
    """Format an EvaluationResult into a concise feedback string for the improver."""
    lines = [f"Iteration {iteration} evaluation:", f"  Passed: {result.passed}", f"  Score:  {result.score:.4f}"]
    if result.feedback:
        lines.append(f"  Feedback: {result.feedback[:500]}")
    if result.metrics:
        metrics_str = ", ".join(f"{k}={v:.4f}" for k, v in result.metrics.items())
        lines.append(f"  Metrics: {metrics_str}")
    return "\n".join(lines)
