from __future__ import annotations
import json, re
from sqlalchemy.orm import Session
from ..ai.providers import generate_reply
from ..models import Agent, Project, Task, TaskReview
from ..security.policies import safe_path
from .developer import _prefix, _snapshot, _source

def _json(text: str):
    text=text.strip()
    if text.startswith("```"):
        text=re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text=re.sub(r"\s*```$", "", text)
    a,b=text.find("{"),text.rfind("}")
    if a<0 or b<=a: raise ValueError("Reviewer did not return valid JSON")
    return json.loads(text[a:b+1])

def review_task(db: Session, task_id: int, reviewer_name: str = "QA Engineer"):
    task=db.get(Task, task_id)
    if not task: raise ValueError("Task not found")
    project=db.get(Project, task.project_id) if task.project_id else None
    reviewer=db.query(Agent).filter(Agent.name==reviewer_name).first() or db.query(Agent).filter(Agent.name=="QA Engineer").first()
    if not project or not reviewer: raise ValueError("Project or reviewer not found")
    prefix=_prefix(project)
    prompt=f'''You are reviewing completed work in a professional software development team.\nPROJECT: {project.name}\nTASK: {task.title}\nDESCRIPTION: {task.description}\nTASK RESULT: {task.result}\nWORKSPACE FILES:\n{_snapshot(prefix)}\nSOURCE:\n{_source(prefix)}\n\nReturn ONLY JSON:\n{{"status":"approved|changes_requested","summary":"...","findings":[{{"severity":"low|medium|high|critical","file":"relative path or none","finding":"...","recommendation":"..."}}],"follow_up_tasks":["..."]}}\nBe concrete. Do not claim to execute tests or commands.'''
    result=generate_reply(prompt, use_search=False, response_format="json")
    payload=_json(result["reply"])
    review=TaskReview(task_id=task.id, reviewer_agent_id=reviewer.id, status=payload.get("status","changes_requested"), summary=payload.get("summary","")[:5000], findings=json.dumps(payload.get("findings",[]), ensure_ascii=False))
    db.add(review)
    review_dir=safe_path(f"{prefix}/reviews"); review_dir.mkdir(parents=True, exist_ok=True)
    md=[f"# Review: {task.title}","",f"Reviewer: {reviewer.name}",f"Status: {review.status}","",review.summary,"","## Findings"]
    for f in payload.get("findings",[]):
        md.append(f"- **{f.get('severity','medium')}** `{f.get('file','')}` — {f.get('finding','')}\n  - Recommendation: {f.get('recommendation','')}")
    (review_dir/f"task-{task.id}.md").write_text("\n".join(md),encoding="utf-8")
    db.commit(); db.refresh(review)
    return review, payload
