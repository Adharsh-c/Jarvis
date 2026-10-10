from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Agent, Project, Task
from .core import log
from .developer import run_task, ready_tasks
from .review import review_task

# One orchestration worker per project. This prevents two dashboard clicks from
# launching duplicate workers for the same project.
_LOCK = threading.Lock()
_RUNNING: set[int] = set()


def _set_agent_status(db: Session, agent_id: int, status: str):
    agent = db.get(Agent, agent_id)
    if agent:
        agent.status = status
        db.commit()


def _project_done(db: Session, project_id: int) -> bool:
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    return bool(tasks) and all(t.status == "done" for t in tasks)


def _has_blocked(db: Session, project_id: int) -> bool:
    return db.query(Task).filter(Task.project_id == project_id, Task.status == "blocked").count() > 0


def _run_one(task_id: int, actor: str):
    db = SessionLocal()
    agent_id = None
    try:
        task = db.get(Task, task_id)
        if not task:
            return {"task_id": task_id, "error": "Task not found"}
        agent_id = task.agent_id
        if agent_id:
            _set_agent_status(db, agent_id, "working")
        log(db, "team.task_started", f"Task #{task.id}: {task.title}", actor)
        result = run_task(db, task.id)
        # Completed repair tasks reopen their source task only after all sibling
        # QA fixes are complete, allowing the source to be regenerated/reviewed.
        finished_title = result["task"].title or ""
        source_id = None
        if finished_title.startswith("Verification repair for task #") or finished_title.startswith("Fix review finding for task #"):
            try:
                source_id = int(finished_title.split("#", 1)[1].split(":", 1)[0].split(" ", 1)[0])
            except (ValueError, IndexError):
                source_id = None
        if source_id is not None and result["task"].status == "done":
            source_task = db.get(Task, source_id)
            if source_task and source_task.project_id == result["task"].project_id:
                if finished_title.startswith("Verification repair"):
                    source_task.status = "todo"
                    source_task.result = (source_task.result or "") + "\n[Repair] A repair task completed; source task queued for regeneration and verification."
                else:
                    pending_siblings = db.query(Task).filter(
                        Task.project_id == source_task.project_id,
                        Task.title.like(f"Fix review finding for task #{source_id}:%"),
                        Task.status != "done",
                    ).count()
                    if pending_siblings == 0:
                        source_task.status = "todo"
                        source_task.result = (source_task.result or "") + "\n[Review repair] All queued review fixes completed; source task queued for re-review."
                db.commit()
        # Every completed implementation task is reviewed before the workflow
        # considers it fully complete. Review is role-based and uses the QA role.
        if result["task"].status == "done":
            try:
                review, payload = review_task(db, task.id, "QA Engineer")
                if review.status == "changes_requested":
                    task = db.get(Task, task.id)
                    task.status = "blocked"
                    for finding in (payload.get("findings") or [])[:8]:
                        description = str(finding.get("recommendation") or finding.get("finding") or "").strip()
                        if not description:
                            continue
                        title = f"Fix review finding for task #{task.id}: {str(finding.get('finding', 'Issue'))[:140]}"
                        exists = db.query(Task).filter(Task.project_id == task.project_id, Task.title == title).first()
                        if not exists:
                            db.add(Task(project_id=task.project_id, agent_id=task.agent_id,
                                        title=title[:250], description=description[:5000],
                                        status="todo", priority="high", dependencies_json="[]"))
                    db.commit()
                    log(db, "team.task_blocked", f"Task #{task.id} requires changes after QA review; repair tasks queued", actor, "warning")
                else:
                    log(db, "team.task_reviewed", f"Task #{task.id}: QA approved", actor)
            except Exception as exc:
                log(db, "team.review_failed", f"Task #{task.id}: {type(exc).__name__}: {exc}"[:500], actor, "warning")
        for command in result.get("commands", []):
            from ..models import Approval
            db.add(Approval(
                action="execute_command",
                reason=f"{result['task'].title}: {command['reason']}",
                risk="high" if command.get("kind") == "install" else "medium",
                payload=json.dumps({
                    "command": command["command"],
                    "cwd": command["cwd"],
                    "source": "agent",
                    "task_id": task_id,
                    "kind": command.get("kind", "verify"),
                }),
            ))
        db.commit()
        return {"task_id": task_id, "status": result["task"].status}
    except Exception as exc:
        log(db, "team.task_failed", f"Task #{task_id}: {type(exc).__name__}: {exc}"[:500], actor, "error")
        return {"task_id": task_id, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if agent_id:
            try:
                _set_agent_status(db, agent_id, "idle")
            except Exception:
                pass
        db.close()


def _worker(project_id: int, actor: str):
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if not project:
            return
        project.status = "working"
        db.commit()
        log(db, "team.orchestrator_started", f"Project #{project_id} automatic team execution started", actor)

        # Run dependency waves until there is no work left. Independent tasks in
        # the same wave run concurrently so assigned specialists are not left idle.
        max_workers = 6
        while True:
            db.expire_all()
            project = db.get(Project, project_id)
            if not project:
                break
            if _project_done(db, project_id):
                project.status = "completed"
                db.commit()
                log(db, "team.project_completed", f"Project #{project_id} completed", actor)
                break

            ready = ready_tasks(db, project_id, limit=50)
            # Do not retry blocked tasks automatically; they require review or a
            # human decision. This avoids infinite loops.
            ready = [t for t in ready if t.status == "todo"]
            if not ready:
                if _has_blocked(db, project_id):
                    project.status = "blocked"
                    db.commit()
                    log(db, "team.project_blocked", f"Project #{project_id} is waiting on blocked tasks", actor, "warning")
                else:
                    project.status = "waiting"
                    db.commit()
                    log(db, "team.project_waiting", f"Project #{project_id} has no currently runnable tasks", actor, "warning")
                break

            log(db, "team.wave_started", f"Project #{project_id}: starting {len(ready)} ready specialist task(s)", actor)
            with ThreadPoolExecutor(max_workers=min(max_workers, len(ready))) as pool:
                futures = [pool.submit(_run_one, task.id, actor) for task in ready]
                for future in as_completed(futures):
                    future.result()
            time.sleep(0.2)
    finally:
        db.close()
        with _LOCK:
            _RUNNING.discard(project_id)


def launch_project(db: Session, project_id: int, actor: str = "system") -> bool:
    with _LOCK:
        if project_id in _RUNNING:
            return False
        _RUNNING.add(project_id)
    thread = threading.Thread(target=_worker, args=(project_id, actor), daemon=True, name=f"jarvis-project-{project_id}")
    thread.start()
    return True


def running_projects() -> list[int]:
    with _LOCK:
        return sorted(_RUNNING)
