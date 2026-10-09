import time
import threading
from collections import defaultdict, deque
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db, SessionLocal
from .models import User, Agent, Project, Task, Approval, AuditLog, ResearchReport, ChatMessage, AgentRun, TaskReview, Memory
from .schemas import *
from .security.auth import hash_password, verify_password, create_token, current_user
from .security.policies import safe_path, run_safe_command, validate_command
from .services.core import seed_agents, log, local_opportunity_report
from .services.team import build_team_plan, build_team_discovery, create_team_project
from .services.orchestrator import launch_project, running_projects
from .services.developer import run_task, ready_tasks
from .ai.providers import generate_reply, generate_research
from .ai.providers import provider_status
from .services.review import review_task
from .services.git import ensure_repo, status as git_status, commit as git_commit

# Lightweight per-process login throttle for this single-user local installation.
_LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_LOCK = threading.Lock()
_REGISTRATION_LOCK = threading.Lock()
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_ATTEMPTS = 10


def _check_login_rate_limit(key: str):
    now = time.monotonic()
    with _LOGIN_LOCK:
        attempts = _LOGIN_ATTEMPTS[key]
        while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            raise HTTPException(429, "Too many login attempts. Wait five minutes and try again.")
        attempts.append(now)


Base.metadata.create_all(bind=engine)
app = FastAPI(title=settings.app_name, version="10.0.0", docs_url="/docs" if settings.enable_docs else None, redoc_url="/redoc" if settings.enable_docs else None)
if settings.environment == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[x.strip() for x in settings.trusted_hosts.split(",") if x.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=()"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

frontend = Path(__file__).resolve().parents[2] / "dashboard"
if frontend.exists():
    app.mount("/dashboard", StaticFiles(directory=frontend), name="dashboard")


def serialize(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


@app.on_event("startup")
def startup():
    if settings.environment == "production":
        required = {"SECRET_KEY": settings.secret_key, "AGENT_PAIRING_TOKEN": settings.agent_pairing_token, "VOICE_API_TOKEN": settings.voice_api_token}
        bad = [k for k,v in required.items() if not v or "replace" in v.lower() or "generate-" in v.lower() or "change-this" in v.lower()]
        if bad:
            raise RuntimeError("Production configuration missing/unsafe: " + ", ".join(bad))
    db = SessionLocal()
    try:
        # Lightweight SQLite migration for the evolving v1 baseline.
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        task_cols = {c["name"] for c in inspector.get_columns("tasks")}
        if "dependencies_json" not in task_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN dependencies_json TEXT DEFAULT '[]'"))
        seed_agents(db)
    finally:
        db.close()


@app.get("/")
def root():
    return FileResponse(frontend / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "JARVIS V10", "version": "10.0.0", "stage": "V10 Ollama-Only Secure Orchestration", "desktop_control": settings.desktop_control_enabled, "ai_provider": settings.ai_provider, "providers": provider_status()}


@app.post("/api/auth/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    # Serialize registrations within the single-process local server.
    with _REGISTRATION_LOCK:
        if db.query(User).count() > 0:
            raise HTTPException(403, "Registration is closed. Ask the JARVIS owner to create an account.")
        if db.scalar(select(User).where(User.email == body.email)):
            raise HTTPException(409, "Email already registered")
        user = User(email=body.email, password_hash=hash_password(body.password))
        db.add(user); db.commit(); db.refresh(user)
        log(db, "user.registered", user.email, user.email)
        return {"access_token": create_token(user.id), "token_type": "bearer"}


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(f"{ip}:{body.email.strip().lower()}")
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(f"{ip}:{body.email.strip().lower()}", None)
    return {"access_token": create_token(user.id), "token_type": "bearer"}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {"id": user.id, "email": user.email}


@app.get("/api/overview")
def overview(db: Session = Depends(get_db), user=Depends(current_user)):
    return {
        "projects": db.query(Project).count(),
        "tasks": db.query(Task).count(),
        "pending_approvals": db.query(Approval).filter_by(status="pending").count(),
        "agents": db.query(Agent).count(),
        "chat_messages": db.query(ChatMessage).filter_by(user_id=user.id).count(),
        "recent_activity": [serialize(x) for x in db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(8).all()],
    }


@app.get("/api/ai/providers")
def ai_providers(user=Depends(current_user)):
    return {"selected": settings.ai_provider, "auto_order": settings.ai_auto_order, "providers": provider_status()}


@app.get("/api/ai/config")
def ai_config(user=Depends(current_user)):
    return {"selected": settings.ai_provider, "auto_order": settings.ai_auto_order, "ollama_enabled": settings.ollama_enabled}


@app.get("/api/agents")
def agents(db: Session = Depends(get_db), user=Depends(current_user)):
    return [serialize(x) for x in db.query(Agent).all()]


@app.get("/api/projects")
def projects(db: Session = Depends(get_db), user=Depends(current_user)):
    return [serialize(x) for x in db.query(Project).order_by(desc(Project.created_at)).all()]


@app.post("/api/projects")
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user=Depends(current_user)):
    item = Project(name=body.name, description=body.description)
    db.add(item); db.commit(); db.refresh(item)
    log(db, "project.created", body.name, user.email)
    return serialize(item)


@app.get("/api/tasks")
def tasks(db: Session = Depends(get_db), user=Depends(current_user)):
    return [serialize(x) for x in db.query(Task).order_by(desc(Task.id)).all()]


@app.post("/api/tasks")
def create_task(body: TaskCreate, db: Session = Depends(get_db), user=Depends(current_user)):
    data = body.model_dump(); data["dependencies_json"] = json.dumps(data.pop("dependencies", [])); item = Task(**data)
    db.add(item); db.commit(); db.refresh(item)
    log(db, "task.created", body.title, user.email)
    return serialize(item)


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, status: str = Query(...), db: Session = Depends(get_db), user=Depends(current_user)):
    if status not in {"todo", "in_progress", "awaiting_verification", "blocked", "done"}:
        raise HTTPException(400, "Invalid task status")
    item = db.get(Task, task_id)
    if not item:
        raise HTTPException(404, "Task not found")
    item.status = status; db.commit()
    log(db, "task.updated", f"{task_id} -> {status}", user.email)
    return serialize(item)


@app.get("/api/approvals")
def approvals(db: Session = Depends(get_db), user=Depends(current_user)):
    return [serialize(x) for x in db.query(Approval).order_by(desc(Approval.created_at)).all()]


@app.post("/api/approvals")
def create_approval(body: ApprovalCreate, db: Session = Depends(get_db), user=Depends(current_user)):
    item = Approval(action=body.action, reason=body.reason, risk=body.risk, payload=json.dumps(body.payload))
    db.add(item); db.commit(); db.refresh(item)
    log(db, "approval.requested", body.action, user.email, "warning")
    return serialize(item)


@app.post("/api/approvals/{approval_id}/decision")
def decision(approval_id: int, body: DecisionRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    if body.decision not in {"approved", "rejected"}:
        raise HTTPException(400, "Decision must be approved or rejected")
    item = db.get(Approval, approval_id)
    if not item:
        raise HTTPException(404, "Approval not found")
    item.status = body.decision
    item.decided_at = datetime.now(timezone.utc)
    db.commit()
    log(db, "approval.decided", f"{approval_id}: {body.decision}", user.email)
    return serialize(item)


@app.post("/api/approvals/{approval_id}/execute")
def execute_approved(approval_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    item = db.get(Approval, approval_id)
    if not item:
        raise HTTPException(404, "Approval not found")
    if item.status != "approved":
        raise HTTPException(409, "Approval must be approved before execution")
    if item.action != "execute_command":
        raise HTTPException(400, "This approval type cannot be executed by this endpoint")

    payload = json.loads(item.payload or "{}")
    command = payload.get("command", "")
    cwd = payload.get("cwd", ".")
    # Claim the approval before running it so double-clicks/retries cannot run
    # the same command twice.
    item.status = "executing"
    db.commit()
    try:
        result = run_safe_command(command, cwd)
    except Exception as exc:
        item.status = "failed"
        item.decided_at = datetime.now(timezone.utc)
        db.commit()
        log(db, "command.failed", f"Approval #{approval_id}: {type(exc).__name__}: {exc}", user.email, "error")
        raise HTTPException(400, str(exc))

    item.status = "executed"
    item.decided_at = datetime.now(timezone.utc)
    task_id = payload.get("task_id")
    project_to_resume = None
    if task_id:
        task = db.get(Task, int(task_id))
        if task and payload.get("kind") == "test":
            passed = result.get("return_code") == 0
            task.status = "done" if passed else "blocked"
            task.result = (task.result or "") + "\nVerification: " + ("PASSED" if passed else "FAILED")
            task.result += "\\nExit code: " + str(result.get("return_code"))
            task.result += "\\nSTDOUT:\\n" + str(result.get("stdout", ""))[-5000:]
            task.result += "\\nSTDERR:\\n" + str(result.get("stderr", ""))[-5000:]
            project_to_resume = task.project_id
            if not passed:
                repairs = db.query(Task).filter(
                    Task.project_id == task.project_id,
                    Task.title.like(f"Verification repair for task #{task.id}%")
                ).count()
                if repairs < 3:
                    agent = db.get(Agent, task.agent_id) if task.agent_id else None
                    db.add(Task(
                        project_id=task.project_id,
                        agent_id=agent.id if agent else None,
                        title=f"Verification repair for task #{task.id} (attempt {repairs + 1})",
                        description=(
                            "Fix the code associated with task #" + str(task.id) +
                            " based on this failed approved test. Do not claim the test passed.\\n\\n"
                            "Exit code: " + str(result.get("return_code")) +
                            "\\nSTDOUT:\\n" + str(result.get("stdout", ""))[-5000:] +
                            "\\nSTDERR:\\n" + str(result.get("stderr", ""))[-5000:]
                        ),
                        status="todo",
                        priority="high",
                        dependencies_json="[]",
                    ))
                    log(db, "team.verification_failed",
                        f"Task #{task.id} failed verification; repair attempt {repairs + 1} queued",
                        user.email, "warning")
    log(db, "command.executed", f"Approval #{approval_id}: {command}", user.email)
    db.commit()

    # Test completion may unblock dependent tasks; a failed test may have queued
    # a repair task. Resume the project's dependency-aware worker in either case.
    if project_to_resume is not None:
        launch_project(db, project_to_resume, user.email)
    return result


@app.get("/api/activity")
def activity(db: Session = Depends(get_db), user=Depends(current_user)):
    return [serialize(x) for x in db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(100).all()]

@app.get("/api/live")
def live_state(db: Session = Depends(get_db), user=Depends(current_user)):
    """Single near-real-time dashboard snapshot used by every dashboard view."""
    projects = db.query(Project).order_by(desc(Project.created_at)).limit(50).all()
    tasks = db.query(Task).order_by(desc(Task.id)).limit(200).all()
    agents = db.query(Agent).all()
    approvals = db.query(Approval).filter_by(status="pending").order_by(desc(Approval.created_at)).limit(50).all()
    activity_rows = db.query(AuditLog).order_by(desc(AuditLog.id)).limit(20).all()
    return {
        "server_time": datetime.now(timezone.utc).isoformat(),
        "running_projects": running_projects(),
        "projects": [serialize(x) for x in projects],
        "tasks": [serialize(x) for x in tasks],
        "agents": [serialize(x) for x in agents],
        "approvals": [serialize(x) for x in approvals],
        "activity": [serialize(x) for x in activity_rows],
        "chat_messages": db.query(ChatMessage).filter_by(user_id=user.id).count(),
    }


@app.get("/api/events")
def events(after_id: int = 0, db: Session = Depends(get_db), user=Depends(current_user)):
    """Lightweight server-sent event stream for dashboards that support SSE.
    It watches the audit log; clients can also use /api/live polling as a fallback.
    """
    def stream():
        last = after_id
        for _ in range(30):
            rows = db.query(AuditLog).filter(AuditLog.id > last).order_by(AuditLog.id.asc()).limit(100).all()
            if rows:
                for row in rows:
                    last = row.id
                    payload = json.dumps(serialize(row), default=str)
                    yield f"id: {row.id}\ndata: {payload}\n\n"
            else:
                yield ": heartbeat\n\n"
            import time; time.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no"})


@app.get("/api/memory")
def memory_list(db: Session = Depends(get_db), user=Depends(current_user)):
    rows = db.query(Memory).filter_by(profile=f"user:{user.id}", enabled=True).order_by(desc(Memory.id)).limit(100).all()
    return [serialize(x) for x in rows]


class MemoryRequest(BaseModel):
    content: str
    kind: str = "note"


@app.post("/api/memory")
def memory_create(body: MemoryRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Memory content is empty")
    item = Memory(profile=f"user:{user.id}", kind=body.kind[:40], content=content)
    db.add(item); db.commit(); db.refresh(item)
    log(db, "memory.created", content[:300], user.email)
    return serialize(item)


@app.delete("/api/memory/{memory_id}")
def memory_delete(memory_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    item = db.get(Memory, memory_id)
    if not item or item.profile != f"user:{user.id}":
        raise HTTPException(404, "Memory not found")
    item.enabled = False; db.commit()
    log(db, "memory.disabled", str(memory_id), user.email)
    return {"ok": True}


@app.get("/api/chat/history")
def chat_history(db: Session = Depends(get_db), user=Depends(current_user)):
    rows = db.query(ChatMessage).filter_by(user_id=user.id).order_by(ChatMessage.id).limit(100).all()
    return [serialize(x) for x in rows]


@app.post("/api/chat")
def chat(body: ChatRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    message = body.message.strip()
    db.add(ChatMessage(user_id=user.id, role="user", content=message)); db.commit()
    previous = db.query(ChatMessage).filter_by(user_id=user.id).order_by(desc(ChatMessage.id)).limit(10).all()
    history_context = "\\n".join(f"{x.role.upper()}: {x.content}" for x in reversed(previous))
    memories = db.query(Memory).filter_by(profile=f"user:{user.id}", enabled=True).order_by(desc(Memory.id)).limit(20).all()
    memory_context = "\\n".join(f"MEMORY: {m.content}" for m in reversed(memories))
    context = "\\n\\n".join(part for part in (history_context, memory_context) if part)
    try:
        result = generate_reply(message, context=context, use_search=body.use_search, provider=body.provider)
    except RuntimeError as exc:
        log(db, "ai.error", str(exc)[:500], user.email, "error")
        raise HTTPException(502, str(exc))
    except Exception as exc:
        log(db, "ai.error", f"{type(exc).__name__}: {exc}"[:500], user.email, "error")
        raise HTTPException(502, f"AI provider error: {type(exc).__name__}: {exc}")
    db.add(ChatMessage(user_id=user.id, role="assistant", content=result["reply"])); db.commit()
    log(db, "ai.chat", message[:300], user.email)
    return result


class VoiceChatRequest(BaseModel):
    token: str
    message: str
    provider: str | None = None
    use_search: bool = False


@app.post("/api/voice/chat")
def voice_chat(body: VoiceChatRequest, db: Session = Depends(get_db)):
    """Token-protected remote voice bridge with shared dashboard persistence."""
    if not settings.voice_api_token or body.token != settings.voice_api_token:
        raise HTTPException(401, "Invalid voice token")
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Voice message is empty")

    # V9 is normally a single-user local system. For multi-user deployments set
    # VOICE_USER_EMAIL so remote voice messages are attached to the right account.
    voice_user = None
    if settings.voice_user_email:
        voice_user = db.scalar(select(User).where(User.email == settings.voice_user_email))
    if voice_user is None:
        users = db.query(User).order_by(User.id.asc()).limit(2).all()
        if len(users) == 1:
            voice_user = users[0]

    user_id = voice_user.id if voice_user else None
    previous = []
    if user_id:
        previous = db.query(ChatMessage).filter_by(user_id=user_id).order_by(desc(ChatMessage.id)).limit(10).all()
    voice_memories = db.query(Memory).filter_by(profile="voice", enabled=True).order_by(desc(Memory.id)).limit(20).all()
    user_memories = []
    if user_id:
        user_memories = db.query(Memory).filter_by(profile=f"user:{user_id}", enabled=True).order_by(desc(Memory.id)).limit(20).all()
    memory_rows = list(reversed(voice_memories + user_memories))
    memory_context = "\n".join(f"MEMORY: {m.content}" for m in memory_rows[-40:])
    history_context = "\n".join(f"{x.role.upper()}: {x.content}" for x in reversed(previous))
    context = "\n\n".join(x for x in [history_context, memory_context] if x)

    if user_id:
        db.add(ChatMessage(user_id=user_id, role="user", content=message))
        db.commit()
    log(db, "voice.command", message[:300], voice_user.email if voice_user else "voice", "info")

    # Explicit memory requests are persisted to the normal dashboard memory as
    # well as the legacy voice profile so both interfaces see the same memory.
    lower = message.lower()
    memory_intent = lower.startswith(("remember ", "remember that ", "don't forget ", "do not forget ", "my preference is ", "i prefer "))
    if memory_intent:
        content = message
        if user_id:
            db.add(Memory(profile=f"user:{user_id}", kind="voice", content=content, enabled=True))
        db.add(Memory(profile="voice", kind="voice", content=content, enabled=True))
        db.commit()
        log(db, "memory.created", content[:300], voice_user.email if voice_user else "voice")

    try:
        result = generate_reply(message, context=context, use_search=body.use_search, provider=body.provider)
    except RuntimeError as exc:
        log(db, "voice.error", str(exc)[:500], voice_user.email if voice_user else "voice", "error")
        raise HTTPException(502, str(exc))
    except Exception as exc:
        log(db, "voice.error", f"{type(exc).__name__}: {exc}"[:500], voice_user.email if voice_user else "voice", "error")
        raise HTTPException(502, f"AI provider error: {type(exc).__name__}: {exc}")

    if user_id:
        db.add(ChatMessage(user_id=user_id, role="assistant", content=result["reply"]))
        db.commit()
    log(db, "ai.voice_chat", message[:300], voice_user.email if voice_user else "voice")
    return result


@app.get("/api/voice/status")
def voice_status(token: str, db: Session = Depends(get_db)):
    if not settings.voice_api_token or token != settings.voice_api_token:
        raise HTTPException(401, "Invalid voice token")
    return {
        "server_time": datetime.now(timezone.utc).isoformat(),
        "running_projects": running_projects(),
        "projects": [serialize(x) for x in db.query(Project).order_by(desc(Project.created_at)).limit(20).all()],
        "tasks": [serialize(x) for x in db.query(Task).order_by(desc(Task.id)).limit(100).all()],
        "agents": [serialize(x) for x in db.query(Agent).all()],
        "activity": [serialize(x) for x in db.query(AuditLog).order_by(desc(AuditLog.id)).limit(20).all()],
    }


@app.post("/api/team/build")
def build_software_team(body: TeamBuildRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    """Discovery -> planning -> team assembly -> automatic execution."""
    try:
        discovery = build_team_discovery(body.idea, body.constraints)
        log(db, "project.discovery_completed", discovery[:500], user.email)
        plan = build_team_plan(body.idea, body.constraints, discovery)
    except Exception as exc:
        log(db, "team.plan_failed", f"{type(exc).__name__}: {exc}"[:500], user.email, "error")
        raise HTTPException(502, f"Project discovery/planning failed: {type(exc).__name__}: {exc}")

    if not body.create_project:
        return {"discovery": discovery, "plan": plan, "project": None, "tasks": []}

    try:
        project, tasks = create_team_project(db, plan)
        project.status = "assembled"
        db.commit()
        db.refresh(project)
        db.add(ResearchReport(industry="software-project-discovery", audience=project.name, region="Local", report=discovery, grounded=False))
        db.commit()
        log(db, "team.project_created", f"{project.name}: {len(tasks)} tasks assigned; automatic execution queued", user.email)
        launch_project(db, project.id, user.email)
        return {
            "project": serialize(project),
            "tasks": [serialize(x) for x in tasks],
            "plan": plan,
            "discovery": discovery,
            "orchestration_started": True,
        }
    except Exception as exc:
        db.rollback()
        log(db, "team.project_failed", f"{type(exc).__name__}: {exc}"[:500], user.email, "error")
        raise HTTPException(500, f"Team project creation failed: {type(exc).__name__}: {exc}")


@app.post("/api/team/run-task/{task_id}")
def run_team_task(task_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    try:
        result=run_task(db, task_id)
        log(db, "team.task_completed", f"Task #{task_id}: {result['summary'][:300]}", user.email)
        for command in result.get("commands", []):
            db.add(Approval(action="execute_command", reason=f"{result['task'].title}: {command['reason']}", risk="medium", payload=json.dumps({"command":command["command"],"cwd":command["cwd"],"source":"agent","task_id":task_id,"kind":command.get("kind","verify")})))
        db.commit()
        return {"project":serialize(result["project"]),"task":serialize(result["task"]),"run":serialize(result["run"]),"files":result["files"],"commands":result["commands"]}
    except Exception as exc:
        log(db, "team.task_failed", f"Task #{task_id}: {type(exc).__name__}: {exc}"[:500], user.email, "error")
        raise HTTPException(502, f"Agent task failed: {type(exc).__name__}: {exc}")

@app.post("/api/team/run-ready")
def run_ready_team_tasks(body: TeamRunRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    results=[]
    for task in ready_tasks(db, body.project_id, body.max_tasks):
        try:
            result=run_task(db, task.id)
            for command in result.get("commands", []):
                db.add(Approval(action="execute_command", reason=f"{result['task'].title}: {command['reason']}", risk="medium", payload=json.dumps({"command":command["command"],"cwd":command["cwd"],"source":"agent","task_id":task.id,"kind":command.get("kind","verify")})))
            results.append({"task":serialize(result["task"]),"files":result["files"],"summary":result["summary"]})
        except Exception as exc:
            results.append({"task_id":task.id,"error":f"{type(exc).__name__}: {exc}"})
    db.commit(); log(db, "team.batch_run", f"Ran {len(results)} software-team task(s)", user.email)
    return {"project_id":body.project_id,"results":results}

@app.post("/api/team/advance")
def advance_team(body: TeamAdvanceRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    results=[]
    for task in ready_tasks(db, body.project_id, body.max_tasks):
        try:
            result=run_task(db, task.id)
            auto_review=None
            if result["task"].status == "done" and result["task"].title and result["task"].agent_id:
                try:
                    review_obj, review_payload = review_task(db, task.id, "QA Engineer")
                    auto_review={"status":review_obj.status,"summary":review_obj.summary}
                    if review_obj.status == "changes_requested":
                        task.status="blocked"
                        db.commit()
                except Exception as review_exc:
                    auto_review={"status":"review_failed","error":f"{type(review_exc).__name__}: {review_exc}"}
            for command in result.get("commands", []):
                db.add(Approval(action="execute_command", reason=f"{result['task'].title}: {command['reason']}", risk="high" if command.get("kind") == "install" else "medium", payload=json.dumps({"command":command["command"],"cwd":command["cwd"],"source":"agent","task_id":task.id,"kind":command.get("kind","verify")})))
            results.append({"task":serialize(result["task"]),"files":result["files"],"summary":result["summary"],"commands":result["commands"],"review":auto_review})
        except Exception as exc:
            results.append({"task_id":task.id,"error":f"{type(exc).__name__}: {exc}"})
    db.commit(); log(db,"team.advance",f"Advanced {len(results)} ready task(s)",user.email)
    return {"project_id":body.project_id,"results":results}


@app.post("/api/team/review/{task_id}")
def review_team_task(task_id: int, body: TeamReviewRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    try:
        review, payload = review_task(db, task_id, body.reviewer_agent)
        reviewed_task = db.get(Task, task_id)
        if reviewed_task and review.status == "approved":
            reviewed_task.status = "done"
        if reviewed_task and review.status == "changes_requested":
            reviewed_task.status = "blocked"
            for finding in (payload.get("findings") or [])[:8]:
                description = str(finding.get("recommendation") or finding.get("finding") or "").strip()
                if not description:
                    continue
                title = f"Fix review finding for task #{task_id}: {str(finding.get('finding', 'Issue'))[:140]}"
                exists = db.query(Task).filter(Task.project_id == reviewed_task.project_id, Task.title == title).first()
                if not exists:
                    db.add(Task(project_id=reviewed_task.project_id, agent_id=reviewed_task.agent_id,
                                title=title[:250], description=description[:5000],
                                status="todo", priority="high",
                                dependencies_json="[]"))
            db.commit()
        log(db, "team.task_reviewed", f"Task #{task_id}: {review.status}", user.email)
        return {"review":serialize(review), "result":payload}
    except Exception as exc:
        log(db,"team.review_failed",f"Task #{task_id}: {type(exc).__name__}: {exc}",user.email,"error")
        raise HTTPException(502,f"Task review failed: {type(exc).__name__}: {exc}")


@app.get("/api/team/reviews")
def team_reviews(task_id: int|None=None, db: Session=Depends(get_db), user=Depends(current_user)):
    q=db.query(TaskReview).order_by(desc(TaskReview.id))
    if task_id is not None: q=q.filter(TaskReview.task_id==task_id)
    return [serialize(x) for x in q.limit(100).all()]


def _project_prefix(project: Project) -> str:
    slug=re.sub(r"[^a-zA-Z0-9_-]+","-",project.name.lower()).strip("-")[:80] or "project"
    return f"projects/{project.id}-{slug}"


@app.post("/api/team/git/init/{project_id}")
def team_git_init(project_id:int, db:Session=Depends(get_db), user=Depends(current_user)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    try:
        prefix=_project_prefix(project); ensure_repo(prefix); result=git_status(prefix)
        log(db,"git.initialized",f"Project #{project.id}",user.email); return result
    except Exception as exc:
        raise HTTPException(400,str(exc))


@app.get("/api/team/git/status/{project_id}")
def team_git_status(project_id:int, db:Session=Depends(get_db), user=Depends(current_user)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    try: return git_status(_project_prefix(project))
    except Exception as exc: raise HTTPException(400,str(exc))


@app.post("/api/team/git/commit/{project_id}")
def team_git_commit(project_id:int, message:str="JARVIS checkpoint", db:Session=Depends(get_db), user=Depends(current_user)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    try:
        result=git_commit(_project_prefix(project),message)
        log(db,"git.commit",f"Project #{project.id}: {message[:120]}",user.email)
        return result
    except Exception as exc: raise HTTPException(400,str(exc))


@app.get("/api/team/runs")
def team_runs(project_id: int|None=None, db: Session=Depends(get_db), user=Depends(current_user)):
    q=db.query(AgentRun).order_by(desc(AgentRun.id))
    return [serialize(x) for x in q.limit(100).all()]

@app.get("/api/team/status")
def team_status(project_id: int | None = None, db: Session = Depends(get_db), user=Depends(current_user)):
    q = db.query(Task)
    if project_id is not None:
        q = q.filter(Task.project_id == project_id)
    tasks = q.all()
    agents = db.query(Agent).all()
    task_by_agent = {}
    for t in tasks:
        if t.agent_id:
            task_by_agent.setdefault(t.agent_id, []).append(t)
    agent_payload = []
    for a in agents:
        rows = task_by_agent.get(a.id, [])
        agent_payload.append({**serialize(a), "task_count": len(rows), "active_tasks": [t.id for t in rows if t.status == "in_progress"]})
    return {
        "agents": agent_payload,
        "tasks": [serialize(t) for t in tasks],
        "running_projects": running_projects(),
        "counts": {
            "total": len(tasks),
            "todo": sum(t.status == "todo" for t in tasks),
            "in_progress": sum(t.status == "in_progress" for t in tasks),
            "blocked": sum(t.status == "blocked" for t in tasks),
            "done": sum(t.status == "done" for t in tasks),
        },
    }


@app.post("/api/plan")
def plan(body: PlanRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    prompt = f"""
Create a software-development execution plan for this idea:
{body.idea}

Return sections:
- Product goal
- Target users
- MVP scope
- User stories
- Architecture
- Data model
- API/modules
- UI screens
- Security requirements
- Testing strategy
- Deployment strategy
- Ordered implementation tasks, each mapped to one of these agents:
  Research Agent, Product Manager, Software Architect, UI/UX Agent,
  Frontend Developer, Backend Developer, QA Engineer, Security Reviewer,
  DevOps Agent, Documentation Agent.
""".strip()
    try:
        result = generate_reply(prompt, use_search=True)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    if body.create_project:
        project = Project(name=body.idea[:190], description="AI-generated development plan")
        db.add(project); db.commit(); db.refresh(project)
        log(db, "project.planned", body.idea[:300], user.email)
        return {"project": serialize(project), "plan": result["reply"]}
    return {"plan": result["reply"]}


@app.post("/api/research")
def research(body: ResearchRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    try:
        report = generate_research(body.industry, body.audience, body.region, provider=body.provider) if body.live else None
    except Exception as exc:
        report = None
        log(db, "research.local_model_error", type(exc).__name__, user.email, "warning")
    if report is None:
        local = local_opportunity_report(body.industry, body.audience, body.region)
        text = json.dumps(local, indent=2)
        grounded = False
    else:
        text = report["summary"]; grounded = report["grounded"]
    item = ResearchReport(industry=body.industry, audience=body.audience, region=body.region, report=text, grounded=grounded)
    db.add(item); db.commit(); db.refresh(item)
    log(db, "research.created", f"{body.industry}/{body.audience}", user.email)
    return {"id": item.id, "report": text, "grounded": grounded}


@app.get("/api/research")
def research_list(db: Session = Depends(get_db), user=Depends(current_user)):
    return [serialize(x) for x in db.query(ResearchReport).order_by(desc(ResearchReport.created_at)).all()]


@app.get("/api/workspace/files")
def workspace_files(db: Session = Depends(get_db), user=Depends(current_user)):
    root = Path(settings.workspace_path).resolve(); output = []
    for p in root.rglob("*"):
        if p.is_file() and len(output) < 500:
            output.append({"path": str(p.relative_to(root)), "size": p.stat().st_size})
    return output


@app.get("/api/workspace/file")
def workspace_file(path: str, user=Depends(current_user)):
    try:
        p = safe_path(path)
    except ValueError as e:
        raise HTTPException(403, str(e))
    if not p.is_file():
        raise HTTPException(404, "File not found")
    if p.stat().st_size > 1_000_000:
        raise HTTPException(413, "File too large")
    return {"path": path, "content": p.read_text(encoding="utf-8", errors="replace")}


DESKTOP_SAFE_ACTIONS = {
    "launch_app": {"risk": "low", "approval": False},
    "open_workspace": {"risk": "low", "approval": False},
    "open_file": {"risk": "low", "approval": False},
    "open_url": {"risk": "medium", "approval": True},
    "system_info": {"risk": "low", "approval": False},
    "capture_screen": {"risk": "high", "approval": True},
}


def _desktop_approval_payload(action: str, args: dict, request_id: int | None = None):
    payload = {"action": action, "args": args, "source": "desktop-control", "agent_id": settings.agent_id}
    if request_id is not None:
        payload["request_id"] = request_id
    return payload


@app.get("/api/desktop/status")
def desktop_status(user=Depends(current_user)):
    return {"enabled": settings.desktop_control_enabled, "agent_id": settings.agent_id, "actions": sorted(DESKTOP_SAFE_ACTIONS.keys())}


@app.post("/api/desktop/action")
def desktop_action(body: DesktopActionRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    if not settings.desktop_control_enabled:
        raise HTTPException(503, "Desktop control is disabled")
    spec = DESKTOP_SAFE_ACTIONS.get(body.action)
    if not spec:
        raise HTTPException(400, f"Desktop action is not allowlisted: {body.action}")
    # Strictly validate arguments before they ever reach the laptop agent.
    if body.action == "launch_app":
        app_name = str(body.args.get("app", "")).lower()
        if app_name not in {"vscode", "explorer", "notepad", "calculator"}:
            raise HTTPException(400, "Allowed apps: vscode, explorer, notepad, calculator")
    elif body.action == "open_workspace":
        path = str(body.args.get("path", ""))
        if not path or ".." in Path(path).parts or path.startswith(("/", "\\")):
            raise HTTPException(400, "Workspace path must be relative")
    elif body.action == "open_file":
        path = str(body.args.get("path", ""))
        if not path or ".." in Path(path).parts or path.startswith(("/", "\\")):
            raise HTTPException(400, "File path must be relative to workspace")
    elif body.action == "open_url":
        url = str(body.args.get("url", ""))
        if not re.match(r"^https://", url, re.I):
            raise HTTPException(400, "Only HTTPS URLs are allowed")
    elif body.action == "system_info":
        pass
    elif body.action == "capture_screen":
        pass
    approval = Approval(
        action="desktop_action",
        reason=body.reason,
        risk=spec["risk"],
        payload=json.dumps(_desktop_approval_payload(body.action, body.args)),
        status="pending" if spec["approval"] else "approved",
    )
    db.add(approval); db.commit(); db.refresh(approval)
    log(db, "desktop.action_requested", f"{body.action} #{approval.id}", user.email, "warning" if spec["approval"] else "info")
    return {"id": approval.id, "action": body.action, "status": approval.status, "requires_approval": spec["approval"]}


def _agent_token_ok(token: str | None):
    return bool(settings.agent_pairing_token and token and token == settings.agent_pairing_token)


@app.post("/api/desktop/emergency-stop")
def desktop_emergency_stop(db: Session = Depends(get_db), user=Depends(current_user)):
    rows = db.query(Approval).filter(Approval.action == "desktop_action", Approval.status.in_(["pending", "approved", "executing"])).all()
    for row in rows:
        row.status = "rejected"
    db.commit()
    log(db, "desktop.emergency_stop", f"Cancelled {len(rows)} desktop action(s)", user.email, "warning")
    return {"ok": True, "cancelled": len(rows)}


@app.get("/api/laptop/actions/pending")
def laptop_actions_pending(agent_id: str = Query(...), x_agent_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not _agent_token_ok(x_agent_token):
        raise HTTPException(401, "Invalid agent token")
    if agent_id != settings.agent_id:
        raise HTTPException(403, "Unknown agent")
    rows = db.query(Approval).filter(Approval.action == "desktop_action", Approval.status == "approved").order_by(Approval.id).limit(10).all()
    output=[]
    for row in rows:
        row.status = "executing"
        payload=json.loads(row.payload or "{}")
        output.append({"id":row.id,"action":payload.get("action"),"args":payload.get("args",{}),"created_at":row.created_at.isoformat() if row.created_at else None})
    db.commit()
    return output


@app.post("/api/laptop/actions/{approval_id}/result")
def laptop_action_result(approval_id: int, body: AgentActionResult, x_agent_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not _agent_token_ok(x_agent_token):
        raise HTTPException(401, "Invalid agent token")
    row=db.get(Approval, approval_id)
    if not row or row.action != "desktop_action":
        raise HTTPException(404, "Desktop action not found")
    # The poll endpoint claims the action by transitioning approved -> executing.
    if row.status != "executing":
        raise HTTPException(409, f"Action result is not expected while status is '{row.status}'")
    row.status = "executed" if body.status == "ok" else "failed"
    payload=json.loads(row.payload or "{}")
    payload["result"]={"status":body.status,"output":body.output[:10000],"error":body.error[:5000]}
    row.payload=json.dumps(payload)
    db.commit()
    return {"ok":True,"approval_id":approval_id,"status":row.status}


@app.post("/api/laptop/command")
def laptop_command(command: str, cwd: str = ".", db: Session = Depends(get_db), user=Depends(current_user)):
    valid, message = validate_command(command)
    if not valid:
        raise HTTPException(400, message)
    approval = Approval(action="execute_command", reason=f"Requested command: {command}", risk="high", payload=json.dumps({"command": command, "cwd": cwd}))
    db.add(approval); db.commit(); db.refresh(approval)
    log(db, "approval.requested", f"Laptop command: {command}", user.email, "warning")
    return {"message": "Command requires approval", "approval_id": approval.id, "validation": message}


@app.post("/api/laptop/pair")
def laptop_pair(body: PairRequest):
    if not settings.agent_pairing_token or body.token != settings.agent_pairing_token:
        raise HTTPException(401, "Invalid pairing token")
    return {"paired": True, "agent_id": settings.agent_id}


@app.post("/api/laptop/heartbeat")
def laptop_heartbeat(body: AgentHeartbeat):
    if not settings.agent_pairing_token:
        raise HTTPException(503, "Agent pairing is not configured")
    return {"ok": True, "agent_id": body.agent_id, "server_version": app.version}
