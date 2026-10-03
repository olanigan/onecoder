"""Policy loading. Layers (later wins): built-ins < onecoder/policy.toml < <project>/.onecoder/policy.toml < $ONECODER_POLICY.

Any unreadable or invalid layer raises PolicyError. Callers must fail closed on it.
"""

import copy
import os
import tomllib
from pathlib import Path

ONECODER_HOME = Path(__file__).resolve().parents[1]

MODES = ("auto", "human-driver", "yolo")
ISOLATIONS = ("auto", "none", "branch", "worktree")

DEFAULTS = {
    "modes": {"default": "auto", "allow_yolo_on_host": False},
    "isolation": {"default": "auto"},
    "gate": {
        "max_added_lines": 800,
        "human_merges": True,
        "protected_paths": [".git/", ".onecoder/policy.toml", ".env", "*.env", "vault.env", "*.pem", "id_rsa*"],
    },
    "supply_chain": {
        "manifests": ["requirements*.txt", "pyproject.toml", "package.json", "package-lock.json",
                      "pnpm-lock.yaml", "yarn.lock", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "uv.lock"],
        "scanner_cmd": "",
        "on_missing_scanner": "warn",
    },
    "review": {"require_verdict": True},
    "closure": {"required_files": [], "banned_files": [], "min_retro_bytes": 0},
}


class PolicyError(Exception):
    pass


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _read(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise PolicyError(f"cannot read policy {path}: {e}")


def validate(p):
    if p["modes"]["default"] not in MODES:
        raise PolicyError(f"modes.default must be one of {MODES}")
    if p["isolation"]["default"] not in ISOLATIONS:
        raise PolicyError(f"isolation.default must be one of {ISOLATIONS}")
    if not isinstance(p["gate"]["max_added_lines"], int) or p["gate"]["max_added_lines"] < 1:
        raise PolicyError("gate.max_added_lines must be a positive integer")
    if p["supply_chain"]["on_missing_scanner"] not in ("warn", "fail", "ignore"):
        raise PolicyError("supply_chain.on_missing_scanner must be warn|fail|ignore")
    c = p["closure"]
    for k in ("required_files", "banned_files"):
        if not isinstance(c[k], list) or not all(isinstance(x, str) for x in c[k]):
            raise PolicyError(f"closure.{k} must be a list of strings")
    if not isinstance(c["min_retro_bytes"], int) or c["min_retro_bytes"] < 0:
        raise PolicyError("closure.min_retro_bytes must be a non-negative integer")
    return p


def load(root=None, env=None):
    env = os.environ if env is None else env
    p = copy.deepcopy(DEFAULTS)
    p = _merge(p, _read(ONECODER_HOME / "policy.toml"))
    if root:
        p = _merge(p, _read(Path(root) / ".onecoder" / "policy.toml"))
    if env.get("ONECODER_POLICY"):
        p = _merge(p, _read(env["ONECODER_POLICY"]))
    return validate(p)
