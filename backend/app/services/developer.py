from __future__ import annotations
import json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from sqlalchemy.orm import Session
from ..ai.providers import generate_reply
from ..models import Agent, AgentRun, Project, Task
from ..security.policies import safe_path

ROLE_INSTRUCTIONS = {
    "Research Agent": "Focus on evidence, assumptions, competitors, validation questions and sources. NEVER invent interviews, survey results, quotes, citations, statistics, or source URLs. If no research tool/source is available, produce a research plan and label claims as hypotheses or assumptions.",
    "Product Manager": "Focus on requirements, user stories, acceptance criteria and priorities. Never present assumptions as validated user feedback; label unknowns and propose validation steps.",
    "Software Architect": "Focus on architecture, components, APIs, data model, security boundaries and ADRs.",
    "UI/UX Agent": "Focus on user flows, responsive UI structure, accessibility and design-system artifacts.",
    "Frontend Developer": "Produce runnable frontend source code and keep dependencies minimal.",
    "Backend Developer": "Produce runnable backend source code, APIs, validation and persistence code.",
    "QA Engineer": "Produce tests and a QA report; inspect existing artifacts and target concrete failure modes.",
    "Security Reviewer": "Perform a defensive security review and produce actionable remediation artifacts.",
    "DevOps Agent": "Produce reproducible local/dev deployment artifacts and CI guidance; do not deploy.",
    "Documentation Agent": "Produce clear setup, API and developer documentation based on the current workspace.",
    "Command Agent": "Coordinate work, resolve dependencies and decide which specialist should act next.",
}

def _json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Agent did not return valid JSON")
    return json.loads(text[start:end + 1])

def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return value[:80] or "project"

def _prefix(project: Project) -> str:
    return f"projects/{project.id}-{_slug(project.name)}"

def _snapshot(prefix: str, limit: int = 60) -> str:
    root = safe_path(prefix)
    if not root.exists(): return "Workspace is empty."
    lines=[]
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(x in path.parts for x in {".git","node_modules",".venv","__pycache__"}):
            lines.append(path.relative_to(root).as_posix())
            if len(lines)>=limit: break
    return "\n".join(lines) or "Workspace is empty."

def _source(prefix: str, limit_files: int = 12, max_chars: int = 6000) -> str:
    root=safe_path(prefix)
    if not root.exists(): return ""
    chunks=[]
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(x in path.parts for x in {".git","node_modules",".venv","__pycache__"}): continue
        if path.suffix.lower() not in {".py",".js",".ts",".tsx",".jsx",".html",".css",".json",".md",".yaml",".yml",".toml",".txt"}: continue
        try: data=path.read_text(encoding="utf-8")
        except Exception: continue
        chunks.append(f"FILE: {path.relative_to(root).as_posix()}\n{data[:max_chars]}")
        if len(chunks)>=limit_files: break
    return "\n\n---\n\n".join(chunks)

def _prompt(project: Project, task: Task, agent: Agent, prefix: str) -> str:
    return f'''You are the {agent.name} on the JARVIS software development team.

PROJECT: {project.name}
PROJECT DESCRIPTION: {project.description}
TASK: {task.title}
TASK DESCRIPTION: {task.description}
PRIORITY: {task.priority}
ROLE GUIDANCE: {ROLE_INSTRUCTIONS.get(agent.name, '')}

CURRENT WORKSPACE FILES:
{_snapshot(prefix)}

EXISTING SOURCE:
{_source(prefix)}

Work only on this task. Produce concrete, reviewable artifacts.
Do not claim to run commands, install packages, access external systems, deploy, or push git.
If a dependency is needed, document it instead of installing it.
Return ONLY valid JSON in this exact shape:
{{
  "summary": "what was completed",
  "notes": "important implementation/review notes",
  "files": [{{"path":"relative/path","content":"complete file contents"}}],
  "commands": [{{"command":"allowlisted command","cwd":"relative workspace directory","reason":"why it should be run"}}],
  "next_tasks": ["optional follow-up task"]
}}

File rules:
- Paths are relative to the project workspace.
- Never use absolute paths, .., drive letters, or system paths.
- No binary files.
- Existing files must be returned as complete replacement content.
- Analysis-only work should create a useful Markdown artifact under docs/.
'''

def _validate_rel(path: str):
    p=Path(path)
    if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]) or not path.strip():
        raise ValueError(f"Unsafe artifact path: {path}")

def _command_kind(command: str, requested: str = "verify") -> str:
    """Classify commands from their actual command text, not model-supplied labels."""
    try:
        import shlex
        parts = [part.lower() for part in shlex.split(command, posix=False)]
    except ValueError:
        parts = command.lower().split()
    normalized = " ".join(parts)
    executable = Path(parts[0]).name.lower() if parts else ""

    if executable in {"pytest", "pytest.exe", "unittest"}:
        return "test"
    if executable in {"python", "python.exe", "python3", "python3.exe"} and any(
        part in {"pytest", "unittest"} for part in parts[1:3]
    ):
        return "test"
    if executable in {"npm", "npm.cmd", "npm.exe"} and len(parts) > 1:
        if parts[1] in {"test", "run"} and (parts[1] == "test" or (len(parts) > 2 and parts[2] == "test")):
            return "test"
        if parts[1] == "run" and len(parts) > 2 and parts[2] == "build":
            return "build"
        if parts[1] == "run" and len(parts) > 2 and parts[2] == "lint":
            return "lint"
        if parts[1] in {"install", "i", "uninstall", "update"}:
            return "install"
    if executable in {"pip", "pip.exe", "pip3", "pip3.exe"} and len(parts) > 1 and parts[1] in {"install", "uninstall"}:
        return "install"
    if requested in {"build", "lint"} and any(token in normalized for token in (" build", " lint")):
        return requested
    return "verify"


def dependencies_satisfied(db: Session, task: Task) -> bool:
    try:
        ids = [int(x) for x in json.loads(task.dependencies_json or "[]")]
    except Exception:
        ids = []
    if not ids:
        return True
    rows = db.query(Task).filter(Task.id.in_(ids)).all()
    return len(rows) == len(ids) and all(row.status == "done" for row in rows)


def _git_checkpoint(prefix: str, message: str) -> str:
    """Best-effort Git checkpoint; returns a factual status string."""
    try:
        from .git import ensure_repo, commit
        ensure_repo(prefix)
        result = commit(prefix, message)
        return "committed" if result.get("committed") else "no_changes"
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}: {exc}"


def run_task(db: Session, task_id: int) -> dict[str, Any]:
    task=db.get(Task, task_id)
    if not task: raise ValueError("Task not found")
    if not task.project_id: raise ValueError("Task is not attached to a project")
    project=db.get(Project, task.project_id)
    agent=db.get(Agent, task.agent_id) if task.agent_id else None
    if not project: raise ValueError("Project not found")
    if not agent: raise ValueError("Task has no assigned agent")
    if task.status in {"done", "in_progress", "awaiting_verification"}: raise ValueError("Task is not runnable in its current state")
    if not dependencies_satisfied(db, task): raise ValueError("Task dependencies are not complete")
    prefix=_prefix(project); safe_path(prefix).mkdir(parents=True, exist_ok=True)
    git_before = _git_checkpoint(prefix, f"Before task {task.id}: {task.title}")
    run=AgentRun(task_id=task.id, agent_id=agent.id, status="running")
    db.add(run); db.commit(); db.refresh(run)
    task.status="in_progress"; db.commit()
    try:
        prompt = _prompt(project, task, agent, prefix)
        output_schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "notes": {"type": "string"},
                "files": {"type": "array", "items": {"type": "object", "properties": {
                    "path": {"type": "string"}, "content": {"type": "string"}
                }, "required": ["path", "content"]}},
                "commands": {"type": "array", "items": {"type": "object", "properties": {
                    "command": {"type": "string"}, "cwd": {"type": "string"},
                    "reason": {"type": "string"}, "kind": {"type": "string"}
                }, "required": ["command"]}}
            },
            "required": ["summary", "files", "commands"]
        }
        payload = None
        parse_error = ""
        for attempt in range(2):
            instruction = prompt if attempt == 0 else (
                prompt + "\\n\\nYour previous output could not be parsed: " + parse_error[:500]
                + "\\nReturn only one valid JSON object matching the required schema. Do not use Markdown fences."
            )
            result = generate_reply(instruction, use_search=False, response_format=output_schema)
            try:
                payload = _json_from_text(result["reply"])
                break
            except (ValueError, json.JSONDecodeError) as exc:
                parse_error = str(exc)
        if payload is None:
            raise ValueError(f"Agent JSON output invalid after retry: {parse_error}")
        # Validate the complete file batch before writing anything. This avoids
        # partial writes if a later generated path is unsafe or duplicated.
        staged = []
        seen_paths = set()
        total_bytes = 0
        for item in payload.get("files") or []:
            rel = str(item.get("path", "")).strip()
            _validate_rel(rel)
            normalized_rel = rel.replace("\\\\", "/")
            path_parts = [part for part in normalized_rel.split("/") if part]
            if any(part.lower() == ".git" for part in path_parts):
                raise ValueError("Agent output may not write inside .git")
            if Path(path_parts[-1]).name.lower() == ".env":
                raise ValueError("Agent output may not create or overwrite .env; use .env.example")
            key = normalized_rel.casefold()
            if key in seen_paths:
                raise ValueError(f"Duplicate generated file path: {rel}")
            seen_paths.add(key)
            content = str(item.get("content", ""))
            content_bytes = content.encode("utf-8")
            if len(content_bytes) > 2 * 1024 * 1024:
                raise ValueError(f"Generated file exceeds 2 MiB limit: {rel}")
            total_bytes += len(content_bytes)
            if total_bytes > 10 * 1024 * 1024:
                raise ValueError("Generated file batch exceeds 10 MiB limit")
            target = safe_path(f"{prefix}/{rel}")
            staged.append((rel, target, content))
        written = []
        change_manifest = []
        rollback = []
        try:
            for rel, target, content in staged:
                existed = target.exists()
                previous = target.read_bytes() if existed else None
                rollback.append((target, existed, previous))
                before_hash = hashlib.sha256(previous).hexdigest() if previous is not None else None
                content_bytes = content.encode("utf-8")
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".jarvis-tmp")
                try:
                    temporary.write_bytes(content_bytes)
                    temporary.replace(target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                written.append(rel)
                change_manifest.append({
                    "path": rel,
                    "change": "modified" if existed else "created",
                    "before_sha256": before_hash,
                    "after_sha256": hashlib.sha256(content_bytes).hexdigest(),
                    "bytes": len(content_bytes),
                })
        except Exception:
            # Restore earlier files if any write in this batch fails.
            for target, existed, previous in reversed(rollback):
                try:
                    if existed and previous is not None:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(previous)
                    elif target.exists():
                        target.unlink()
                except OSError:
                    pass
            raise
        commands=[]
        for item in payload.get("commands") or []:
            cmd=str(item.get("command", "")).strip()
            if cmd:
                kind=_command_kind(cmd, str(item.get("kind", "verify")))
                commands.append({"command":cmd,"cwd":str(item.get("cwd", ".")) or ".","reason":str(item.get("reason", "Agent requested verification")),"kind":kind})
        task.result=json.dumps({
            "summary": payload.get("summary", ""),
            "files": written,
            "change_manifest": change_manifest,
            "commands": commands,
            "next_tasks": [str(x)[:500] for x in (payload.get("next_tasks") or [])[:5]],
            "follow_up_tasks": [str(x)[:500] for x in (payload.get("follow_up_tasks") or [])[:5]],
        }, ensure_ascii=False)
        task.status="awaiting_verification" if any(x.get("kind") == "test" for x in commands) else "done"; run.status="completed"; run.summary=str(payload.get("summary","")); run.output=str(payload.get("notes","")); run.files_json=json.dumps(written); run.finished_at=datetime.now(timezone.utc)
        git_after = _git_checkpoint(prefix, f"After task {task.id}: {task.title}")
        task_result = json.loads(task.result or "{}")
        task_result["git_checkpoint_before"] = git_before
        task_result["git_checkpoint_after"] = git_after
        task.result = json.dumps(task_result, ensure_ascii=False)
        db.commit()
        return {"task":task,"run":run,"project":project,"files":written,"commands":commands,"summary":payload.get("summary",""),"git_before":git_before,"git_after":git_after}
    except Exception as exc:
        db.rollback(); task=db.get(Task,task_id); run=db.get(AgentRun,run.id)
        task.status="blocked"; task.result=f"Agent run failed: {type(exc).__name__}: {exc}"
        run.status="failed"; run.output=str(exc); run.finished_at=datetime.now(timezone.utc); db.commit(); raise

def ready_tasks(db: Session, project_id: int|None=None, limit: int=1):
    q=db.query(Task).filter(Task.status.in_(["todo","blocked"]))
    if project_id is not None: q=q.filter(Task.project_id==project_id)
    rows=[]
    for task in q.order_by(Task.id.asc()).all():
        if dependencies_satisfied(db, task):
            rows.append(task)
            if len(rows) >= limit:
                break
    return rows
