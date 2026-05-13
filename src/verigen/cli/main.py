"""CLI entry point for verigen v0.3."""

import json
import math
from pathlib import Path
from typing import Optional

import click
import dspy

from verigen.core.module import VerifiableCodeGen
from verigen.task.loader import load_task


@click.group()
def cli():
    """verigen: DSPy-native verifiable code generation through evolutionary optimization."""
    pass


def _configure_lm(model: Optional[str], api_base: Optional[str]) -> bool:
    """Configure the DSPy LM. Returns True if successful."""
    import os as _os

    _default_lm_kwargs = dict(max_tokens=8192)

    if model:
        lm_kwargs = {"model": model, **_default_lm_kwargs}
        if api_base:
            lm_kwargs["api_base"] = api_base.rstrip("/")
        if "ollama" in model or "localhost" in (api_base or ""):
            lm_kwargs.setdefault("api_key", "not-needed")
        dspy.configure(lm=dspy.LM(**lm_kwargs))
        click.echo(f"✓ Using model: {model}")
        return True

    if api_base:
        dspy.configure(lm=dspy.LM(
            model="openai/qwen3.6",
            api_base=api_base.rstrip("/"),
            api_key="not-needed",
            **_default_lm_kwargs,
        ))
        click.echo(f"✓ Using API base: {api_base}")
        return True

    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8080/v1/models", timeout=2)
        dspy.configure(lm=dspy.LM(
            model="openai/qwen3.6",
            api_base="http://localhost:8080/v1",
            api_key="not-needed",
            **_default_lm_kwargs,
        ))
        click.echo("✓ Using local llama-server at http://localhost:8080/v1")
        return True
    except Exception:
        pass

    if _os.environ.get("OPENAI_API_KEY"):
        dspy.configure(lm=dspy.LM(model="openai/gpt-4o", **_default_lm_kwargs))
        click.echo("✓ Using OPENAI_API_KEY from environment")
        return True
    if _os.environ.get("ANTHROPIC_API_KEY"):
        dspy.configure(lm=dspy.LM(model="anthropic/claude-sonnet-4", **_default_lm_kwargs))
        click.echo("✓ Using ANTHROPIC_API_KEY from environment")
        return True
    if _os.environ.get("GOOGLE_API_KEY"):
        dspy.configure(lm=dspy.LM(model="google/gemini-3-pro", **_default_lm_kwargs))
        click.echo("✓ Using GOOGLE_API_KEY from environment")
        return True

    click.echo("No LLM configured. Options:", err=True)
    click.echo("  --model openai/gpt-4o --api-base https://api.openai.com/v1    (with env OPENAI_API_KEY)", err=True)
    click.echo("  --model ollama_chat/qwen3.6                                    (local Ollama)", err=True)
    click.echo("  --api-base http://localhost:8080/v1                             (local llama-server)", err=True)
    click.echo("  export OPENAI_API_KEY=... && verigen run <task>", err=True)
    return False


def _interpret_score(score: float) -> str:
    """Human-readable interpretation of a sigmoid-normalized score."""
    if score <= 0.0:
        return "implementation is broken or untested"
    # Convert score back to ratio: score = ratio / (1 + ratio) → ratio = score / (1 - score)
    ratio = score / (1.0 - score) if score < 1.0 else float("inf")
    if ratio >= 10:
        return f"~{ratio:.0f}× faster than reference — excellent"
    if ratio >= 3:
        return f"{ratio:.1f}× faster than reference — good"
    if ratio >= 1.5:
        return f"{ratio:.1f}× faster than reference — decent"
    if ratio >= 0.95:
        return f"{ratio:.2f}× relative to reference — on par"
    return f"{ratio:.2f}× relative to reference — room for improvement"


@cli.command()
@click.argument("task_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--max-iterations", "-n", default=30, show_default=True, help="Maximum evolution iterations")
@click.option("--score-threshold", "-t", type=float, help="Early stop when score >= threshold (e.g. 0.70 = ~2.3× reference)")
@click.option("--model", help="DSPy LM model string, e.g. 'openai/gpt-4o' or 'ollama_chat/qwen3.6'")
@click.option("--api-base", help="API base URL for the model (e.g., http://localhost:8080/v1)")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output directory (default: task_dir/output/)")
@click.option("--timeout", default=30, show_default=True, help="Evaluation timeout in seconds")
@click.option("--strategy", type=click.Choice(["greedy", "beam"]), default="greedy", show_default=True,
              help="Evolution strategy: greedy (single best) or beam (top-K candidates)")
@click.option("--beam-width", default=3, show_default=True, help="Number of candidates to keep in beam search")
@click.option("--mutation-mode", type=click.Choice(["full", "focused"]), default="full", show_default=True,
              help="Mutation scope: full (rewrite entire program) or focused (only EVOLVE-BLOCK region)")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Suppress live progress output")
def run(
    task_dir: str,
    max_iterations: int,
    score_threshold: Optional[float],
    model: Optional[str],
    api_base: Optional[str],
    output: Optional[str],
    timeout: int,
    strategy: str,
    beam_width: int,
    mutation_mode: str,
    quiet: bool,
):
    """Run verifiable code generation on a task directory.

    TASK_DIR must contain initial.py (with EVOLVE-BLOCK markers) and evaluate.py.
    """
    # Configure DSPy LM
    configured = _configure_lm(model, api_base)
    if not configured:
        raise click.Abort()

    # Load task
    click.echo(f"Loading task from {task_dir}...")
    task = load_task(task_dir, timeout=timeout)
    click.echo(f"  Description: {task.description or '(none)'}")
    click.echo(f"  Template: {len(task.template)} chars")
    if task.expected_name:
        click.echo(f"  Expected name: {task.expected_name}")
    click.echo()

    # Run evolution
    strategy_label = f"{strategy} (beam_width={beam_width})" if strategy == "beam" else strategy
    click.echo(f"Running evolution (max {max_iterations} iterations, strategy={strategy_label}, mutation={mutation_mode})...")
    if not quiet:
        click.echo()

    best_so_far = 0.0
    best_iter = 0

    def _on_iteration(iteration, phase, score, passed, elapsed_ms, is_best):
        nonlocal best_so_far, best_iter
        if quiet:
            return
        badge = "✓" if passed else "✗"
        is_new_best = "★" if is_best else " "
        if is_best:
            best_so_far = score
            best_iter = iteration
        click.echo(f"  [{iteration:3d}] {phase:7s} {badge} score={score:.4f}  {elapsed_ms:7.0f}ms  {is_new_best}")

    gen = VerifiableCodeGen(
        max_iterations=max_iterations,
        score_threshold=score_threshold,
        on_iteration=_on_iteration if not quiet else None,
        strategy=strategy,
        beam_width=beam_width,
        mutation_mode=mutation_mode,
    )
    result = gen(task)

    # Report
    click.echo()
    status_label = {
        "threshold_reached": "✓ Threshold reached",
        "completed": "✓ Completed all iterations",
        "plateau": "∼ Plateau (no improvement in recent iterations)",
        "initial_failed": "✗ Initial generation failed hard constraints",
    }.get(result.status, result.status)
    click.echo(f"  Status: {status_label}")
    click.echo(f"  Best score: {result.best_score:.4f} (at iteration {best_iter})")
    click.echo(f"  Interpretation: {_interpret_score(result.best_score)}")
    click.echo(f"  Best feedback: {result.best_feedback[:200]}")
    click.echo()

    # Determine output directory
    if output:
        out_dir = Path(output)
    else:
        out_dir = Path(task_dir) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save outputs
    code_path = out_dir / "best_program.py"
    code_path.write_text(result.best_code)
    click.echo(f"  Saved: {code_path}")

    trace_path = out_dir / "trace.jsonl"
    result.trace.save(trace_path)
    click.echo(f"  Saved: {trace_path}")

    # Summary
    ratio = result.best_score / (1.0 - result.best_score) if result.best_score < 1.0 else float("inf")
    summary = {
        "score": result.best_score,
        "speed_ratio": round(ratio, 4),
        "status": result.status,
        "strategy": strategy,
        "beam_width": beam_width if strategy == "beam" else None,
        "mutation_mode": mutation_mode,
        "n_iterations": result.n_iterations,
        "best_iteration": best_iter,
        "interpretation": _interpret_score(result.best_score),
        "feedback": result.best_feedback,
        "metrics": result.best_metrics,
        "code_path": str(code_path),
        "trace_path": str(trace_path),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    click.echo(f"  Saved: {summary_path}")
    click.echo()

    if result.status == "plateau":
        click.echo("  Tip: Score plateaued. Try:")
        click.echo("    1) Refine program.md with specific optimization hints")
        click.echo("    2) Use --strategy beam to explore multiple approaches")
        click.echo(f"    3) Increase --max-iterations (current: {max_iterations})")
    elif result.status == "initial_failed":
        click.echo("  Tip: The initial generation failed tests. Check the evaluator's test cases")
        click.echo("  and the LLM output in trace.jsonl. Tighten program.md instructions.")
    click.echo()

    # Print iteration summary in non-quiet mode
    if not quiet:
        click.echo("Iteration history:")
        for entry in result.trace.entries:
            badge = "✓" if entry.passed else "✗"
            ms = f"{entry.elapsed_ms:7.0f}ms" if entry.elapsed_ms else ""
            click.echo(f"  [{entry.iteration:3d}] {entry.phase:7s} {badge} score={entry.score:.4f}  {ms}  {entry.feedback[:60]}")
        click.echo()

    # Shutdown the evaluation pool
    if hasattr(task, '_pool') and task._pool:
        task._pool.shutdown()
