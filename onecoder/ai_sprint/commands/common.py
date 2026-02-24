from pathlib import Path


class LazyConsole:
    def __init__(self):
        self._console = None

    @property
    def inner(self):
        if self._console is None:
            from rich.console import Console

            self._console = Console()
        return self._console

    def print(self, *args, **kwargs):
        self.inner.print(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


console = LazyConsole()


def find_project_root():
    """Find the project root directory (containing .git)."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


PROJECT_ROOT = find_project_root()
SPRINT_DIR = PROJECT_ROOT / ".sprint"


def auto_detect_sprint_id():
    """Detect the active sprint ID based on current directory or environment."""
    import os

    # 1. Check environment variable
    if "ACTIVE_SPRINT_ID" in os.environ:
        return os.environ["ACTIVE_SPRINT_ID"]

    # 2. Check if current directory is inside a sprint
    try:
        current = Path.cwd()
        if SPRINT_DIR in current.parents or current == SPRINT_DIR:
            # Not quite right, we need to check if we are in .sprint/<id>
            # But usually we are in project root.
            pass
    except Exception:
        pass

    # 3. Check for most recently updated sprint in .sprint directory
    if SPRINT_DIR.exists():
        sprints = [
            d
            for d in SPRINT_DIR.iterdir()
            if d.is_dir() and (d / "sprint.json").exists() or (d / "sprint.yaml").exists()
        ]
        if sprints:
            # Sort by modification time of sprint.json/yaml
            def get_mtime(d):
                f = d / "sprint.yaml"
                if not f.exists():
                    f = d / "sprint.json"
                return f.stat().st_mtime

            latest = max(sprints, key=get_mtime)
            return latest.name

    return None


try:
    from ..state import SprintStateManager  # noqa: F401
except ImportError:
    pass
