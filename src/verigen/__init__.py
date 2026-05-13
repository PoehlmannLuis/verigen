"""verigen: DSPy-native verifiable code generation through evolutionary optimization.

v0.3 — Worker pool, beam search, focused mutation, caching, static pre-filter.
"""

from verigen.core.module import VerifiableCodeGen
from verigen.core.evaluator import EvaluationResult, EvalWorkerPool, prefilter_code
from verigen.task.loader import TaskSpec, load_task, make_task
from verigen.core.trace import TraceLogger, TraceEntry

__all__ = [
    "VerifiableCodeGen",
    "EvaluationResult",
    "EvalWorkerPool",
    "prefilter_code",
    "TaskSpec",
    "load_task",
    "make_task",
    "TraceLogger",
    "TraceEntry",
]
