import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models import Agent, AuditLog

AGENTS = [
("Command Agent", "Orchestrator", "Understands requests, creates plans, and coordinates the team."),
("Research Agent", "Market Intelligence", "Researches demand, competitors, trends, and product opportunities."),
("Product Manager", "Product Planning", "Creates requirements, user stories, priorities, and acceptance criteria."),
("Software Architect", "Architecture", "Designs application architecture, APIs, databases, and technical standards."),
("UI/UX Agent", "Design", "Creates user flows, layouts, accessibility guidance, and design-system recommendations."),
("Frontend Developer", "Frontend Engineering", "Builds React, Next.js, TypeScript, HTML, CSS, and browser interfaces."),
("Backend Developer", "Backend Engineering", "Builds APIs, services, authentication, integrations, and databases."),
("QA Engineer", "Quality Assurance", "Creates test plans, unit/integration tests, and regression strategies."),
("Security Reviewer", "Application Security", "Reviews dependencies, secrets, permissions, and application security."),
("DevOps Agent", "Infrastructure", "Prepares Docker, CI/CD, deployment, monitoring, and environment configuration."),
("Documentation Agent", "Documentation", "Creates setup guides, API documentation, and technical references."),
("Laptop Agent", "Local Execution", "Carries out approved workspace operations on the paired development machine."),
]


def seed_agents(db: Session):
    existing = {a.name for a in db.query(Agent).all()}
    changed = False
    for name, role, description in AGENTS:
        if name not in existing:
            db.add(Agent(name=name, role=role, description=description))
            changed = True
    if changed:
        db.commit()


def log(db: Session, event: str, details: str, actor: str = "system", level: str = "info"):
    db.add(AuditLog(actor=actor, event=event, details=details, level=level))
    db.commit()


def local_opportunity_report(industry, audience, region):
    return {
        "summary": f"Offline hypothesis scan for {industry} products serving {audience} in {region}.",
        "validation_status": "hypothesis_only",
        "warning": "This is an offline hypothesis report. Validate current market facts with an external research workflow before making business decisions.",
        "opportunities": [
            {"idea": f"Workflow automation platform for {audience}", "problem": "Manual repetitive work and fragmented tools", "mvp": ["Workspace", "Task automation", "Notifications", "Analytics"]},
            {"idea": f"Compliance/reporting assistant for {industry}", "problem": "Time-consuming documentation and reporting", "mvp": ["Templates", "Evidence collection", "Exports", "Audit trail"]},
            {"idea": f"Customer portal for {industry}", "problem": "Low visibility and fragmented communication", "mvp": ["Customer login", "Status tracking", "Messaging", "Document sharing"]},
        ],
        "research_questions": [
            "Who experiences the problem most frequently?",
            "What do they use today?",
            "What measurable outcome would justify payment?",
            "What privacy, regulatory, and integration constraints exist?",
        ],
    }
