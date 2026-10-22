"""Build the work graph from tracking data, spec files, and governance tasks.

Mapping onto the existing model (no schema change to the CSV store):
  spec  = specs/<name>.md (frontmatter: id, title, status, epic)   [in git, reviewed]
  epic  = sprint                                                 [tracking CSV]
  task  = issue                                                  [tracking CSV]
  task  = governance task .onecoder/tasks/<id>                   [state.json, review.json]
  ac    = "- [ ] AC-n: ..." line in a governance task's brief.md
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import policy as pol
from ..task import list_tasks, tasks_dir
from ..track.local import LocalTrackStore

SPEC_DIR = "specs"
AC_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(AC-\d+)\s*:\s*(.+?)\s*$", re.M)
UNPLANNED = "group:unplanned"
GOVERNANCE = "group:governance"


def parse_frontmatter(text: str) -> Dict[str, str]:
    """Flat `key: value` frontmatter. A trailing `  # comment` is dropped."""
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    return out


def _node(id: str, kind: str, title: str, status: str, parent: Optional[str], source: str,
          data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"id": id, "kind": kind, "title": title, "status": status, "parent": parent,
            "source": source, "data": data or {}}


def _load_specs(root: Path, nodes: Dict[str, Dict[str, Any]], epic_parent: Dict[str, str]) -> None:
    for path in sorted((root / SPEC_DIR).glob("*.md")) if (root / SPEC_DIR).is_dir() else []:
        text = path.read_text(encoding="utf-8")
        meta = parse_frontmatter(text)
        sid = meta.get("id") or path.stem
        title = meta.get("title") or next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), path.stem)
        nodes[f"spec:{sid}"] = _node(f"spec:{sid}", "spec", title, meta.get("status", "draft"), None, "specs",
                                    {"path": str(path.relative_to(root))})
        if meta.get("epic"):
            epic_parent.setdefault(meta["epic"], f"spec:{sid}")


def _load_tracking(store: LocalTrackStore, nodes: Dict[str, Dict[str, Any]], epic_parent: Dict[str, str]) -> None:
    for s in store.list_sprints().get("sprints", []):
        eid = f"epic:{s['id']}"
        parent = epic_parent.get(s["id"])
        nodes[eid] = _node(eid, "epic", s.get("name") or s["id"], s.get("status") or "planned", parent, "tracking",
                           {"sprint": s["id"], "project": s.get("project", "")})
    for i in store.list_issues().get("issues", []):
        tid = f"task:{i['id']}"
        parent = f"epic:{i['sprint']}" if i.get("sprint") else UNPLANNED
        nodes[tid] = _node(tid, "task", i.get("title") or i["id"], i.get("status") or "open", parent, "tracking",
                           {"issue": i["id"], "labels": i.get("labels", [])})


def _load_governance(root: Path, nodes: Dict[str, Dict[str, Any]]) -> None:
    for state in list_tasks(root):
        gid = f"gov:{state['id']}"
        verdict_path = tasks_dir(root) / state["id"] / "review.json"
        status = "open"
        if verdict_path.exists():
            try:
                status = json.loads(verdict_path.read_text()).get("verdict", "reviewed")
            except (ValueError, AttributeError):
                status = "reviewed"
        issue_parent = f"task:{state['issue']}" if state.get("issue") and f"task:{state['issue']}" in nodes else GOVERNANCE
        nodes[gid] = _node(gid, "task", state["id"], status, issue_parent, "governance",
                           {"mode": state.get("mode"), "isolation": state.get("isolation"), "branch": state.get("branch")})
        brief = tasks_dir(root) / state["id"] / "brief.md"
        if brief.exists():
            for m in AC_RE.finditer(brief.read_text(encoding="utf-8")):
                ac = f"ac:{state['id']}:{m.group(2)}"
                nodes[ac] = _node(ac, "ac", f"{m.group(2)}: {m.group(3)}", "done" if m.group(1).lower() == "x" else "open",
                                  gid, "governance")


def _ensure_groups(nodes: Dict[str, Dict[str, Any]]) -> None:
    """Add group nodes only when something lands in them, so the tree has no empty buckets."""
    for gid, title in ((UNPLANNED, "Unplanned tasks"), (GOVERNANCE, "Governance tasks")):
        if any(n["parent"] == gid for n in nodes.values()):
            nodes[gid] = _node(gid, "group", title, "", None, "derived")


def build_graph(root: Path, store: Optional[LocalTrackStore] = None) -> Dict[str, Any]:
    """Pure read of the project. Always from CSV and files, never from SQLite."""
    store = store or LocalTrackStore(root=root, policy=pol.load(root))
    nodes: Dict[str, Dict[str, Any]] = {}
    epic_parent: Dict[str, str] = {}
    _load_specs(root, nodes, epic_parent)
    _load_tracking(store, nodes, epic_parent)
    _load_governance(root, nodes)
    _ensure_groups(nodes)
    # A spec-linked epic may point at a spec that does not exist. Detach it rather than dangle.
    for n in nodes.values():
        if n["parent"] and n["parent"] not in nodes:
            n["parent"] = None
    return {
        "project": root.name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "csv",
        "nodes": sorted(nodes.values(), key=lambda n: (n["kind"], n["id"])),
        "counts": _counts(nodes.values()),
    }


def _counts(nodes) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for n in nodes:
        if n["kind"] == "group":
            continue
        bucket = out.setdefault(n["kind"], {})
        bucket[n["status"]] = bucket.get(n["status"], 0) + 1
    return out
