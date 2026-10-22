"""Per-project SQLite index for the visual graph: `.onecoder/track.db`.

CSV (or the spec and governance files) is the source of truth. This database is derived,
gitignored, and rebuilt whenever its inputs change. If it cannot be written or read, the caller
falls back to building the graph straight from CSV, and says so.
"""

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from .. import gitutil as g
from .. import policy as pol
from ..track.local import LocalTrackStore
from .model import SPEC_DIR, _counts

DB_NAME = "track.db"
GITIGNORE = "# Derived index. Rebuilt from CSV, specs and governance files. Never commit.\ntrack.db\ntrack.db-*\n"
SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT, status TEXT,
    parent TEXT, source TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def db_path(root: Path) -> Path:
    return g.state_root(root) / ".onecoder" / DB_NAME


def fingerprint(root: Path) -> str:
    """Hash of every input's path, mtime and size. Any edit to CSV, specs, or governance files changes it."""
    inputs = []
    track_dir = LocalTrackStore(root=root, policy=pol.load(root)).track_dir
    inputs += sorted(track_dir.glob("*.csv"))
    inputs += sorted((root / SPEC_DIR).glob("*.md")) if (root / SPEC_DIR).is_dir() else []
    tdir = g.state_root(root) / ".onecoder" / "tasks"
    if tdir.is_dir():
        inputs += sorted(p for p in tdir.rglob("*") if p.is_file())
    h = hashlib.sha256()
    for p in inputs:
        st = p.stat()
        h.update(f"{p}|{st.st_mtime_ns}|{st.st_size}\n".encode())
    return h.hexdigest()


def ensure_gitignore(dbdir: Path) -> None:
    """Self-ignoring: the index never gets committed, in this repo or a nested one."""
    gi = dbdir / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE)


def write(root: Path, graph: Dict[str, Any], fp: str) -> Path:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_gitignore(path.parent)
    tmp = path.with_name(DB_NAME + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO nodes (id, kind, title, status, parent, source, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(n["id"], n["kind"], n["title"], n["status"], n["parent"], n["source"], json.dumps(n["data"]))
             for n in graph["nodes"]],
        )
        conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)",
                         [("fingerprint", fp), ("generated_at", graph["generated_at"]), ("project", graph["project"])])
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, path)
    return path


def read(root: Path, fp: str) -> Optional[Dict[str, Any]]:
    """Return the cached graph only if it was built from exactly the current inputs."""
    path = db_path(root)
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        if meta.get("fingerprint") != fp:
            return None
        rows = conn.execute("SELECT id, kind, title, status, parent, source, data FROM nodes ORDER BY kind, id").fetchall()
    finally:
        conn.close()
    nodes = [{"id": r[0], "kind": r[1], "title": r[2], "status": r[3], "parent": r[4], "source": r[5],
              "data": json.loads(r[6] or "{}")} for r in rows]
    return {"project": meta.get("project", root.name), "generated_at": meta.get("generated_at", ""),
            "source": "sqlite", "nodes": nodes, "counts": _counts(nodes)}
