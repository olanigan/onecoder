import subprocess
from pathlib import Path


def git(root, *args, check=False):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def repo_root(cwd):
    rc, out, _ = git(cwd, "rev-parse", "--show-toplevel")
    return Path(out) if rc == 0 and out else None


def state_root(root):
    """Main worktree root: shared by all linked worktrees, so task state is found from anywhere."""
    rc, out, _ = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if rc != 0 or not out:
        return Path(root)
    common = Path(out)
    return common.parent if common.name == ".git" else Path(root)


def current_branch(root):
    rc, out, _ = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return out if rc == 0 and out != "HEAD" else None


def head_sha(root):
    rc, out, _ = git(root, "rev-parse", "HEAD")
    return out if rc == 0 else None


def default_branch(root):
    rc, out, _ = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and out:
        return out.split("/", 1)[-1]
    for cand in ("main", "master", "trunk"):
        if git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{cand}")[0] == 0:
            return cand
    return current_branch(root)


def is_dirty(root):
    rc, out, _ = git(root, "status", "--porcelain", "--untracked-files=normal")
    # .onecoder/ runtime state is excluded via info/exclude, so it never counts as dirt.
    return rc == 0 and bool(out)


def worktree_count(root):
    rc, out, _ = git(root, "worktree", "list", "--porcelain")
    return sum(1 for l in out.splitlines() if l.startswith("worktree ")) if rc == 0 else 0


def in_linked_worktree(root):
    rc1, a, _ = git(root, "rev-parse", "--path-format=absolute", "--git-dir")
    rc2, b, _ = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return rc1 == 0 and rc2 == 0 and a != b


def ensure_excluded(root, pattern="/.onecoder/"):
    rc, out, _ = git(root, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
    if rc != 0:
        return
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = p.read_text() if p.exists() else ""
    if pattern not in cur.splitlines():
        p.write_text(cur + ("" if cur.endswith("\n") or not cur else "\n") + pattern + "\n")
