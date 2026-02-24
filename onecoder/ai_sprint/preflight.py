import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from .state import SprintStateManager
from .checks import check_spec_alignment, check_secrets
import json

try:
    from onecore import GovernanceEngine  # type: ignore
except ImportError:
    GovernanceEngine = None


class SprintPreflight:
    def __init__(self, sprint_dir: Path, repo_root: Path):
        self.sprint_dir = sprint_dir
        self.repo_root = repo_root
        self.state_manager = SprintStateManager(sprint_dir)
        self.results: List[Dict[str, Any]] = []
        self.engine = None
        if GovernanceEngine:
            try:
                self.engine = GovernanceEngine(str(repo_root))
            except Exception:
                pass

    def run_all(
        self, staged: bool = False, files: Optional[List[str]] = None
    ) -> Tuple[int, List[Dict[str, Any]]]:
        self.results = []
        self.staged_mode = staged
        self.target_files = [Path(f) for f in files] if files else None

        # Initialize scan data via Rust Engine if available and not in staged mode (full scan)
        self.scan_data = None
        if self.engine and not staged and not files:
            try:
                self.scan_data = json.loads(self.engine.scan())
            except Exception:
                pass

        # 1. Task Breakdown Check
        self.results.append(self.check_task_breakdown())

        # 2. Documentation Check
        self.results.append(self.check_documentation())

        # 3. Spec Tracing Check
        self.results.append(self.check_spec_tracing())

        # 4. Component Scope Check
        self.results.append(self.check_component_scope())

        # 5. Governance Check
        self.results.append(self.check_governance())

        # 6. Retro Sync Check
        self.results.append(self.check_retro_sync())

        # 7. LOC Limit Check (New Zero Debt Policy)
        self.results.append(self.check_loc_limit())

        # 8. Secret Scanning (New Zero Debt Policy)
        self.results.append(self.check_secrets())

        # 9. Illegal Files Check (Zero Leakage Policy)
        self.results.append(self.check_illegal_files())

        # 10. Spec-Code Alignment Check (Ghost Map)
        self.results.append(
            check_spec_alignment(self.repo_root, getattr(self, "staged_mode", False))
        )

        # Calculate score
        valid_results = [
            r for r in self.results if isinstance(r, dict) and r.get("status")
        ]
        passed_count = sum(1 for r in valid_results if r["status"] == "passed")
        total_count = len(valid_results)
        score = int((passed_count / total_count) * 100) if total_count > 0 else 0

        return score, self.results

    def _get_project_files(self) -> List[Path]:
        """Get all tracked and untracked (non-ignored) files in the repo."""
        if self.target_files:
            return [
                self.repo_root / f
                for f in self.target_files
                if (self.repo_root / f).exists()
            ]

        # Use Rust engine results if available
        if getattr(self, "scan_data", None) and self.scan_data:
            return [self.repo_root / f for f in self.scan_data["file_list"]]

        try:
            cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
            if getattr(self, "staged_mode", False):
                cmd = ["git", "diff", "--cached", "--name-only"]

            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            files = []
            ignore_dirs = {
                ".git",
                "node_modules",
                "__pycache__",
                ".venv",
                ".sprint",
                ".vitepress",
                ".wrangler",
                "dist",
                ".adk",
                "archive",
            }
            for f in result.stdout.split("\n"):
                if not f.strip():
                    continue
                p = self.repo_root / f.strip()
                if not any(part in p.parts for part in ignore_dirs):
                    files.append(p)
            return files
        except Exception:
            # Fallback to rglob if git fails, but honor some defaults
            ignore_dirs = {
                ".git",
                "node_modules",
                "__pycache__",
                ".venv",
                ".sprint",
                ".vitepress",
                ".wrangler",
                "dist",
                "archive",
            }
            all_files = []

            for p in self.repo_root.rglob("*"):
                if p.is_file() and not any(part in p.parts for part in ignore_dirs):
                    all_files.append(p)
            return all_files

    def check_task_breakdown(self) -> Dict[str, Any]:
        # Ensure latest sync
        self.state_manager.sync_from_files()
        state = self.state_manager.load()
        tasks = state.get("tasks", [])
        if len(tasks) < 5:
            return {
                "name": "Task Breakdown",
                "status": "failed",
                "message": f"Sprint has only {len(tasks)} tasks (minimum 5 required).",
                "critical": True,
            }
        return {
            "name": "Task Breakdown",
            "status": "passed",
            "message": f"Sprint has {len(tasks)} tasks.",
        }

    def check_documentation(self) -> Dict[str, Any]:
        readme_file = self.sprint_dir / "README.md"
        todo_file = self.sprint_dir / "TODO.md"

        errors = []
        if not readme_file.exists() or readme_file.stat().st_size < 20:
            errors.append("README.md is missing or empty.")
        if not todo_file.exists() or todo_file.stat().st_size < 20:
            errors.append("TODO.md is missing or empty.")

        if errors:
            return {
                "name": "Documentation",
                "status": "failed",
                "message": " ".join(errors),
                "critical": True,
            }
        return {
            "name": "Documentation",
            "status": "passed",
            "message": "README.md and TODO.md are present.",
        }

    def check_spec_tracing(self) -> Dict[str, Any]:
        # Check if Spec-Id is present in README or TODO
        readme_content = ""
        todo_content = ""

        if (self.sprint_dir / "README.md").exists():
            readme_content = (self.sprint_dir / "README.md").read_text()
        if (self.sprint_dir / "TODO.md").exists():
            todo_content = (self.sprint_dir / "TODO.md").read_text()

        combined = readme_content + todo_content
        if "Spec-Id" not in combined and not re.search(r"SPEC-[A-Z]+-\d+", combined):
            return {
                "name": "Spec Tracing",
                "status": "failed",
                "message": "No Spec-Id found in sprint documentation.",
                "critical": True,
            }
        return {
            "name": "Spec Tracing",
            "status": "passed",
            "message": "Spec tracking markers found.",
        }

    def check_component_scope(self) -> Dict[str, Any]:
        component = self.state_manager.get_component()
        if not component:
            return {
                "name": "Component Scope",
                "status": "failed",
                "message": "No component scope defined in sprint.json.",
                "critical": True,
            }
        return {
            "name": "Component Scope",
            "status": "passed",
            "message": f"Component scope: {component}",
        }

    def check_governance(self) -> Dict[str, Any]:
        # Clean git state check (no staged changes outside sprint artifacts)
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            staged_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]

            sprint_rel_path = str(self.sprint_dir.relative_to(self.repo_root))

            illegal_staged = [
                f
                for f in staged_files
                if not (
                    f.startswith(sprint_rel_path)
                    or f
                    in [
                        "TODO.md",
                        "RETRO.md",
                        "README.md",
                        "sprint.json",
                        "sprint.yaml",
                    ]
                )
            ]

            if (
                illegal_staged
                and not getattr(self, "staged_mode", False)
                and not getattr(self, "target_files", None)
            ):
                return {
                    "name": "Governance (Git State)",
                    "status": "failed",
                    "message": f"Illegal staged changes found: {', '.join(illegal_staged[:3])}...",
                    "critical": True,
                }
        except Exception as e:
            return {
                "name": "Governance (Git State)",
                "status": "warning",
                "message": f"Could not check git state: {e}",
            }

        return {
            "name": "Governance (Git State)",
            "status": "passed",
            "message": "Git state is clean.",
        }

    def check_retro_sync(self) -> Dict[str, Any]:
        """Check if RETRO.md content matches sprint.json data."""
        state = self.state_manager.load()
        if not state:
            return {
                "name": "Retro Sync",
                "status": "warning",
                "message": "Could not load sprint state.",
            }

        # If RETRO.md exists, ensure it's parsed
        if (self.sprint_dir / "RETRO.md").exists():
            retro = state.get("retro", {})
            if not retro.get("summary") and not retro.get("actionItems"):
                return {
                    "name": "Retro Sync",
                    "status": "warning",
                    "message": "RETRO.md exists but no summary/actions parsed in sprint.json. Check RETRO.md format.",
                }
            return {
                "name": "Retro Sync",
                "status": "passed",
                "message": "RETRO.md content synced to sprint.json.",
            }
        return {
            "name": "Retro Sync",
            "status": "passed",
            "message": "RETRO.md does not exist (optional).",
        }

    def check_loc_limit(self) -> Dict[str, Any]:
        """Check if any files exceed the 400 LOC limit (with No-Regression policy)."""
        violations = []
        project_files = self._get_project_files()

        for p in project_files:
            if ".sprint" in p.parts:
                continue
            if any(
                part in p.parts
                for part in {".wrangler", "dist", "build", "node_modules", ".venv"}
            ):
                continue

            if p.suffix in {".py", ".ts", ".js", ".tsx", ".jsx"}:
                try:
                    with open(p, "r", errors="ignore") as f:
                        lines = sum(1 for _ in f)

                    if lines > 400:
                        # No-Regression Check: Compare with HEAD version
                        try:
                            rel_path = str(p.relative_to(self.repo_root))
                            head_content = subprocess.run(
                                ["git", "show", f"HEAD:{rel_path}"],
                                cwd=self.repo_root,
                                capture_output=True,
                                text=True,
                                check=False,
                            )
                            if head_content.returncode == 0:
                                head_lines = len(head_content.stdout.splitlines())
                                if lines <= head_lines:
                                    # File is large but not growing, allow it
                                    continue
                        except Exception:
                            pass

                        violations.append(
                            f"{p.relative_to(self.repo_root)} ({lines} lines)"
                        )
                except Exception:
                    pass

        if violations:
            return {
                "name": "LOC Limit Enforcement",
                "status": "failed",
                "message": f"Found {len(violations)} files exceeding 400 LOC or increasing in size: {', '.join(violations[:2])}...",
                "critical": False,
            }
        return {
            "name": "LOC Limit Enforcement",
            "status": "passed",
            "message": "All modified files are under 400 LOC or passing no-regression policy.",
        }

    def check_secrets(self) -> Dict[str, Any]:
        """Basic secret scanning with placeholder avoidance."""
        return check_secrets(self.repo_root, getattr(self, "scan_data", None))

    def check_illegal_files(self) -> Dict[str, Any]:
        """Check for strictly prohibited files like .env or build artifacts."""
        violations = []
        project_files = self._get_project_files()

        # Paths that are strictly forbidden
        illegal_patterns = [
            r"\.env$",
            r"\.vitepress/(dist|cache)",
            r"secrets\.txt$",
            r"mlruns/",
        ]

        for p in project_files:
            rel_path = str(p.relative_to(self.repo_root))
            for pattern in illegal_patterns:
                if re.search(pattern, rel_path):
                    violations.append(rel_path)
                    break

        if violations:
            return {
                "name": "Zero Leakage Enforcement",
                "status": "failed",
                "message": f"Found prohibited files: {', '.join(violations[:3])}",
                "critical": True,
            }
        return {
            "name": "Zero Leakage Enforcement",
            "status": "passed",
            "message": "No prohibited files detected.",
        }
