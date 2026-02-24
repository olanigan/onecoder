import click
import subprocess
import sys
import time
import json
from pathlib import Path


def find_repo_root() -> Path:
    """Find the project root directory (containing .git)."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


@click.group(name="agent")
def agent():
    """Universal Agent Orchestration."""
    pass


@agent.command()
@click.option(
    "--cmd",
    required=True,
    help="The external agent command to run (e.g. 'claude code')",
)
@click.option("--task-id", help="The task ID to associate this session with.")
def start(cmd, task_id):
    """Starts an external agent session and orchestrates the process."""
    repo_root = find_repo_root()
    sprint_base = repo_root / ".sprint"

    # Attempt to find an active sprint if not provided
    active_sprint = None
    if sprint_base.exists():
        sprints = [d for d in sprint_base.iterdir() if d.is_dir()]
        if sprints:
            active_sprint = sorted(sprints)[-1]

    click.secho("[*] Launching Universal Orchestrator", fg="cyan", bold=True)
    click.secho(f"[*] Command: {cmd}", fg="dim")

    if active_sprint:
        click.secho(f"[*] Sprint: {active_sprint.name}", fg="dim")
        session_log_dir = active_sprint / "sessions"
        session_log_dir.mkdir(parents=True, exist_ok=True)
        session_id = f"session_{int(time.time())}"
        log_file = session_log_dir / f"{session_id}.log"
    else:
        click.secho(
            "[!] No active sprint detected. Session logs will be transient.",
            fg="yellow",
        )
        log_file = None

    start_time = time.time()

    try:
        # We use a context manager or direct subprocess to stream output
        # For a truly universal wrapper, we want to behave like a pty if possible,
        # but for a basic OSS version, we'll start with a standard subprocess.
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
            stdin=sys.stdin,
            text=True,
        )

        # Wait for the process to finish
        process.wait()
        exit_code = process.returncode

    except Exception as e:
        click.secho(f"[-] Execution failed: {e}", fg="red")
        exit_code = 1

    end_time = time.time()
    duration = end_time - start_time

    if log_file:
        session_meta = {
            "session_id": session_id,
            "command": cmd,
            "task_id": task_id,
            "start_time": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(start_time)
            ),
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time)),
            "duration_seconds": duration,
            "exit_code": exit_code,
        }
        with open(log_file.with_suffix(".json"), "w") as f:
            json.dump(session_meta, f, indent=4)

    if exit_code == 0:
        click.secho(
            f"\n[+] Agent session complete (Duration: {duration:.1f}s)",
            fg="green",
            bold=True,
        )
    else:
        click.secho(
            f"\n[!] Agent session exited with code {exit_code}", fg="yellow", bold=True
        )

    # Pro Funnel
    if log_file:
        click.echo(
            f"[*] Session artifacts saved to: {log_file.parent.relative_to(repo_root)}"
        )

    click.echo("\n---")
    click.echo(
        "💡 [TIP] Need verified landings? Use 'fullcoder agent' for Governance-Verified check-ins."
    )
