from pathlib import Path, PureWindowsPath
import shlex
import re
import subprocess
from ..config import settings

# Deliberately small allowlist. Commands run without a shell and only inside
# the configured workspace. Human approval remains mandatory at the API layer.
ALLOWED_COMMANDS = {"python", "python3", "pip", "pip3", "npm", "node", "git", "pytest", "uvicorn"}
SHELL_METACHARACTERS = set(";|&<>`\n\r")


def workspace_root():
    return Path(settings.workspace_path).resolve()


def safe_path(relative: str):
    root = workspace_root()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path is outside approved workspace")
    return candidate


def _parse(command: str):
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Empty command")
    # This conservative rule also rejects quoted shell syntax. It avoids the
    # ambiguity of shell parsing and is safer than trying to strip operators.
    if any(char in command for char in SHELL_METACHARACTERS):
        raise ValueError("Shell operators and command chaining are not allowed")
    if re.search(r"(?i)(?:^|\s|[\"'])[a-z]:[\\/]", command) or re.search(r"(?<!\S)\.\.[\\/]", command):
        raise ValueError("Absolute or parent-directory command paths are not allowed")
    try:
        parts = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError("Invalid command quoting") from exc
    if not parts:
        raise ValueError("Empty command")
    executable = Path(parts[0]).name.lower()
    if executable not in ALLOWED_COMMANDS:
        raise ValueError(f"Command '{executable}' is not allowlisted")
    args = parts[1:]
    if executable in {"python", "python3", "node"}:
        if any(arg in {"-c", "-e", "--eval"} for arg in args):
            raise ValueError("Inline code execution is not allowed; use a reviewed workspace file")
        if executable in {"python", "python3"} and args and args[0].startswith("-") and args[0] not in {"-m"}:
            raise ValueError("Python interpreter flags are restricted")
    if executable in {"pip", "pip3"} and args and args[0].lower() in {"install", "uninstall"}:
        raise ValueError("Package installation/removal must use the dedicated reviewed approval workflow")
    if executable == "npm" and args and args[0].lower() in {"install", "i", "uninstall", "update", "exec"}:
        raise ValueError("npm package changes or execution require a dedicated reviewed approval workflow")
    if executable == "git" and args:
        subcommand = args[0].lower()
        safe_git = {"status", "diff", "log", "show", "ls-files", "branch", "rev-parse", "add", "commit", "init"}
        if subcommand not in safe_git:
            raise ValueError(f"Git subcommand '{subcommand}' is not allowlisted")
        if any(arg in {"-C", "--git-dir", "--work-tree", "--config-env"} for arg in args):
            raise ValueError("Git path/config override flags are not allowed")
    if executable in {"python", "python3"} and len(args) >= 2 and args[0] == "-m":
        if args[1].lower() in {"pip", "ensurepip"}:
            raise ValueError("Package management through Python modules is not allowed")
        if args[1].lower() not in {"pytest", "unittest", "compileall"}:
            raise ValueError(f"Python module '{args[1]}' is not allowlisted")
    # Prevent path arguments from escaping the workspace even though cwd itself
    # is checked separately. Option values and normal source-relative paths work.
    for arg in args:
        if arg.startswith("-"):
            continue
        if PureWindowsPath(arg).is_absolute() or Path(arg).is_absolute():
            raise ValueError("Absolute command paths are not allowed; use workspace-relative paths")
        normalized = arg.replace("\\\\", "/")
        path_parts = [part for part in normalized.split("/") if part]
        if ".." in path_parts:
            raise ValueError("Parent-directory command paths are not allowed")
    return [executable, *args]


def validate_command(command: str):
    try:
        _parse(command)
        return True, "Allowed for execution after human approval"
    except ValueError as exc:
        return False, str(exc)


def run_safe_command(command: str, cwd: str = "."):
    args = _parse(command)
    path = safe_path(cwd)
    result = subprocess.run(args, cwd=path, shell=False, capture_output=True, text=True, timeout=settings.command_timeout_seconds)
    return {"return_code": result.returncode, "stdout": result.stdout[-10000:], "stderr": result.stderr[-10000:], "command": args}
