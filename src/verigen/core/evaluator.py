"""Evaluation model and sandboxed execution for generated code."""

import atexit
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Union

# Track temp code files for cleanup even if the process is killed mid-run.
# Using a module-level list because atexit doesn't run on SIGKILL.
_temp_files: list[str] = []


def _cleanup_temp_files() -> None:
    """Remove all tracked temp code files. Registered with atexit."""
    for path in _temp_files[:]:
        try:
            if os.path.exists(path):
                os.unlink(path)
                _temp_files.remove(path)
        except OSError:
            pass


atexit.register(_cleanup_temp_files)


@dataclass
class EvaluationResult:
    """Result from evaluating generated code.

    Attributes:
        score: Continuous metric value (higher = better). For hard constraints only, use 1.0.
        passed: Whether hard constraints (tests) passed.
        feedback: Natural language description of results, errors, and improvement suggestions.
        metrics: Structured numeric metrics for traceability.
        artifacts: Arbitrary string outputs (stdout, stderr, logs, etc.).
    """
    score: float = 0.0
    passed: bool = False
    feedback: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)


def evaluate_in_sandbox(
    eval_module_path: Union[str, Path],
    code_str: str,
    timeout: int = 30,
) -> EvaluationResult:
    """Evaluate generated code by running evaluate() from eval_module_path in a subprocess.

    This provides process-level isolation: the generated code runs in a clean
    subprocess and cannot affect the parent.

    Args:
        eval_module_path: Path to evaluate.py that exports an evaluate(code_str) -> dict function.
        code_str: The generated Python code to evaluate.
        timeout: Maximum execution time in seconds.

    Returns:
        EvaluationResult parsed from the subprocess output.
    """
    eval_path = Path(eval_module_path).resolve()
    eval_dir = eval_path.parent

    proc = None
    code_filename = None

    try:
        # Write code to a temp file so the subprocess can read it
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix="verigen_code_",
        )
        tmp.write(code_str)
        tmp.flush()
        code_filename = tmp.name
        tmp.close()
        _temp_files.append(code_filename)

        runner = textwrap.dedent(f"""
        import sys, json, os

        sys.path.insert(0, {str(eval_dir)!r})
        os.chdir({str(eval_dir)!r})

        from evaluate import evaluate

        with open({code_filename!r}) as f:
            code = f.read()

        try:
            result = evaluate(code)
        except Exception as e:
            result = {{
                "score": 0.0,
                "passed": False,
                "feedback": f"Evaluator raised {{type(e).__name__}}: {{e}}",
                "metrics": {{}},
                "artifacts": {{}}
            }}

        print("__VERIGEN_RESULT__")
        print(json.dumps(result))
        """)

        proc = subprocess.run(
            [sys.executable, "-c", runner],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        stdout_str = proc.stdout or ""
        stderr_str = proc.stderr or ""

        # Parse the JSON result following the marker.
        # Do the split once — the old code called splitlines() inside the loop.
        lines = stdout_str.splitlines()
        result_json = None
        for i, line in enumerate(lines):
            if line.strip() == "__VERIGEN_RESULT__":
                if i + 1 < len(lines):
                    result_json = lines[i + 1]
                break

        if result_json is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                feedback=_fallback_feedback(stdout_str, stderr_str),
                artifacts={"stdout": stdout_str, "stderr": stderr_str},
            )

        result_dict = json.loads(result_json)
        return EvaluationResult(**result_dict)

    except subprocess.TimeoutExpired:
        return EvaluationResult(
            score=0.0,
            passed=False,
            feedback=f"Evaluation timed out after {timeout}s.",
        )
    except json.JSONDecodeError as e:
        stdout_str = proc.stdout if proc else ""
        stderr_str = proc.stderr if proc else ""
        return EvaluationResult(
            score=0.0,
            passed=False,
            feedback=f"Failed to parse evaluation result: {e}",
            artifacts={"stdout": stdout_str, "stderr": stderr_str},
        )
    except Exception as e:
        stdout_str = proc.stdout if proc and proc.stdout else ""
        stderr_str = proc.stderr if proc and proc.stderr else ""
        return EvaluationResult(
            score=0.0,
            passed=False,
            feedback=f"Sandbox error: {type(e).__name__}: {e}",
            artifacts={"stdout": stdout_str, "stderr": stderr_str},
        )
    finally:
        if code_filename and os.path.exists(code_filename):
            try:
                os.unlink(code_filename)
            except OSError:
                pass


def _fallback_feedback(stdout: str, stderr: str) -> str:
    parts = []
    if stdout.strip():
        parts.append(f"stdout:\n{stdout.strip()[:500]}")
    if stderr.strip():
        parts.append(f"stderr:\n{stderr.strip()[:500]}")
    if not parts:
        return "No output from evaluator subprocess."
    return "Could not parse evaluation result.\n" + "\n".join(parts)
