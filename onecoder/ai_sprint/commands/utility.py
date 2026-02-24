import click
import json
import subprocess
import sys
import shutil
from .common import console, PROJECT_ROOT, SPRINT_DIR

@click.command()
@click.option("--limit", default=100, help="Number of commits to trace")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def trace(limit, json_output):
    """Visualize specification traceability across history."""
    from ..trace import trace_specifications

    trace_map = trace_specifications(PROJECT_ROOT, limit)

    if json_output:
        print(json.dumps(trace_map, indent=2))
        return

    from rich.tree import Tree
    from rich.panel import Panel

    root_tree = Tree("[bold cyan]OneCoder Traceability Map[/bold cyan]")

    for spec_id, data in trace_map.get("specs", {}).items():
        spec_node = root_tree.add(
            f"[bold yellow]Specification: {spec_id}[/bold yellow]"
        )
        for sprint_id in data.get("sprints", []):
            sprint_node = spec_node.add(f"[cyan]Sprint: {sprint_id}[/cyan]")
            sprint_data = trace_map.get("sprints", {}).get(sprint_id, {})
            for tid in data.get("tasks", []):
                if tid in sprint_data.get("tasks", {}):
                    task_node = sprint_node.add(f"[green]Task: {tid}[/green]")
                    for commit in sprint_data["tasks"][tid]:
                        if spec_id in commit.get("spec_ids", []):
                            task_node.add(
                                f"[dim]{commit['hash']}[/dim] {commit['message']}"
                            )

    console.print(Panel(root_tree, border_style="blue", expand=False))

@click.command()
def check_submodules():
    """Verify that all submodule commits are pushed to their remotes."""
    from ..submodule import get_unpushed_submodules

    unpushed = get_unpushed_submodules(PROJECT_ROOT)
    if unpushed:
        console.print(
            "[bold red]Error:[/bold red] Unpushed submodule commits detected."
        )
        sys.exit(1)
    console.print("[bold green]✓ Submodule integrity verified.[/bold green]")

@click.command()
def install_hooks():
    """Install Git hooks for Procedural Integrity enforcement and governance."""
    hooks_dir = PROJECT_ROOT / ".git" / "hooks"
    if not hooks_dir.parent.exists():
        console.print("[yellow]Not a git repository. Skipping hook installation.[/yellow]")
        return
        
    hooks_dir.mkdir(parents=True, exist_ok=True)

    sprint_bin = "onecoder"
    cmd_prefix = (
        f"uv run {sprint_bin}" if (PROJECT_ROOT / "uv.lock").exists() else sprint_bin
    )

    pre_commit_path = hooks_dir / "pre-commit"
    pre_commit_content = (
        "#!/bin/bash\n"
        f"{cmd_prefix} sprint check-submodules || exit 1\n"
    )
    pre_commit_path.write_text(pre_commit_content)
    pre_commit_path.chmod(0o755)

    console.print(
        "[bold green]✓ Installed Procedural Integrity enforcement hook.[/bold green]"
    )