from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(RegisterRequest):
    pass


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    description: str = ""
    project_id: Optional[int] = None
    agent_id: Optional[int] = None
    priority: str = "medium"
    dependencies: list[int] = Field(default_factory=list)


class ApprovalCreate(BaseModel):
    action: str
    reason: str
    risk: str = "medium"
    payload: dict = Field(default_factory=dict)


class DecisionRequest(BaseModel):
    decision: str


class ResearchRequest(BaseModel):
    industry: str
    audience: str
    region: str = "Global"
    live: bool = True
    provider: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    use_search: bool = True
    provider: str | None = None


class PlanRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=10000)
    create_project: bool = True


class PairRequest(BaseModel):
    token: str


class AgentHeartbeat(BaseModel):
    agent_id: str
    hostname: str = ""
    platform: str = ""


class ExecuteApprovedRequest(BaseModel):
    approval_id: int


class TeamBuildRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=10000)
    constraints: str = Field(default="", max_length=10000)
    create_project: bool = True


class TeamAdvanceRequest(BaseModel):
    project_id: int | None = None
    max_tasks: int = Field(default=3, ge=1, le=10)


class TeamReviewRequest(BaseModel):
    reviewer_agent: str = "QA Engineer"


class TeamRunRequest(BaseModel):
    project_id: int | None = None
    task_id: int | None = None
    max_tasks: int = Field(default=1, ge=1, le=10)


class DesktopActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    args: dict = Field(default_factory=dict)
    reason: str = Field(default="User requested desktop action", max_length=500)

class DesktopActionResult(BaseModel):
    status: str
    output: str = ""
    error: str = ""

class AgentActionResult(BaseModel):
    status: str
    output: str = ""
    error: str = ""
