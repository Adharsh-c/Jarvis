import json
import re
from sqlalchemy.orm import Session
from ..models import Agent, Project, Task
from ..ai.providers import generate_reply

TEAM_ROLES = [
    "Research Agent", "Product Manager", "Software Architect", "UI/UX Agent",
    "Frontend Developer", "Backend Developer", "QA Engineer", "Security Reviewer",
    "DevOps Agent", "Documentation Agent"
]

def _json_from_text(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end+1])
    raise ValueError("Team planner did not return valid JSON")

def build_team_discovery(idea: str, constraints: str = ""):
    prompt = f"""You are the JARVIS Discovery Agent. Before software implementation begins, deeply analyze the user's project request.

PROJECT IDEA:
{idea}

CONSTRAINTS:
{constraints or 'None specified'}

Produce a practical discovery brief covering:
Important evidence rules: do not invent interviews, survey results, customer quotes, statistics, competitor facts, citations, or source URLs. With no live web/research tool, label uncertain claims as assumptions/hypotheses and produce a concrete validation plan.
1. Problem and intended outcome
2. Target users and primary workflows
3. Functional requirements
4. Non-functional requirements
5. Technical assumptions and unknowns
6. Data, integrations and security considerations
7. MVP boundary and later-phase candidates
8. Validation/research questions
9. Risks and dependencies
10. Definition of done

This is local-model analysis. Do not claim live web research or verified current market facts. Return clear structured text."""
    return generate_reply(prompt, use_search=False)["reply"]


def build_team_plan(idea: str, constraints: str = "", discovery: str = ""):
    prompt = f"""You are JARVIS Command Agent managing a professional software development team.
Create an actionable development plan using the discovery brief below.

PROJECT IDEA:
{idea}

CONSTRAINTS:
{constraints or 'None specified'}

DISCOVERY BRIEF:
{discovery or 'No separate discovery brief was available.'}

Use these team roles: {', '.join(TEAM_ROLES)}. Every listed role MUST receive at least one concrete task. Do not leave a role idle.
Build a dependency graph with clear phases: discovery/research -> product/architecture -> UI/frontend/backend -> QA/security -> DevOps/documentation. Independent tasks in the same phase should be runnable in parallel.
Research Agent must own evidence/validation artifacts. Product Manager must own requirements/acceptance criteria. Software Architect must own architecture. UI/UX must own user flows/design artifacts. Frontend and Backend must own implementation. QA must own tests and verification. Security must own a defensive security review. DevOps must own reproducible environment/CI artifacts. Documentation must own setup/API documentation.

Return ONLY valid JSON with this exact shape:
{{
  "project_name": "short name",
  "summary": "one paragraph",
  "milestones": [{{"name":"...","goal":"..."}}],
  "tasks": [
    {{"title":"...","description":"specific deliverable", "agent":"one exact team role", "priority":"low|medium|high|critical", "depends_on": []}}
  ]
}}
Create 12-24 tasks. Keep dependencies as task titles. Do not include markdown."""
    result = generate_reply(prompt, use_search=False, response_format="json")
    return _json_from_text(result["reply"])

def create_team_project(db: Session, plan: dict):
    project = Project(name=plan.get("project_name", "JARVIS Project")[:200], description=plan.get("summary", "AI-managed software project"), status="planning")
    db.add(project); db.flush()
    agents = {a.name: a for a in db.query(Agent).all()}
    created = []
    by_title = {}
    plan_tasks = list(plan.get("tasks", []) or [])
    assigned_roles = {str(item.get("agent", "")).strip() for item in plan_tasks}
    # Safety net: if the model omitted a specialist despite the prompt, create a
    # concrete role task so no specialist is permanently unassigned/idle.
    role_fallbacks = {
        "Research Agent": ("Validate requirements and research questions", "Create a research/validation brief and document assumptions."),
        "Product Manager": ("Finalize product requirements", "Create user stories, priorities and acceptance criteria."),
        "Software Architect": ("Finalize technical architecture", "Create architecture, API, data model and security-boundary artifacts."),
        "UI/UX Agent": ("Define user experience", "Create user flows, responsive UI structure and accessibility guidance."),
        "Frontend Developer": ("Implement frontend foundation", "Create the runnable frontend foundation from approved requirements."),
        "Backend Developer": ("Implement backend foundation", "Create the runnable backend foundation, APIs and persistence."),
        "QA Engineer": ("Create automated QA coverage", "Create tests and a verification report for the implemented system."),
        "Security Reviewer": ("Perform security review", "Review the project defensively for secrets, permissions, dependencies and common application risks."),
        "DevOps Agent": ("Prepare reproducible development environment", "Create local/dev environment, CI guidance and operational artifacts."),
        "Documentation Agent": ("Document the project", "Create setup, API and developer documentation based on the current workspace."),
    }
    for role, (title, description) in role_fallbacks.items():
        if role not in assigned_roles:
            plan_tasks.append({"title": title, "description": description, "agent": role, "priority": "medium", "depends_on": []})

    for item in plan_tasks:
        agent = agents.get(item.get("agent"))
        task = Task(project_id=project.id, agent_id=agent.id if agent else None, title=item.get("title", "Untitled task")[:250], description=item.get("description", ""), priority=item.get("priority", "medium"), dependencies_json="[]")
        db.add(task); db.flush(); created.append(task); by_title[task.title.strip().lower()] = task.id
    for task, item in zip(created, plan_tasks):
        deps=[]
        for dep in item.get("depends_on", []) or []:
            dep_id = by_title.get(str(dep).strip().lower())
            if dep_id and dep_id != task.id: deps.append(dep_id)
        task.dependencies_json = json.dumps(deps)
    db.commit()
    for task in created: db.refresh(task)
    db.refresh(project)
    return project, created
