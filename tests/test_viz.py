"""Tests for the visual work graph: model, SQLite index, CSV fallback, HTTP surface, and CLI."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from onecoder.track.local import LocalTrackStore
from onecoder.viz import store as viz_store
from onecoder.viz.model import build_graph, parse_frontmatter
from onecoder.viz.server import make_server
from onecoder.viz.snapshot import snapshot

BRIEF = """---
id: gen-ui-core
kind: ship          # ship = authorized change
---
# gen-ui-core

- [x] AC-1: catalog has four components
- [ ] AC-2: verbatim check is property tested
"""


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=path, check=True)
    return path


def seed(root: Path) -> None:
    """A realistic project: a spec, an epic that implements it, tasks, and one governance task."""
    (root / "specs").mkdir()
    (root / "specs" / "generative-ui.md").write_text(
        "---\nid: gen-ui\ntitle: Generative UI MVP\nstatus: approved\nepic: sprint-mvp\n---\n# body\n")
    store = LocalTrackStore(root=root)
    store.create_sprint(project="demo", name="MVP build", status="active", id="sprint-mvp")
    store.create_issue(project="demo", title="Normalizer table tests", sprint="sprint-mvp")
    store.create_issue(project="demo", title="Renderer page")
    issue = store.list_issues(sprint="sprint-mvp")["issues"][0]
    gov = root / ".onecoder" / "tasks" / "gen-ui-core"
    gov.mkdir(parents=True)
    (gov / "state.json").write_text(json.dumps({"id": "gen-ui-core", "mode": "human-driver",
                                                "isolation": "none", "branch": "main", "issue": issue["id"]}))
    (gov / "brief.md").write_text(BRIEF)
    (gov / "review.json").write_text(json.dumps({"verdict": "pass"}))


class TestModel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = git_repo(Path(self.tmp.name) / "proj")
        seed(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_frontmatter_drops_inline_comments(self):
        meta = parse_frontmatter("---\nkind: ship          # ship = authorized\nid: x\n---\nbody")
        self.assertEqual(meta, {"kind": "ship", "id": "x"})

    def test_spec_epic_task_ac_hierarchy(self):
        g = build_graph(self.root)
        by_id = {n["id"]: n for n in g["nodes"]}
        self.assertEqual(by_id["spec:gen-ui"]["title"], "Generative UI MVP")
        self.assertEqual(by_id["epic:sprint-mvp"]["parent"], "spec:gen-ui")
        issue_id = [n for n in g["nodes"] if n["kind"] == "task" and n["title"] == "Normalizer table tests"][0]["id"]
        self.assertEqual(by_id[issue_id]["parent"], "epic:sprint-mvp")
        self.assertEqual(by_id["gov:gen-ui-core"]["parent"], issue_id)
        self.assertEqual(by_id["gov:gen-ui-core"]["status"], "pass")
        self.assertEqual(by_id["ac:gen-ui-core:AC-1"]["status"], "done")
        self.assertEqual(by_id["ac:gen-ui-core:AC-2"]["status"], "open")
        self.assertEqual(by_id["ac:gen-ui-core:AC-2"]["parent"], "gov:gen-ui-core")

    def test_unplanned_tasks_go_to_a_group_and_no_dangling_parents(self):
        g = build_graph(self.root)
        by_id = {n["id"]: n for n in g["nodes"]}
        renderer = [n for n in g["nodes"] if n["title"] == "Renderer page"][0]
        self.assertEqual(renderer["parent"], "group:unplanned")
        self.assertIn("group:unplanned", by_id)
        for n in g["nodes"]:
            if n["parent"]:
                self.assertIn(n["parent"], by_id)

    def test_counts_exclude_groups(self):
        counts = build_graph(self.root)["counts"]
        self.assertNotIn("group", counts)
        self.assertEqual(counts["spec"], {"approved": 1})


class TestIdsDoNotCollide(unittest.TestCase):
    def test_issues_created_in_a_burst_all_keep_distinct_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalTrackStore(root=git_repo(Path(tmp) / "p"))
            ids = [store.create_issue(project="demo", title=f"t{i}")["id"] for i in range(20)]
            self.assertEqual(len(set(ids)), 20)
            self.assertEqual(len(store.list_issues()["issues"]), 20)


class TestIndexAndFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = git_repo(Path(self.tmp.name) / "proj")
        seed(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sqlite_index_is_built_then_reused_until_an_input_changes(self):
        first = snapshot(self.root)
        self.assertEqual(first["source"], "sqlite")
        self.assertTrue((self.root / ".onecoder" / "track.db").exists())
        self.assertEqual(snapshot(self.root)["generated_at"], first["generated_at"])  # served from the index
        LocalTrackStore(root=self.root).create_issue(project="demo", title="New task after the index")
        second = snapshot(self.root)
        self.assertTrue(any(n["title"] == "New task after the index" for n in second["nodes"]))

    def test_index_is_self_ignoring_and_git_ignores_only_the_db(self):
        snapshot(self.root)
        gi = (self.root / ".onecoder" / ".gitignore").read_text()
        self.assertIn("track.db", gi)
        ignored = subprocess.run(["git", "check-ignore", "-q", ".onecoder/track.db"], cwd=self.root).returncode
        kept = subprocess.run(["git", "check-ignore", "-q", ".onecoder/track/issues.csv"], cwd=self.root).returncode
        self.assertEqual(ignored, 0)
        self.assertNotEqual(kept, 0)

    def test_falls_back_to_csv_when_the_index_cannot_be_written(self):
        # Put a directory where the database file must go: the write fails, the UI still works.
        (self.root / ".onecoder" / "track.db").mkdir(parents=True)
        g = snapshot(self.root)
        self.assertEqual(g["source"], "csv")
        self.assertIn("serving from CSV", g["warning"])
        self.assertTrue(any(n["title"] == "Renderer page" for n in g["nodes"]))

    def test_stale_index_is_never_served(self):
        fp = viz_store.fingerprint(self.root)
        viz_store.write(self.root, build_graph(self.root), fp)
        (self.root / "specs" / "generative-ui.md").write_text("---\nid: gen-ui\ntitle: Renamed\n---\n")
        self.assertIsNone(viz_store.read(self.root, viz_store.fingerprint(self.root)))


class TestHttpAndCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = git_repo(Path(self.tmp.name) / "proj")
        seed(self.root)
        self.server = make_server(self.root, port=0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_page_and_graph_are_served_with_a_strict_csp(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"OneCoder: work graph", body)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        status, headers, body = self.get("/api/graph")
        graph = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn(graph["source"], {"sqlite", "csv"})
        self.assertTrue(any(n["kind"] == "epic" for n in graph["nodes"]))
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_unknown_paths_are_404(self):
        self.assertEqual(self.get("/etc/passwd")[0], 404)

    def test_cli_print_json_runs_from_the_project(self):
        r = subprocess.run([sys.executable, "-m", "onecoder", "viz", "--print-json"],
                           cwd=self.root, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(ROOT)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("spec:gen-ui", r.stdout)


if __name__ == "__main__":
    unittest.main()
