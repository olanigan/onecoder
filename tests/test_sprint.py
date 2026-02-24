import os
from pathlib import Path
from click.testing import CliRunner
from onecoder.cli import cli
import pytest
from unittest.mock import patch
import subprocess

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def temp_repo(tmp_path):
    # Initialize a dummy git repo
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    os.chdir(repo_dir)
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

def test_task_finish_auto_detect_task_non_interactive(runner, temp_repo):
    with patch.dict(os.environ, {"ONECODER_SKIP_PREFLIGHT": "true"}):
        # Setup sprint and task
        runner.invoke(cli, ["sprint", "init", "auto-detect", "-y", "--no-branch"])
        sprint_dir = temp_repo / ".sprint" / "001-auto-detect"
        
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

        # Start task - this sets it to in-progress
        runner.invoke(cli, ["sprint", "start", "task-001", "--type", "implementation"])
        
        # Create a file
        (temp_repo / "data.txt").write_text("data")

        # Finish task without task_name or validation - should auto-detect and use defaults
        result = runner.invoke(cli, ["sprint", "finish", "-y", "-m", "feat: auto finish"])
        
        if result.exit_code != 0:
            print(result.output)
            
        assert result.exit_code == 0
        assert "Finishing task: task-001" in result.output
        assert "Task marked as done" in result.output
        assert "Success: Commit created." in result.output
