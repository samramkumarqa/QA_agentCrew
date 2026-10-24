"""Deterministic parts: parse agent JSON, validate it, measure coverage and apply the revision.
Nothing here asks the LLM; it checks the LLM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from .schemas import RequirementsDoc, Revision, TestCase, TestSuite


class AgentOutputError(ValueError):
    """The agent's answer can't be used; the message is sent back to it as feedback."""


def extract_json(text: str):
    """The JSON object in an agent's answer, tolerating code fences and text around it."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I | re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except json.JSONDecodeError as e:
            raise AgentOutputError(f"The answer is not valid JSON ({e.msg} at character {e.pos}).") from e
    raise AgentOutputError("The answer must be a single JSON object, with no text before or after it.")


def parse(model: type[BaseModel], text: str):
    data = extract_json(text)
    try:
        return model.model_validate(data)
    except ValidationError as e:
        problems = []
        for err in e.errors()[:12]:
            loc = ".".join(str(x) for x in err["loc"])
            problems.append(f"{loc}: {err['msg']}")
        raise AgentOutputError("The JSON doesn't match the required format: " + "; ".join(problems)) from e


# ------------------------------------------------------------- structural rules (sent back as feedback)

def check_requirements(doc: RequirementsDoc) -> list[str]:
    errs = []
    if not doc.requirements:
        errs.append("No requirements were extracted.")
    ids = [r.id for r in doc.requirements]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"Requirement ids must be unique; repeated: {', '.join(dup)}.")
    bad = [i for i in ids if not re.match(r"^REQ-\d+$", i)]
    if bad:
        errs.append(f"Requirement ids must look like REQ-01; got {', '.join(bad[:5])}.")
    return errs


def check_cases(cases: list[TestCase], req_ids: set[str]) -> list[str]:
    errs = []
    ids = [c.id for c in cases]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"Test case ids must be unique; repeated: {', '.join(dup)}.")
    for c in cases:
        unknown = [r for r in c.requirement_ids if r not in req_ids]
        if not c.requirement_ids:
            errs.append(f"{c.id} must list the requirement id(s) it covers.")
        elif unknown:
            errs.append(f"{c.id} refers to unknown requirement(s) {', '.join(unknown)}; use only {', '.join(sorted(req_ids))}.")
        if not [s for s in c.steps if s.strip()]:
            errs.append(f"{c.id} has no steps.")
        if not c.expected_result.strip():
            errs.append(f"{c.id} has no expected result.")
    return errs


# ------------------------------------------------------------- coverage and revision

@dataclass
class Coverage:
    total: int
    covered: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    without_negative: list[str] = field(default_factory=list)

    @property
    def percent(self) -> int:
        return round(100 * len(self.covered) / self.total) if self.total else 0


def coverage(doc: RequirementsDoc, suite: TestSuite) -> Coverage:
    by_req: dict[str, list[TestCase]] = {r.id: [] for r in doc.requirements}
    for c in suite.test_cases:
        for r in c.requirement_ids:
            if r in by_req:
                by_req[r].append(c)
    covered = [r for r, cs in by_req.items() if cs]
    return Coverage(
        total=len(by_req), covered=covered, uncovered=[r for r, cs in by_req.items() if not cs],
        without_negative=[r for r, cs in by_req.items() if cs and not any(c.type != "Positive" for c in cs)],
    )


def traceability(doc: RequirementsDoc, suite: TestSuite) -> list[dict]:
    rows = []
    for r in doc.requirements:
        cases = [c for c in suite.test_cases if r.id in c.requirement_ids]
        types = sorted({c.type for c in cases})
        rows.append({"requirement": r.id, "title": r.title, "test_cases": [c.id for c in cases],
                     "types": types, "status": "Covered" if cases else "Not covered"})
    return rows


def apply_revision(suite: TestSuite, rev: Revision) -> tuple[TestSuite, dict]:
    cases = {c.id: c for c in suite.test_cases}
    removed = [i for i in rev.remove if i in cases]
    for i in removed:
        cases.pop(i)
    updated = []
    for c in rev.update:
        if c.id in cases:
            cases[c.id] = c
            updated.append(c.id)
    added = []
    for c in rev.add:
        cid = c.id
        if cid in cases:  # renumber clashes instead of overwriting
            n = max([int(re.sub(r"\D", "", k) or 0) for k in cases] + [0]) + 1
            cid = f"TC-{n:03d}"
            c = c.model_copy(update={"id": cid})
        cases[cid] = c
        added.append(cid)
    ordered = sorted(cases.values(), key=lambda c: (int(re.sub(r"\D", "", c.id) or 0), c.id))
    return TestSuite(test_cases=ordered), {"added": added, "updated": updated, "removed": removed}
