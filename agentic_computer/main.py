"""CLI entry point for agentic-computer.

Provides commands for running the agent interactively,
starting the API server, and managing workflows.
"""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agentic_computer import __version__
from agentic_computer.config import get_settings

console = Console()

BANNER = r"""
   ___                    __  _         ______                          __
  / _ | ___ ____ ___  / /_(_)___   / ____/___  __ _  ___  __ __/ /____ ____
 / __ |/ _ `/ -_) _ \/ __/ / __/  / /   / _ \/  ' \/ _ \/ // / __/ -_) __/
/_/ |_|\_,_/\__/_//_/\__/_/\__/  /_/    \___/_/_/_/ .__/\_,_/\__/\__/_/
                                                  /_/
"""


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """agentic-computer — Autonomous computer agent."""
    pass


@cli.command()
@click.option("--task", "-t", help="Task to execute (non-interactive mode).")
@click.option("--model", "-m", help="Override LLM model.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
def run(task: str | None, model: str | None, verbose: bool) -> None:
    """Run the agent interactively or execute a single task."""
    settings = get_settings()
    if model:
        settings.llm.model = model
    if verbose:
        settings.log_level = "DEBUG"

    console.print(Panel(Text(BANNER, style="bold cyan"), title="agentic-computer", subtitle=f"v{__version__}"))

    if task:
        console.print(f"[bold green]Executing task:[/bold green] {task}\n")
        asyncio.run(_run_task(task, settings))
    else:
        console.print("[bold yellow]Interactive mode[/bold yellow] — type your task or 'quit' to exit.\n")
        asyncio.run(_interactive_loop(settings))


async def _run_task(task: str, settings: object) -> None:
    """Execute a single task through the orchestrator."""
    from agentic_computer.core.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    result = await orchestrator.run(task)
    console.print(Panel(str(result), title="Result", border_style="green"))


async def _interactive_loop(settings: object) -> None:
    """Run an interactive REPL for the agent."""
    from agentic_computer.core.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    while True:
        try:
            task = console.input("[bold blue]> [/bold blue]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break
        if task.strip().lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break
        if not task.strip():
            continue
        try:
            result = await orchestrator.run(task)
            console.print(Panel(str(result), title="Result", border_style="green"))
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")


@cli.command()
@click.option("--host", default=None, help="Server host.")
@click.option("--port", "-p", default=None, type=int, help="Server port.")
def serve(host: str | None, port: int | None) -> None:
    """Start the FastAPI server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "agentic_computer.server.app:app",
        host=host or settings.server.host,
        port=port or settings.server.port,
        reload=settings.server.reload,
    )


@cli.command()
@click.argument("workflow_path")
@click.option("--input", "-i", "input_data", help="JSON input data for the workflow.")
def workflow(workflow_path: str, input_data: str | None) -> None:
    """Execute a YAML workflow file."""
    import json
    from pathlib import Path

    from agentic_computer.workflows.engine import WorkflowEngine

    engine = WorkflowEngine()
    wf_path = Path(workflow_path)
    if not wf_path.exists():
        console.print(f"[bold red]Workflow file not found:[/bold red] {workflow_path}")
        sys.exit(1)

    data = json.loads(input_data) if input_data else {}
    result = asyncio.run(engine.execute_file(wf_path, data))
    console.print(Panel(str(result), title="Workflow Result", border_style="green"))


if __name__ == "__main__":
    cli()
