"""OneCoder MCP Server: Model Context Protocol stdio server for track and governance tools."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .track import get_track_store
from .track.workstation import get_workstation_id

TOOLS = [
    {
        "name": "validate_workstations",
        "description": "Audit and validate onboarding status, registered project paths, and reachability across workstations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workstation": {"type": "string", "description": "Optional target workstation ID to check specifically"}
            }
        }
    },
    {
        "name": "onboard_workstation",
        "description": "Self-onboard this workstation: auto-detects machine identity and scans a root directory to register verified local project paths.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Root directory to scan. Defaults to current workspace root."}
            }
        }
    },
    {
        "name": "emit_work_event",
        "description": "Emit a real-time agent work event/pulse into the cross-station stream (auto-capturing workstation, git branch, and dirty file count). No commits required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Brief description of current action, agent goal, or milestone"},
                "project": {"type": "string", "description": "Project id/name, e.g. 'decision-engine'"},
                "event_type": {"type": "string", "description": "'pulse' | 'checkpoint' | 'session_start' | 'handoff' | 'error'"},
                "dirty_files": {"type": "array", "items": {"type": "string"}, "description": "Optional list of modified files; auto-detected if omitted"},
                "metadata": {"type": "object", "description": "Optional JSON metadata (e.g. agent name, model, task tokens)"}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "get_station_radar",
        "description": "Get cross-workstation radar: real-time status of all machines, active projects, dirty trees, and conflict warnings.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "check_station_conflicts",
        "description": "Check if other workstations have recently touched a project with uncommitted or unpushed work, avoiding cross-station stepping.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project id/name, e.g. 'decision-engine'"}
            },
            "required": ["project"]
        }
    },
    {
        "name": "list_projects",
        "description": "List all tracked projects across all workstations, optionally filtered by category, tag, or status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category filter: 'monetized_app', 'productized_template', 'working_prototype', 'experiment', 'infrastructure'"},
                "status": {"type": "string", "description": "Status filter, e.g. 'active'"},
                "tag": {"type": "string", "description": "Tag filter, e.g. 'cloudflare', 'ai', 'slm'"}
            }
        }
    },
    {
        "name": "update_project",
        "description": "Update a project's category, status, name, tags, repo_url, or workstation path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Project ID, e.g. 'decision-engine'"},
                "name": {"type": "string"},
                "category": {"type": "string"},
                "status": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "repo_url": {"type": "string"},
                "path": {"type": "string", "description": "Absolute local path on current workstation"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "get_project_location",
        "description": "Get cross-workstation location details for a project: repo URL, local path on this machine, and paths on all other workstations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project id/name"}
            },
            "required": ["project"]
        }
    },
    {
        "name": "register_project_path",
        "description": "Register or update the local absolute filesystem path and/or GitHub repo URL for a project on this workstation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project id/name"},
                "path": {"type": "string", "description": "Absolute path on this workstation. Defaults to cwd."},
                "repo_url": {"type": "string", "description": "GitHub repository URL"}
            },
            "required": ["project"]
        }
    },
    {
        "name": "log_session",
        "description": "Write a dev session log markdown file into the given project's sessions directory, AND record a matching progress_log entry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project id/name"},
                "task": {"type": "string", "description": "Short title, e.g. 'feat: ADS primitive engine'"},
                "summary": {"type": "string", "description": "Full markdown body of the session log"},
                "sessions_dir": {"type": "string", "description": "Directory to write the session file into. Defaults to './sessions'"},
                "issue": {"type": "string"},
                "sprint": {"type": "string"}
            },
            "required": ["project", "task", "summary"]
        }
    },
    {
        "name": "log_progress",
        "description": "Log a freeform progress note against a project (and optionally an issue/sprint). Auto-stamps workstation hostname and current git branch/commit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "note": {"type": "string"},
                "sprint": {"type": "string"},
                "issue": {"type": "string"}
            },
            "required": ["project", "note"]
        }
    },
    {
        "name": "query_progress",
        "description": "Query the progress log, optionally filtered by project, issue, sprint, or since a given ISO date.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "sprint": {"type": "string"},
                "issue": {"type": "string"},
                "since": {"type": "string", "description": "ISO date; only entries at/after this time"}
            }
        }
    },
    {
        "name": "create_issue",
        "description": "Create an issue under a project, optionally assigned to a sprint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project id/name"},
                "title": {"type": "string"},
                "sprint": {"type": "string", "description": "Sprint id to attach this issue to"},
                "status": {"type": "string", "description": "Defaults to 'open'"},
                "labels": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["project", "title"]
        }
    },
    {
        "name": "update_issue",
        "description": "Update an issue's title, status, sprint, or labels.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "sprint": {"type": "string"},
                "status": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["id"]
        }
    },
    {
        "name": "list_issues",
        "description": "List issues, optionally filtered by project, status, or sprint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "sprint": {"type": "string"},
                "status": {"type": "string"}
            }
        }
    },
    {
        "name": "create_sprint",
        "description": "Create a sprint under a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "name": {"type": "string"},
                "status": {"type": "string", "description": "Defaults to 'planned'"},
                "starts_at": {"type": "string", "description": "ISO date"},
                "ends_at": {"type": "string", "description": "ISO date"}
            },
            "required": ["project", "name"]
        }
    },
    {
        "name": "update_sprint",
        "description": "Update a sprint's name, status, or dates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "status": {"type": "string"},
                "starts_at": {"type": "string"},
                "ends_at": {"type": "string"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "list_sprints",
        "description": "List sprints, optionally filtered by project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"}
            }
        }
    }
]


def execute_tool(store: Any, name: str, args: Dict[str, Any]) -> Any:
    method = getattr(store, name, None)
    if not method:
        raise ValueError(f"Unknown tool: {name}")
    return method(**args)


def run_stdio_server(backend: Optional[str] = None, root: Optional[Path] = None):
    """Run MCP server over stdio using standard JSON-RPC 2.0."""
    store = get_track_store(root=root, backend=backend)
    backend_kind = "remote" if hasattr(store, "secret") and store.secret else "local"
    sys.stderr.write(f"onecoder-track MCP server running (backend={backend_kind})\n")
    sys.stderr.flush()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception as e:
            err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "onecoder-track", "version": "0.1.0"}
                }
            }
        elif method == "notifications/initialized":
            continue  # Notification, no response
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                result_data = execute_tool(store, tool_name, tool_args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result_data, indent=2)}],
                        "isError": False
                    }
                }
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True
                    }
                }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
