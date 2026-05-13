"""Evaluation model, sandboxed execution, worker pool, caching, and static pre-filter."""

import ast
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Union


# ── Data Model ──────────────────────────────────────────────────────────────

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


# ── Static Analysis Pre-Filter ─────────────────────────────────────────────

def prefilter_code(code: str, expected_name: Optional[str] = None) -> Optional[EvaluationResult]:
    """Fast static checks before running in a subprocess.

    Returns an EvaluationResult with passed=False if the code is obviously broken,
    or None if it passes static checks.

    This runs in <5ms vs ~500ms for a subprocess spawn — huge win for bad code.
    """
    # 1. Syntax check
    try:
        compile(code, "<eval>", "exec")
    except SyntaxError as e:
        return EvaluationResult(
            score=0.0, passed=False,
            feedback=f"Syntax error: {e}",
            metrics={},
            artifacts={"static_error": f"SyntaxError: {e}"},
        )

    # 2. Structural check: does the code define what's expected?
    if expected_name:
        try:
            tree = ast.parse(code)
            defined = {
                node.name for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            }
            if expected_name not in defined:
                return EvaluationResult(
                    score=0.0, passed=False,
                    feedback=f"Static check: expected '{expected_name}' was not defined in generated code",
                    metrics={},
                    artifacts={"static_error": f"Missing definition: {expected_name}"},
                )
        except SyntaxError:
            pass  # already caught above

    return None


# ── Persistent Worker Pool ─────────────────────────────────────────────────

_WORKER_SCRIPT = r"""
import sys, json, os, signal

eval_dir = sys.argv[1]
sys.path.insert(0, eval_dir)
os.chdir(eval_dir)

from evaluate import evaluate

_current_id = None

def _alarm_handler(signum, frame):
    resp = {"id": _current_id, "error": "timeout"}
    print(json.dumps(resp), flush=True)

signal.signal(signal.SIGALRM, _alarm_handler)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    _current_id = req["id"]
    signal.alarm(req.get("timeout", 30))
    try:
        result = evaluate(req["code"])
        signal.alarm(0)
        resp = {"id": req["id"], "result": result}
    except Exception as e:
        signal.alarm(0)
        resp = {"id": req["id"], "error": "evaluate() raised: " + type(e).__name__ + ": " + str(e)}
    print(json.dumps(resp), flush=True)
    _current_id = None
"""


class _EvalWorker:
    """A persistent subprocess worker that evaluates code via stdin/stdout JSON protocol."""

    def __init__(self, eval_dir: str):
        self._eval_dir = eval_dir
        self._proc = subprocess.Popen(
            [sys.executable, "-c", _WORKER_SCRIPT, eval_dir],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
        self._next_id = 0

    def send(self, code: str, timeout: int) -> dict:
        """Send code to the worker and return the response dict."""
        req_id = self._next_id
        self._next_id += 1
        request = {"id": req_id, "code": code, "timeout": timeout}

        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("Worker process not ready")

        self._proc.stdin.write(json.dumps(request) + "\n")
        self._proc.stdin.flush()

        # Read exactly one response line
        line = self._proc.stdout.readline()
        if not line:
            # Worker died — try to get stderr for diagnostics
            stderr = ""
            if self._proc.stderr:
                stderr = self._proc.stderr.read()
            raise RuntimeError(f"Worker process died (stderr: {stderr[:500]})")

        return json.loads(line.strip())

    @property
    def is_alive(self) -> bool:
        return self._proc.poll() is None

    def kill(self):
        """Force-kill the worker process."""
        if self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(timeout=5)


class EvalWorkerPool:
    """Pool of persistent subprocess workers for evaluating generated code.

    Workers stay alive between evaluations, importing the evaluator module once.
    Provides built-in evaluation caching and static analysis pre-filter.
    """

    def __init__(self, eval_dir: str, max_workers: int = 1, cache_max: int = 100):
        self._eval_dir = eval_dir
        self._max_workers = max_workers
        self._workers: list[_EvalWorker] = []
        self._rr = 0
        self._cache: dict[str, EvaluationResult] = {}
        self._cache_max = cache_max
        self._cache_ordered: list[str] = []  # for LRU eviction

    # ── Public API ─────────────────────────────────────────────────

    def evaluate(self, code: str, timeout: int = 30,
                 expected_name: Optional[str] = None) -> EvaluationResult:
        """Evaluate code in the pool.

        Checks cache → static pre-filter → subprocess evaluation.
        Results are cached by code hash.
        """
        # 1. Cache hit?
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        if code_hash in self._cache:
            return self._cache[code_hash]

        # 2. Static analysis pre-filter
        prefilter_result = prefilter_code(code, expected_name)
        if prefilter_result is not None:
            self._cache_result(code_hash, prefilter_result)
            return prefilter_result

        # 3. Send to worker
        result = self._evaluate_on_worker(code, timeout)

        # 4. Cache the result
        self._cache_result(code_hash, result)
        return result

    def shutdown(self):
        """Kill all workers and clear cache."""
        for w in self._workers:
            try:
                w.kill()
            except Exception:
                pass
        self._workers.clear()
        self._cache.clear()
        self._cache_ordered.clear()

    # ── Internal ───────────────────────────────────────────────────

    def _evaluate_on_worker(self, code: str, timeout: int) -> EvaluationResult:
        worker = self._get_worker()
        try:
            response = worker.send(code, timeout)
        except (BrokenPipeError, RuntimeError) as e:
            # Worker died — remove it and retry
            self._workers = [w for w in self._workers if w is not worker]
            worker = self._get_worker()  # spawn a fresh one
            try:
                response = worker.send(code, timeout)
            except Exception as e2:
                return EvaluationResult(
                    score=0.0, passed=False,
                    feedback=f"Worker error after restart: {e2}",
                )

        if "error" in response:
            return EvaluationResult(
                score=0.0, passed=False,
                feedback=response["error"][:1000],
            )

        try:
            result_dict = response["result"]
            return EvaluationResult(**result_dict)
        except (KeyError, TypeError, ValueError) as e:
            return EvaluationResult(
                score=0.0, passed=False,
                feedback=f"Bad result from evaluator: {e}",
            )

    def _get_worker(self) -> _EvalWorker:
        # Find a living worker or spawn a new one
        for w in self._workers:
            if w.is_alive:
                return w

        if len(self._workers) < self._max_workers:
            w = _EvalWorker(self._eval_dir)
            self._workers.append(w)
            return w

        # All workers dead — replace the first one
        w = _EvalWorker(self._eval_dir)
        self._workers[0] = w
        return w

    def _cache_result(self, code_hash: str, result: EvaluationResult):
        if len(self._cache) >= self._cache_max:
            # LRU eviction
            oldest = self._cache_ordered.pop(0)
            self._cache.pop(oldest, None)
        self._cache[code_hash] = result
        self._cache_ordered.append(code_hash)


# ── Legacy API (backward compatible) ────────────────────────────────────────

def evaluate_in_sandbox(
    eval_module_path: Union[str, Path],
    code_str: str,
    timeout: int = 30,
) -> EvaluationResult:
    """Evaluate generated code by spawning a fresh subprocess.

    This is the legacy single-shot approach. For repeated evaluations
    (the common case in evolution), prefer using an EvalWorkerPool.
    """
    eval_path = Path(eval_module_path).resolve()
    eval_dir = eval_path.parent

    proc = None
    code_filename = None

    try:
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix="verigen_code_",
        )
        try:
            tmp_file.write(code_str)
            tmp_file.flush()
            code_filename = tmp_file.name
        finally:
            tmp_file.close()

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
            capture_output=True, text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        stdout_str = proc.stdout or ""
        stderr_str = proc.stderr or ""

        lines = stdout_str.splitlines()
        result_json = None
        for i, line in enumerate(lines):
            if line.strip() == "__VERIGEN_RESULT__":
                if i + 1 < len(lines):
                    result_json = lines[i + 1]
                break

        if result_json is None:
            return EvaluationResult(
                score=0.0, passed=False,
                feedback=_fallback_feedback(stdout_str, stderr_str),
                artifacts={"stdout": stdout_str, "stderr": stderr_str},
            )

        result_dict = json.loads(result_json)
        return EvaluationResult(**result_dict)

    except subprocess.TimeoutExpired:
        return EvaluationResult(
            score=0.0, passed=False,
            feedback=f"Evaluation timed out after {timeout}s.",
        )
    except json.JSONDecodeError as e:
        return EvaluationResult(
            score=0.0, passed=False,
            feedback=f"Failed to parse evaluation result: {e}",
            artifacts={"stdout": proc.stdout if proc else "", "stderr": proc.stderr if proc else ""},
        )
    except Exception as e:
        return EvaluationResult(
            score=0.0, passed=False,
            feedback=f"Sandbox error: {type(e).__name__}: {e}",
            artifacts={"stdout": proc.stdout if proc and proc.stdout else "", "stderr": proc.stderr if proc and proc.stderr else ""},
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
