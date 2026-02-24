import re
from pathlib import Path
from typing import List


class GuidanceEngine:
    """Analyze project artifacts to provide context-aware guidance for agents."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.feedback_file = project_root / "FEEDBACK.md"
        self.sprint_guide = project_root / "SPRINT.md"

    def generate_guidance(self, sprint_dir: Path, sprint_name: str) -> Path:
        """Scan artifacts and generate media/agent_guidance.md."""
        todo_file = sprint_dir / "TODO.md"
        guidance_path = sprint_dir / "media" / "agent_guidance.md"

        guidance_content = [
            f"# Agent Guidance: Sprint {sprint_name}\n",
            "> [!NOTE]",
            "> This guidance is automatically generated based on historical friction points and current task context.\n",
        ]

        # 1. Scan FEEDBACK.md for recent friction
        friction_points = self._extract_friction_points()
        if friction_points:
            guidance_content.append("## ⚠️ Historical Friction Alerts\n")
            for point in friction_points:
                guidance_content.append("> [!IMPORTANT]")
                guidance_content.append(f"> {point}\n")

        # 2. Scan TODO.md for complex tasks
        complex_tasks = self._identify_complex_tasks(todo_file)
        if complex_tasks:
            guidance_content.append("## 💡 Implementation Tips\n")
            for task in complex_tasks:
                guidance_content.append("> [!TIP]")
                guidance_content.append(f"> **Task**: {task}")
                guidance_content.append(
                    "> Ensure you follow the specific tech-stack guidelines in `AGENTS.md` for this component.\n"
                )

        # 3. Add default safety reminders
        guidance_content.append("## 🛡️ Safety & Governance Reminders\n")
        guidance_content.append("> [!WARNING]")
        guidance_content.append(
            "> **Procedural Integrity**: Do not mark tasks as done without implementation commits."
        )
        guidance_content.append(
            "> **Atomic Commits**: Follow the 'One Task, One Commit' rule (SPEC-GOV-007).\n"
        )

        guidance_path.parent.mkdir(parents=True, exist_ok=True)
        guidance_path.write_text("\n".join(guidance_content))
        return guidance_path

    def _extract_friction_points(self) -> List[str]:
        """Simple heuristic to extract friction from FEEDBACK.md."""
        points = []
        if not self.feedback_file.exists():
            return points

        content = self.feedback_file.read_text()
        # Look for "Problem" or "Issue" or "Friction" sections in recent entries
        # For MVP, we take the last 3 suggested improvements
        matches = re.findall(r"\*\s*\*\*Problem\*\*:?\s*(.+)", content, re.I)
        if matches:
            points.extend(matches[-3:])

        # Also look for suggested improvements
        matches = re.findall(
            r"### Suggested Improvements\n\n1\.\s+\*\*([^*]+)\*\*", content
        )
        if matches:
            points.extend([f"Improvement: {m}" for m in matches[-2:]])

        return points

    def _identify_complex_tasks(self, todo_file: Path) -> List[str]:
        """Identify tasks that might need extra guidance."""
        tasks = []
        if not todo_file.exists():
            return tasks

        content = todo_file.read_text()
        # Tasks with many subtasks or "Implement" in title
        lines = content.split("\n")
        for line in lines:
            if re.match(
                r"-\s*\[\s\]\s*(.*(Implement|Refactor|Migrate|Auth).*)", line, re.I
            ):
                tasks.append(line.strip()[6:])

        return tasks[:3]  # Limit to top 3

    def generate_best_practices(self) -> str:
        """Generate a section of current agent best-practices."""
        return (
            "## 🧩 BEST PRACTICES (Refined Insights)\n"
            "> [!TIP]\n"
            "> **Native Verification (Touch Grass)**: When validating critical backend state (tiers, auth, database sync), "
            "always use direct scripts (e.g. `curl` or standalone `.py` scripts) to bypass local CLI overrides. "
            "The API is the source of truth.\n"
            "> [!IMPORTANT]\n"
            "> **Persistent Feedback Loop**: Immediately capture failure modes or governance friction into `.issues/`. "
            "Update `FEEDTRACKER.md` to share these insights across agent sessions.\n"
        )

    def generate_plan_prompt(self, context: str = "task") -> str:
        """Generate the detailed planning and workflow prompt."""
        prompt = [
            "ONECODER WORKFLOW & PLANNING:",
            "You are operating within the OneCoder framework. Before proceeding, you MUST plan your actions.",
            "",
            "1. **Review Workflow Commands**:",
        ]

        if context == "sprint":
            prompt.extend(
                [
                    "    -   `sprint init`: Initialize a new sprint (You are here).",
                    "    -   `sprint task start <task_id>`: Start working on a task.",
                    "    -   `sprint commit`: Commit changes.",
                    "    -   `sprint status`: Check sprint status.",
                ]
            )
        else:
            prompt.extend(
                [
                    "    -   `sprint task start <task>`: Start a task (You are here).",
                    "    -   `sprint task finish <task>`: Finish a task.",
                    "    -   `sprint commit`: Commit changes.",
                    "    -   `onecoder ...`: Run specific agentic tools if needed.",
                ]
            )

        prompt.extend(
            [
                "",
                "2. **Update TODO.md**:",
                "    -   Add a sub-task list for the current scope in `TODO.md`.",
                "    -   **Explicitly list the OneCoder/Shell commands you plan to execute.**",
                "    -   Example:",
                "        - [ ] Verify environment",
                "        - [ ] `run_tests.sh`",
                "        - [ ] Edit `src/main.py`",
                "        - [ ] `sprint finish`",
            ]
        )
        return "\n".join(prompt)

        return "\n".join(prompt)

    def generate_init_prompt(
        self, sprint_name: str, sprint_type: str = "feature"
    ) -> str:
        """Generate a governance prompt for sprint initialization."""
        prompt = [
            f"You are initializing a **{sprint_type}** sprint: '{sprint_name}'",
            "",
            "CORE GOVERNANCE RULES:",
            "1. **Context Capture**: Immediately capture artifacts (plan, task list) into `.sprint/{id}/context/`.",
            "2. **Clean Tree**: Ensure specific '.gitignore' rules are set if creating new temp files.",
            "3. **Plan First**: Do not write code until you have a detailed Implementation Plan artifact.",
            "",
            self.generate_best_practices(),
            "",
        ]
        if sprint_type == "shadow":
            prompt.append(
                "4. **Shadow Mode**: This is an ephemeral workspace. Do not push branches or create PRs unless promoted."
            )

        prompt.append("")
        prompt.append(self.generate_plan_prompt(context="sprint"))

        return "\n".join(prompt)

    def generate_start_prompt(self, task_name: str) -> str:
        """Generate a governance prompt for task start."""
        prompt = [
            f"You are starting task: '{task_name}'",
            "",
            "CRITICAL GOVERNANCE RULES:",
            "1. **Clean Tree**: You must have a clean git tree before and after this task.",
            "2. **Atomic Commits**: Run `sprint commit` immediately after `sprint finish`. One task = One commit.",
            "3. **Procedural Integrity**: Do not mark tasks done without valid implementation.",
            "4. **Traceability**: If this implements a SPEC, ensure you know the ID for the commit message.",
            "",
            self.generate_best_practices(),
            "",
        ]

        prompt.append("")
        prompt.append(self.generate_plan_prompt(context="task"))

        return "\n".join(prompt)
