import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@click.command()
def guide():
    """Getting Started & Best Practices Guide."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Welcome to OneCoder![/bold cyan]\n"
            "Local-first sprint management for coding agents.",
            title="OneCoder Guide",
            border_style="blue",
        )
    )

    workflow_table = Table(
        title="Common Workflows", show_header=True, header_style="bold magenta"
    )
    workflow_table.add_column("Goal", style="dim", width=30)
    workflow_table.add_column("Command(s)", style="yellow")

    workflow_table.add_row("Start a new sprint", "onecoder sprint init <name>")
    workflow_table.add_row("Work on a task", "onecoder sprint task start <id>")
    workflow_table.add_row(
        "Commit with governance",
        "onecoder sprint commit -m 'message' --spec-id SPEC-123",
    )
    workflow_table.add_row("Check sprint health", "onecoder sprint preflight")
    workflow_table.add_row("View all sprints", "onecoder sprint status")
    workflow_table.add_row("Close a sprint", "onecoder sprint close <name>")

    console.print(workflow_table)

    console.print("\n[bold green]Best Practices[/bold green]")
    console.print(
        "  • [cyan]Plan First[/cyan]: Always have an implementation plan before writing code."
    )
    console.print(
        "  • [cyan]Atomic Commits[/cyan]: One task = One commit. Use 'sprint commit' for governance metadata."
    )
    console.print(
        "  • [cyan]Frictionless Commits[/cyan]: Pass files directly as arguments to avoid prompts:"
    )
    console.print(
        "      [dim]onecoder sprint commit -m 'feat: ...' file1 file2 --spec-id SPEC-XXX[/dim]"
    )
    console.print(
        "  • [cyan]Telemetry[/cyan]: Failure modes are captured automatically. Check '.issues/' for history."
    )


if __name__ == "__main__":
    guide()
