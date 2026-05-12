"""verigen: DSPy-native verifiable code generation through evolutionary optimization."""

from verigen.core.module import VerifiableCodeGen
from verigen.core.evaluator import EvaluationResult
from verigen.task.loader import TaskSpec, load_task, make_task
from verigen.core.trace import TraceLogger, TraceEntry

__all__ = [
    "VerifiableCodeGen",
    "EvaluationResult",
    "TaskSpec",
    "load_task",
    "make_task",
    "TraceLogger",
    "TraceEntry",
]
