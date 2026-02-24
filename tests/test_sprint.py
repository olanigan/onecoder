import os
from pathlib import Path
from click.testing import CliRunner
from onecoder.cli import cli
import pytest
from unittest.mock import patch

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def temp_repo(tmp_path):
    # Initialize a dummy git repo
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    os.chdir(repo_dir)
    import subprocess
    subprocess.run(["git", "init"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    
    # Mock PROJECT_ROOT and SPRINT_DIR in places they are used
    with patch("onecoder.ai_sprint.commands.common.PROJECT_ROOT", repo_dir), \
         patch("onecoder.ai_sprint.commands.common.SPRINT_DIR", repo_dir / ".sprint"), \
         patch("onecoder.ai_sprint.commands.sprint.PROJECT_ROOT", repo_dir), \
         patch("onecoder.ai_sprint.commands.sprint.SPRINT_DIR", repo_dir / ".sprint"), \
         patch("onecoder.ai_sprint.commands.task.PROJECT_ROOT", repo_dir), \
         patch("onecoder.ai_sprint.commands.task.SPRINT_DIR", repo_dir / ".sprint"), \
         patch("onecoder.ai_sprint.commands.governance.preflight.PROJECT_ROOT", repo_dir), \
         patch("onecoder.ai_sprint.commands.governance.preflight.SPRINT_DIR", repo_dir / ".sprint"), \
         patch("onecoder.ai_sprint.commands.governance.commit.PROJECT_ROOT", repo_dir):
        yield repo_dir

def test_sprint_init(runner, temp_repo):
    result = runner.invoke(cli, ["sprint", "init", "test-sprint", "-y", "--no-branch"])
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "Initialized sprint at" in result.output
    
    sprint_dir = temp_repo / ".sprint" / "001-test-sprint"
    assert sprint_dir.exists()
    assert (sprint_dir / "sprint.yaml").exists()
    assert (sprint_dir / "TODO.md").exists()

def test_sprint_status(runner, temp_repo):
    runner.invoke(cli, ["sprint", "init", "s1", "-y", "--no-branch"])
    result = runner.invoke(cli, ["sprint", "status"])
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "s1" in result.output

def test_task_lifecycle(runner, temp_repo):
    # Init sprint
    runner.invoke(cli, ["sprint", "init", "life", "-y", "--no-branch"])
    sprint_dir = temp_repo / ".sprint" / "001-life"
    
    # Let's use the actual state manager to add a task to ensure sync_engine works
    from onecoder.ai_sprint.state import SprintStateManager
    sm = SprintStateManager(sprint_dir)
    state = sm.load()
    state["tasks"].append({
        "id": "task-001",
        "title": "Task 1",
        "status": "todo"
    })
    sm.save(state)
    sm.sync_todo_from_state()

    # Start task
    result = runner.invoke(cli, ["sprint", "start", "task-001", "--type", "implementation"])
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "Starting task: task-001" in result.output
    
    # Create a file to stage so commit works
    work_file = temp_repo / "work.txt"
    work_file.write_text("done")

    # Finish task
    # Provide 'y' for the staging prompt
    result = runner.invoke(cli, ["sprint", "finish", "task-001", "-v", "proof", "-y"], input="y\n")
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "Task marked as done" in result.output