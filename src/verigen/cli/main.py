"""CLI entry point for verigen."""

import json
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


@cli.command()
@click.argument("task_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--max-iterations", "-n", default=30, show_default=True, help="Maximum evolution iterations")
@click.option("--score-threshold", "-t", type=float, help="Early stop when score >= threshold")
@click.option("--model", help="DSPy LM model string, e.g. 'openai/gpt-4o' or 'ollama_chat/qwen3.6'")
@click.option("--api-base", help="API base URL for the model (e.g., http://localhost:8080/v1)")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output directory (default: task_dir/output/)")
@click.option("--timeout", default=30, show_default=True, help="Evaluation timeout in seconds")
def run(
    task_dir: str,
    max_iterations: int,
    score_threshold: Optional[float],
    model: Optional[str],
    api_base: Optional[str],
    output: Optional[str],
    timeout: int,
):
    """Run verifiable code generation on a task directory.

    TASK_DIR must contain initial.py (with EVOLVE-BLOCK markers) and evaluate.py.
    """
    # Configure DSPy LM
    _default_lm_kwargs = dict(max_tokens=8192)
    if model:
        lm_kwargs = {"model": model, **_default_lm_kwargs}
        if api_base:
            lm_kwargs["api_base"] = api_base
        if "ollama" in model or "localhost" in (api_base or ""):
            lm_kwargs.setdefault("api_key", "not-needed")
        dspy.configure(lm=dspy.LM(**lm_kwargs))
    elif api_base:
        dspy.configure(lm=dspy.LM(
            model="openai/qwen3.6",
            api_base=api_base,
            api_key="not-needed",
            **_default_lm_kwargs,
        ))
    else:
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
        except Exception:
            click.echo("No model configured. Use --model and/or --api-base, or configure dspy.settings.lm.", err=True)
            raise click.Abort()

    # Load task
    click.echo(f"Loading task from {task_dir}...")
    task = load_task(task_dir, timeout=timeout)
    click.echo(f"  Description: {task.description or '(none)'}")
    click.echo(f"  Template: {len(task.template)} chars")
    click.echo()

    # Run
    click.echo(f"Running evolution (max {max_iterations} iterations)...")
    gen = VerifiableCodeGen(
        max_iterations=max_iterations,
        score_threshold=score_threshold,
    )
    result = gen(task)

    # Report
    click.echo()
    click.echo(f"✓ Done after {result.n_iterations} iterations")
    click.echo(f"  Best score: {result.best_score:.4f}")
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
    summary = {
        "score": result.best_score,
        "n_iterations": result.n_iterations,
        "feedback": result.best_feedback,
        "metrics": result.best_metrics,
        "code_path": str(code_path),
        "trace_path": str(trace_path),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    click.echo(f"  Saved: {summary_path}")
    click.echo()

    # Print iteration summary
    click.echo("Iteration history:")
    for entry in result.trace.entries:
        badge = "✓" if entry.passed else "✗"
        click.echo(f"  [{entry.iteration:3d}] {entry.phase:7s} {badge} score={entry.score:.4f}  {entry.feedback[:80]}")
