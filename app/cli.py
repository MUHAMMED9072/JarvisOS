from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.markdown import Markdown

from app.autonomy.build_orchestrator import BuildOrchestrator, Stage


STAGE_ICONS = {
    Stage.INTERPRET: "🔍",
    Stage.CONTEXT: "📚",
    Stage.PLAN: "📋",
    Stage.AGENT_SELECT: "🤖",
    Stage.TOOL_SELECT: "🔧",
    Stage.ADS_GENERATE: "⚙️",
    Stage.SANDBOX: "🧪",
    Stage.TEST: "✅",
    Stage.SIMULATE: "🔮",
    Stage.GOVERN: "🛡️",
    Stage.GIT_COMMIT: "📦",
    Stage.REPORT: "📊",
}

console = Console()


def run_build(orchestrator: BuildOrchestrator, request: str) -> None:
    console.print()
    console.print(Panel(f"[bold cyan]{request}[/bold cyan]", title="Jarvis Build"))
    console.print()

    start = time.time()
    result = orchestrator.build(request)
    duration = time.time() - start

    table = Table(title="Build Pipeline Stages")
    table.add_column("Stage", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Time", style="dim")
    table.add_column("Details")

    for stage_name, stage_result in sorted(
        result.stages.items(),
        key=lambda x: list(Stage.__members__.values()).index(
            next(s for s in Stage if s.value == x[0])
        ) if any(s.value == x[0] for s in Stage) else 0,
    ):
        icon = ""
        for s in Stage:
            if s.value == stage_name:
                icon = STAGE_ICONS.get(s, "")
                break
        name = f"{icon} {stage_name.replace('_', ' ').title()}"

        if stage_result.status == "passed":
            status = "[green]PASSED[/green]"
        elif stage_result.status == "failed":
            status = "[red]FAILED[/red]"
        else:
            status = f"[yellow]{stage_result.status.upper()}[/yellow]"

        time_str = f"{stage_result.duration_ms:.0f}ms"
        detail = stage_result.error if stage_result.error else ""

        table.add_row(name, status, time_str, detail)

    console.print(table)
    console.print()

    if result.status.name == "COMPLETED":
        msg = (
            f"[green]Build completed successfully in {duration:.1f}s[/green]\n"
            f"{result.summary}"
        )
        if result.commit_hash:
            msg += f"\nCommit: [dim]{result.commit_hash}[/dim]"
        console.print(Panel(msg, title="Result", border_style="green"))
    else:
        console.print(Panel(
            f"[red]Build failed: {result.error}[/red]",
            title="Result",
            border_style="red",
        ))


def run_interactive(orchestrator: BuildOrchestrator) -> None:
    console.print(Panel(
        "[bold cyan]JARVIS OS[/bold cyan] — AI Software Engineer\n"
        "Type [dim]exit[/dim] to quit.",
        title="Interactive Mode",
    ))
    while True:
        try:
            req = console.input("\n[bold cyan]> [/bold cyan]")
            if req.lower() in ("exit", "quit", "q"):
                break
            if not req.strip():
                continue
            run_build(orchestrator, req.strip())
        except KeyboardInterrupt:
            break
        except EOFError:
            break
    console.print("\n[dim]Goodbye.[/dim]")


def run_status(orchestrator: BuildOrchestrator) -> None:
    stats = orchestrator.get_statistics()
    table = Table(title="Build Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")
    for k, v in stats.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="JARVIS OS — AI Software Engineer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m app.cli build \"Create a REST API client\"\n"
            "  python -m app.cli interactive\n"
            "  python -m app.cli status\n"
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="interactive",
        choices=["build", "interactive", "status"],
        help="Command to run (default: interactive)",
    )
    parser.add_argument(
        "request",
        nargs="*",
        help="Build request (for 'build' command)",
    )

    args = parser.parse_args()

    orchestrator = BuildOrchestrator()

    if args.command == "build":
        request = " ".join(args.request) if args.request else ""
        if not request:
            console.print("[red]Error: build requires a request[/red]")
            sys.exit(1)
        run_build(orchestrator, request)

    elif args.command == "interactive":
        run_interactive(orchestrator)

    elif args.command == "status":
        run_status(orchestrator)


if __name__ == "__main__":
    main()
