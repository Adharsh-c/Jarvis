from __future__ import annotations
import subprocess
from pathlib import Path
from ..security.policies import safe_path

def _repo_root(prefix: str):
    root = safe_path(prefix)
    root.mkdir(parents=True, exist_ok=True)
    return root

def _run(args: list[str], cwd: Path):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)

def ensure_repo(prefix: str):
    root = _repo_root(prefix)
    if not (root / ".git").exists():
        r = _run(["git", "init"], root)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip() or "git init failed")
    # Generated project workspaces need a local identity for automatic commits.
    # Preserve any identity the user already configured in that repository.
    for key, value in (("user.name", "JARVIS Local Agent"), ("user.email", "jarvis@localhost")):
        existing = _run(["git", "config", "--get", key], root)
        if existing.returncode != 0 or not existing.stdout.strip():
            configured = _run(["git", "config", key, value], root)
            if configured.returncode != 0:
                raise RuntimeError((configured.stderr or configured.stdout).strip() or f"Could not set local Git {key}")
    return root

def _branch(root: Path):
    r = _run(["git", "branch", "--show-current"], root)
    return r.stdout.strip() or "main"

def status(prefix: str):
    root = ensure_repo(prefix)
    r = _run(["git", "status", "--short"], root)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git status failed")
    return {"branch": _branch(root), "changes": r.stdout.splitlines()}

def commit(prefix: str, message: str):
    root = ensure_repo(prefix)
    add = _run(["git", "add", "-A"], root)
    if add.returncode != 0:
        raise RuntimeError(add.stderr.strip() or "git add failed")
    diff = _run(["git", "diff", "--cached", "--quiet"], root)
    if diff.returncode == 0:
        return {"committed": False, "message": "No changes to commit", "branch": _branch(root)}
    r = _run(["git", "commit", "-m", message[:120]], root)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "git commit failed")
    return {"committed": True, "message": message[:120], "branch": _branch(root), "output": r.stdout[-4000:]}
