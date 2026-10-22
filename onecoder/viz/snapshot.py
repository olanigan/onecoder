"""One entry point for the UI: SQLite when it is current, rebuilt when it is not, CSV when it cannot be used."""

import sqlite3
from pathlib import Path
from typing import Any, Dict

from . import store
from .model import build_graph


def snapshot(root: Path) -> Dict[str, Any]:
    try:
        fp = store.fingerprint(root)
        cached = store.read(root, fp)
        if cached is not None:
            return cached
        graph = build_graph(root)
        store.write(root, graph, fp)
        graph["source"] = "sqlite"
        return graph
    except (OSError, sqlite3.Error) as e:
        graph = build_graph(root)
        graph["source"] = "csv"
        graph["warning"] = f"sqlite index unavailable, serving from CSV: {e}"
        return graph
