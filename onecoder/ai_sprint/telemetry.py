import json
import os
import datetime
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, List


class FailureModeCapture:
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or self._find_project_root()
        self.telemetry_dir = self.repo_root / ".onecoder" / "telemetry"
        self.failure_log = self.telemetry_dir / "failures.jsonl"
        self._ensure_dir()

    def _find_project_root(self) -> Path:
        """Find the project root directory (containing .git)."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path.cwd()  # Fallback to current directory

    def _ensure_dir(self):
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_info(self) -> str:
        """Try to retrieve the current user's username or email."""
        try:
            # First check environment
            user = os.environ.get("USER") or os.environ.get("USERNAME")
            if user:
                return user

            # Then try to look for onecoder config (simplified)
            config_file = Path.home() / ".onecoder" / "config.json"
            if config_file.exists():
                with open(config_file, "r") as f:
                    config = json.load(f)
                    user_data = config.get("user", {})
                    return (
                        user_data.get("username") or user_data.get("email") or "unknown"
                    )
        except Exception:
            pass
        return "unknown"

    def capture(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Capture an error with full context and log it to JSONL."""
        now = datetime.datetime.now().isoformat()

        # Try to get user from onecoder config if available
        user_info = self._get_user_info()

        failure_data: Dict[str, Any] = {
            "timestamp": now,
            "error_type": type(error).__name__,
            "message": str(error),
            "stack_trace": traceback.format_exc(),
            "user": user_info,
            "context": context or {},
        }

        # Try to auto-detect sprint and task context if not provided
        if "sprint_id" not in failure_data["context"]:
            failure_data["context"]["sprint_id"] = os.environ.get("ACTIVE_SPRINT_ID")

        if "task_id" not in failure_data["context"]:
            # If we are in a sprint command, try to get task_id from args
            args = failure_data["context"].get("command_args", [])
            for i, arg in enumerate(args):
                if arg == "--task-id" and i + 1 < len(args):
                    failure_data["context"]["task_id"] = args[i + 1]
                    break

        try:
            with open(self.failure_log, "a") as f:
                f.write(json.dumps(failure_data) + "\n")
        except Exception as e:
            # Fallback to stderr if logging fails
            print(f"Failed to log failure mode: {e}")

    def get_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent failures."""
        if not self.failure_log.exists():
            return []

        failures = []
        try:
            with open(self.failure_log, "r") as f:
                for line in f:
                    if line.strip():
                        failures.append(json.loads(line))
        except Exception:
            pass

        return failures[-limit:]
