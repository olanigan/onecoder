"""Unit and integration tests for OneCoder tracking (local SQLite, remote client, CLI, and MCP)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BIN = str(ROOT / "bin" / "onecoder")

from onecoder.track.local import LocalTrackStore
from onecoder.track.remote import RemoteTrackClient, RemoteTrackError
from onecoder.track.store import get_track_store
from onecoder.track.workstation import get_workstation_id, slugify


def sh(cwd, *args, env=None):
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=merged_env)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


class TestWorkstationHelpers(unittest.TestCase):
    def test_get_workstation_id(self):
        ws = get_workstation_id()
        self.assertTrue(bool(ws))
        self.assertIsInstance(ws, str)

    def test_slugify(self):
        self.assertEqual(slugify("Implement Feature #123!"), "implement-feature-123")
        self.assertEqual(slugify("   Spaces   and --- dashes "), "spaces-and-dashes")
        self.assertEqual(slugify(""), "task")


class TestLocalTrackStore(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.db_path = self.root / "track.db"
        self.store = LocalTrackStore(db_path=self.db_path, root=self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_project_crud(self):
        p = self.store.update_project("test-proj", name="Test Project", category="devtools", tags=["cli", "python"])
        self.assertEqual(p["id"], "test-proj")
        self.assertEqual(p["name"], "Test Project")
        self.assertIn("cli", p["tags"])

        plist = self.store.list_projects(category="devtools")
        self.assertEqual(len(plist["projects"]), 1)
        self.assertEqual(plist["projects"][0]["id"], "test-proj")

        reg = self.store.register_project_path("test-proj", path=str(self.root / "sub"), repo_url="https://github.com/test/test.git")
        self.assertTrue(reg["registered"])

        loc = self.store.get_project_location("test-proj")
        self.assertEqual(loc["project"], "test-proj")
        self.assertEqual(loc["repo_url"], "https://github.com/test/test.git")

    def test_sprint_crud(self):
        sp = self.store.create_sprint("test-proj", "Sprint 01", status="active")
        self.assertEqual(sp["name"], "Sprint 01")
        self.assertEqual(sp["status"], "active")

        sps = self.store.list_sprints("test-proj")
        self.assertEqual(len(sps["sprints"]), 1)

        up = self.store.update_sprint(sp["id"], status="completed")
        self.assertEqual(up["status"], "completed")

    def test_issue_crud(self):
        sp = self.store.create_sprint("test-proj", "Sprint 01")
        iss = self.store.create_issue("test-proj", "Fix memory leak", sprint=sp["id"], labels=["bug", "core"])
        self.assertEqual(iss["title"], "Fix memory leak")
        self.assertEqual(iss["sprint"], sp["id"])
        self.assertIn("bug", iss["labels"])

        ilist = self.store.list_issues(project="test-proj", sprint=sp["id"])
        self.assertEqual(len(ilist["issues"]), 1)

        up = self.store.update_issue(iss["id"], status="closed")
        self.assertEqual(up["status"], "closed")

    def test_events_and_radar(self):
        ev = self.store.emit_work_event("Test checkpoint", project="test-proj", event_type="checkpoint")
        self.assertEqual(ev["summary"], "Test checkpoint")
        self.assertEqual(ev["event_type"], "checkpoint")

        radar = self.store.get_station_radar()
        self.assertTrue(len(radar["workstations"]) > 0)

        conflicts = self.store.check_station_conflicts("test-proj")
        self.assertFalse(conflicts["conflict_detected"])

    def test_progress_and_session(self):
        prog = self.store.log_progress("test-proj", "Refactored module X")
        self.assertEqual(prog["project"], "test-proj")

        q = self.store.query_progress("test-proj")
        self.assertEqual(len(q["progress"]), 1)

        ses = self.store.log_session("test-proj", "Refactor Session", "Details of session", sessions_dir="my_sessions")
        session_file = Path(ses["session_file"])
        self.assertTrue(session_file.exists())
        txt = session_file.read_text()
        self.assertIn("## Refactor Session", txt)


class TestTrackStoreFactory(unittest.TestCase):
    def test_factory_selection(self):
        with tempfile.TemporaryDirectory() as td:
            local = get_track_store(root=Path(td), backend="local")
            self.assertIsInstance(local, LocalTrackStore)

            remote = get_track_store(root=Path(td), backend="remote")
            self.assertIsInstance(remote, RemoteTrackClient)

            auto_no_secret = get_track_store(root=Path(td), backend="auto")
            self.assertIsInstance(auto_no_secret, LocalTrackStore)


class TestMCPStdioServer(unittest.TestCase):
    def test_mcp_protocol(self):
        reqs = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}}),
        ]
        p = subprocess.Popen(
            [sys.executable, "-m", "onecoder.mcp"],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={"PYTHONPATH": str(ROOT), "ONECODER_TRACK_BACKEND": "local"}
        )
        stdout, stderr = p.communicate(input="\n".join(reqs) + "\n", timeout=5)
        lines = [l for l in stdout.strip().splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)

        r1 = json.loads(lines[0])
        self.assertEqual(r1["id"], 1)
        self.assertEqual(r1["result"]["serverInfo"]["name"], "onecoder-track")

        r2 = json.loads(lines[1])
        self.assertEqual(r2["id"], 2)
        tool_names = [t["name"] for t in r2["result"]["tools"]]
        self.assertIn("list_projects", tool_names)
        self.assertIn("create_sprint", tool_names)
        self.assertIn("create_issue", tool_names)
        self.assertIn("emit_work_event", tool_names)

        r3 = json.loads(lines[2])
        self.assertEqual(r3["id"], 3)
        self.assertFalse(r3["result"]["isError"])


class TestCLIIntegration(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        # make git repo
        sh(self.root, "git", "init", "-q", "-b", "main")
        sh(self.root, "git", "config", "user.email", "test@test.local")
        sh(self.root, "git", "config", "user.name", "Tester")
        (self.root / "init.txt").write_text("ok\n")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-qm", "init")

    def tearDown(self):
        self.td.cleanup()

    def test_cli_sprint_and_issue(self):
        env = {"PYTHONPATH": str(ROOT)}
        # New sprint
        rc, out, err = sh(self.root, BIN, "sprint", "new", "Sprint 10", "-p", "cli-test", "--local", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("Created sprint", out)

        # List sprint
        rc, out, err = sh(self.root, BIN, "sprint", "list", "-p", "cli-test", "--local", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("Sprint 10", out)

        # New issue
        rc, out, err = sh(self.root, BIN, "issue", "new", "Implement CLI feature", "-p", "cli-test", "--local", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("Created issue", out)

        # List issue
        rc, out, err = sh(self.root, BIN, "issue", "list", "-p", "cli-test", "--local", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("Implement CLI feature", out)

        # Pulse
        rc, out, err = sh(self.root, BIN, "pulse", "Heartbeat test", "-p", "cli-test", "--local", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("pulse emitted", out)

        # Radar
        rc, out, err = sh(self.root, BIN, "radar", "--local", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("CROSS-STATION RADAR", out)

        # Conflicts
        rc, out, err = sh(self.root, BIN, "conflicts", "-p", "cli-test", "--local", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("No conflicts detected", out)


if __name__ == "__main__":
    unittest.main()
