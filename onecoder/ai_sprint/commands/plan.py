import click
from rich.panel import Panel
from .common import console, PROJECT_ROOT, auto_detect_sprint_id
from onecoder.alignment import AlignmentEngine


@click.command()
@click.option(
    "--context",
    type=click.Choice(["sprint", "task"]),
    default="task",
    help="Context for the plan (sprint init or task start)",
)
def plan(context):
    """Display the OneCoder planning guidance and workflow commands."""
    engine = AlignmentEngine(PROJECT_ROOT)

    sprint_id = auto_detect_sprint_id() or "unknown"
    prompt = engine.generate_unified_plan(sprint_id, context)

    console.print(
        Panel(
            prompt,
            title="[bold blue]ONECODER UNIFIED PLAN[/bold blue]",
            border_style="blue",
        )
    )
