"""What each agent must produce. Agents answer in JSON; these models validate it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Priority = Literal["High", "Medium", "Low"]


def _cap(v):
    return v.strip().capitalize() if isinstance(v, str) else v


class Requirement(BaseModel):
    id: str = Field(description="REQ-01, REQ-02, ...")
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Priority = "Medium"

    _p = field_validator("priority", mode="before")(_cap)


class Question(BaseModel):
    requirement_id: str = ""
    question: str
    why_it_matters: str = ""


class RequirementsDoc(BaseModel):
    requirements: list[Requirement]
    questions: list[Question] = Field(default_factory=list)


class TestCase(BaseModel):
    id: str = Field(description="TC-001, TC-002, ...")
    requirement_ids: list[str]
    title: str
    type: Literal["Positive", "Negative", "Boundary"] = "Positive"
    priority: Priority = "Medium"
    preconditions: str = ""
    steps: list[str]
    test_data: str = ""
    expected_result: str

    _t = field_validator("type", "priority", mode="before")(_cap)


class TestSuite(BaseModel):
    test_cases: list[TestCase]


class Finding(BaseModel):
    kind: Literal["uncovered", "missing_negative", "vague_step", "weak_expected", "duplicate", "wrong_mapping", "other"]
    target: str = Field(description="the REQ-.. or TC-.. it is about")
    severity: Priority = "Medium"
    detail: str
    suggestion: str = ""

    _s = field_validator("severity", mode="before")(_cap)


class ReviewReport(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""


class Revision(BaseModel):
    """The designer's answer to the review: only what changes."""
    add: list[TestCase] = Field(default_factory=list)
    update: list[TestCase] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    notes: str = ""


class AutomationItem(BaseModel):
    test_case_id: str
    priority: Priority = "Medium"
    layer: Literal["UI", "API", "Unit", "Manual only"] = "UI"
    reason: str

    _p = field_validator("priority", mode="before")(_cap)


class AutomationPlan(BaseModel):
    items: list[AutomationItem] = Field(default_factory=list)
    summary: str = ""
