"""Task specification loading from a task directory."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

from verigen.core.evaluator import EvaluationResult, evaluate_in_sandbox
from verigen.task.evolve_block import extract_block


@dataclass
class TaskSpec:
    """A verifiable code generation task.

    Attributes:
        description: First heading from program.md.
        program_context: Full content of program.md for rich task instructions.
        template: Content of initial.py with EVOLVE-BLOCK-START/END markers.
        eval_module_path: Absolute path to evaluate.py.
        evaluate_fn: Bound evaluator (calls evaluate_in_sandbox with this task's evaluate.py).
    """
    description: str
    program_context: str
    template: str
    eval_module_path: str
    evaluate_fn: Callable[[str], EvaluationResult] = field(repr=False)


def load_task(task_dir: Union[str, Path], timeout: int = 30) -> TaskSpec:
    """Load a verifiable code generation task from a directory.

    Expected directory contents:
        initial.py        – code template with EVOLVE-BLOCK-START/END markers
        evaluate.py       – exports evaluate(code_str: str) -> dict
        program.md        – instructions/research program for the agent (markdown)

    The first line or first `# Heading` of program.md becomes the task description.
    The full content is stored as program_context for richer agent prompts.

    Args:
        task_dir: Path to the task directory.
        timeout: Default timeout in seconds for evaluation subprocess.

    Returns:
        A TaskSpec ready to pass to VerifiableCodeGen.
    """
    task_dir = Path(task_dir).resolve()
    initial_path = task_dir / "initial.py"
    eval_path = task_dir / "evaluate.py"
    program_path = task_dir / "program.md"

    if not initial_path.exists():
        raise FileNotFoundError(f"Missing {initial_path}")
    if not eval_path.exists():
        raise FileNotFoundError(f"Missing {eval_path}")
    if not program_path.exists():
        raise FileNotFoundError(f"Missing {program_path}")

    # Read template
    template = initial_path.read_text()
    if not extract_block(template):
        raise ValueError(
            f"{initial_path} must contain EVOLVE-BLOCK-START and EVOLVE-BLOCK-END markers"
        )

    # Read description and full context from program.md
    description = _read_description(program_path)
    program_context = program_path.read_text()

    # Create the bound evaluator
    eval_path_str = str(eval_path)

    def evaluate_fn(code_str: str) -> EvaluationResult:
        return evaluate_in_sandbox(eval_path_str, code_str, timeout=timeout)

    return TaskSpec(
        description=description,
        program_context=program_context,
        template=template,
        eval_module_path=eval_path_str,
        evaluate_fn=evaluate_fn,
    )


def _read_description(md_path: Path) -> str:
    """Extract a short description from a markdown file.

    Uses the first `# Heading` line, falling back to the first non-empty line.
    """
    content = md_path.read_text()
    lines = content.splitlines()
    # Prefer a level-1 heading
    for line in lines:
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    # Fall back to first non-empty line
    for line in lines:
        s = line.strip()
        if s:
            return s
    return ""


def make_task(
    description: str,
    template: str,
    eval_code: str,
    eval_module_path: Optional[Union[str, Path]] = None,
    program_context: str = "",
    timeout: int = 30,
) -> TaskSpec:
    """Create a TaskSpec programmatically (e.g., from tests).

    Writes evaluate.py to a temp location.
    """
    import tempfile as tf

    if eval_module_path:
        eval_path = Path(eval_module_path)
    else:
        tmp_dir = Path(tf.mkdtemp(prefix="verigen_task_"))
        eval_path = tmp_dir / "evaluate.py"
        eval_path.write_text(eval_code)

    return TaskSpec(
        description=description,
        program_context=program_context,
        template=template,
        eval_module_path=str(eval_path),
        evaluate_fn=lambda code: evaluate_in_sandbox(str(eval_path), code, timeout=timeout),
    )
