"""Deterministic tool-call gate. No model calls, no network.

evaluate() -> verdict {level: allow|warn|block, reasons: [...]}; decide() maps it through the mode.
Block is the hard floor: it denies in every mode. Warn asks a human-driver and is logged in yolo.
Callers fail closed: any exception here must become a deny.
"""

import fnmatch
import re
from pathlib import PurePosixPath

from . import gitutil as g

RANK = {"allow": 0, "warn": 1, "block": 2}

SHELL_TOOLS = {"bash", "shell", "sh", "run_command", "execute_command", "terminal", "exec", "local_shell"}
WRITE_TOOLS = {"write", "edit", "multiedit", "write_file", "edit_file", "apply_patch", "str_replace_editor",
               "str_replace_based_edit_tool", "create_file", "notebookedit"}
CONTENT_KEYS = {"content", "new_string", "new_str", "text", "patch", "diff", "file_text", "contents"}

# Real credential shapes only. A bare word like "password" is not a secret.
SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("quoted-credential", re.compile(r"""(?i)\b(?:api[_-]?key|secret(?:[_-]?key)?|token|passwd|password)\b\s*[:=]\s*['"][A-Za-z0-9/+_=.\-]{16,}['"]""")),
]

_NOCHAIN = r"[^\n;&|]*"
BLOCKED_COMMANDS = [
    ("force-push", re.compile(r"\bgit\s+push\b" + _NOCHAIN + r"(--force\b|--force-with-lease\b|\s-f\b)")),
    ("bypass-hooks", re.compile(r"\bgit\s+(commit|push|merge|rebase)\b" + _NOCHAIN + r"--no-verify\b")),
    ("pipe-to-shell", re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")),
    ("rm-rf-root", re.compile(r"\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*[fF]|-[a-zA-Z]*[fF][a-zA-Z]*[rR])[a-zA-Z]*\s+(/|~|\$HOME|/\*|\*)(\s|$)")),
    ("agent-merge", re.compile(r"\bgh\s+pr\s+merge\b")),
]
RISKY_COMMANDS = [
    ("hard-reset", re.compile(r"\bgit\s+reset\b" + _NOCHAIN + r"--hard\b")),
    ("git-clean", re.compile(r"\bgit\s+clean\b" + _NOCHAIN + r"-[a-zA-Z]*f")),
    ("branch-delete", re.compile(r"\bgit\s+branch\b" + _NOCHAIN + r"\s-D\b")),
    ("chmod-777", re.compile(r"\bchmod\s+-R\s+0?777\b")),
    ("sql-drop", re.compile(r"(?i)\bdrop\s+(table|database)\b")),
    ("sudo", re.compile(r"(^|[;&|]\s*)sudo\b")),
    ("publish", re.compile(r"\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b")),
]
_PUSH = re.compile(r"\bgit\s+push\b([^\n;&|]*)")
_MUTATE = r"(?:>>?|\btee\b|\brm\b|\bmv\b|\bcp\b|\bsed\s+-i\b|\btruncate\b|\bchmod\b)"


def _verdict():
    return {"level": "allow", "reasons": []}


def _add(v, level, rule, detail):
    v["reasons"].append({"level": level, "rule": rule, "detail": detail})
    if RANK[level] > RANK[v["level"]]:
        v["level"] = level


def scan_secrets(text):
    """[(rule, line_no)] -- never returns the matched value."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, rx in SECRET_PATTERNS:
            if rx.search(line):
                hits.append((name, n))
    return hits


def _is_protected(path, protected):
    s = path.replace("\\", "/")
    s = s[2:] if s.startswith("./") else s
    p = PurePosixPath(s)
    for pat in protected:
        if pat.endswith("/"):
            d = pat.rstrip("/")
            if s == d or s.startswith(d + "/") or ("/" + d + "/") in ("/" + s):
                return pat
        elif fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(p.name, pat) or s == pat:
            return pat
    return None


def _rel(path, root):
    if root and path.startswith(str(root).rstrip("/") + "/"):
        return path[len(str(root).rstrip("/")) + 1:]
    return path


def normalize(payload):
    """Harness payload -> (kind, data). Unknown tools are 'other' (not this gate's business)."""
    name = str(payload.get("tool_name") or payload.get("tool") or "").lower()
    inp = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    if name in SHELL_TOOLS:
        cmd = inp.get("command") or inp.get("cmd") or ""
        if isinstance(cmd, list):
            cmd = " ".join(map(str, cmd))
        return "command", {"command": str(cmd)}
    if name in WRITE_TOOLS:
        path = inp.get("file_path") or inp.get("path") or inp.get("filename") or ""
        chunks = [str(v) for k, v in inp.items() if k in CONTENT_KEYS and isinstance(v, str)]
        for e in inp.get("edits") or []:
            if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                chunks.append(e["new_string"])
        return "write", {"path": str(path), "content": "\n".join(chunks)}
    return "other", {}


def _check_command(v, cmd, policy, root):
    for name, rx in BLOCKED_COMMANDS:
        if name == "agent-merge" and not policy["gate"]["human_merges"]:
            continue
        if rx.search(cmd):
            _add(v, "block", name, "hard floor: denied in every mode")
    for name, rx in RISKY_COMMANDS:
        if rx.search(cmd):
            _add(v, "warn", name, "destructive or irreversible")
    for m in _PUSH.finditer(cmd):
        args = [a for a in m.group(1).split() if not a.startswith("-")]
        refs = args[1:] if len(args) > 1 else []
        default = g.default_branch(root) if root else None
        names = {"main", "master", "trunk"} | ({default} if default else set())
        targets = {r.split(":")[-1].removeprefix("refs/heads/") for r in refs}
        cur = g.current_branch(root) if root else None
        if targets & names or (not refs and cur in names):
            _add(v, "block", "push-default-branch", "agents never push the default branch; open a branch/PR and let the human merge")
    for pat in policy["gate"]["protected_paths"]:
        bare = pat.rstrip("/")
        if "*" in bare:
            rx = re.escape(bare).replace(r"\*", r"[^\s/]*")
        else:
            rx = re.escape(bare)
        if re.search(_MUTATE + _NOCHAIN + r"(?<![\w.-])" + rx + r"(?![\w-])", cmd):
            _add(v, "block", "protected-path", f"command mutates protected path {pat}")


def _check_write(v, path, content, policy, root):
    hit = _is_protected(_rel(path, root), policy["gate"]["protected_paths"])
    if hit:
        _add(v, "block", "protected-path", f"write to protected path {hit}")
    for rule, line in scan_secrets(content):
        _add(v, "block", "secret", f"{rule} at line {line} of content")
    n = len(content.splitlines())
    if n > policy["gate"]["max_added_lines"]:
        _add(v, "warn", "large-write", f"{n} lines exceeds gate.max_added_lines={policy['gate']['max_added_lines']}")


def evaluate(payload, policy, root=None):
    v = _verdict()
    kind, data = normalize(payload)
    if kind == "command":
        _check_command(v, data["command"], policy, root)
    elif kind == "write":
        _check_write(v, data["path"], data["content"], policy, root)
    return v


def decide(verdict, mode):
    """-> (decision, reason). decision in allow|ask|deny. Block is a floor that no mode lowers."""
    rules = ", ".join(f"{r['rule']}" for r in verdict["reasons"]) or "ok"
    if verdict["level"] == "block":
        return "deny", f"onecoder gate: blocked ({rules})"
    if verdict["level"] == "warn":
        if mode == "human-driver":
            return "ask", f"onecoder gate: needs your approval ({rules})"
        return "allow", f"onecoder gate: warned, allowed in {mode} ({rules})"
    return "allow", "ok"
