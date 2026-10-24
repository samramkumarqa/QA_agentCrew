"""The crew: Analyst -> Designer -> Reviewer -> Designer (revision) -> Automation Strategist.

Each task's answer passes a guardrail that parses and validates it; problems go back to the agent as
feedback for a retry. Between design and review, the system measures coverage itself and hands the
facts to the Reviewer, so the review starts from what is actually missing.
"""

from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

os.environ.setdefault("CREWAI_TELEMETRY_ENABLED", "false")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

import yaml  # noqa: E402
from crewai import Agent, Crew, Process, Task  # noqa: E402

from . import checks  # noqa: E402
from .schemas import AutomationPlan, RequirementsDoc, Revision, ReviewReport, TestSuite  # noqa: E402

warnings.filterwarnings("ignore", message="function callbacks cannot be serialized")
CONFIG = Path(__file__).with_name("config")
MAX_BRD_CHARS = 24_000

AGENT_NAMES = {"analyze": "Requirements Analyst", "design": "Test Designer", "review": "QA Reviewer",
               "revise": "Test Designer (revision)", "automate": "Automation Strategist"}


@dataclass
class CrewResult:
    requirements: RequirementsDoc
    draft: TestSuite
    review: ReviewReport
    revision: Revision
    final: TestSuite
    automation: AutomationPlan
    changes: dict
    coverage_before: checks.Coverage
    coverage_after: checks.Coverage
    events: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    truncated: bool = False


class CrewFailed(RuntimeError):
    """A stage couldn't produce usable output after its retries."""


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def run_crew(brd_text: str, llm, project: str = "the application", on_event: Callable[[dict], None] | None = None,
             max_requirements: int = 12, max_cases_per_requirement: int = 3, max_retries: int = 2,
             max_rpm: int | None = None) -> CrewResult:
    """Run the whole crew. `llm` is a CrewAI LLM (or any BaseLLM, e.g. a scripted one in tests)."""
    text = (brd_text or "").strip()
    if len(text) < 40:
        raise ValueError("The document is empty or too short to analyse.")
    truncated = len(text) > MAX_BRD_CHARS
    text = text[:MAX_BRD_CHARS]

    events: list[dict] = []
    parsed: dict = {}
    started = time.time()

    def emit(stage: str, status: str, message: str):
        ev = {"stage": stage, "agent": AGENT_NAMES[stage], "status": status, "message": message,
              "t": round(time.time() - started, 1)}
        events.append(ev)
        if on_event:
            on_event(ev)

    a_cfg, t_cfg = _load("agents.yaml"), _load("tasks.yaml")
    agents = {k: Agent(**v, llm=llm, allow_delegation=False, verbose=False, max_retry_limit=1) for k, v in a_cfg.items()}

    def guarded(stage: str, fn):
        """Wrap a stage's validation: parse, check, store, report; or return feedback for a retry."""
        def guardrail(output):
            try:
                value, message = fn(output.raw)
            except checks.AgentOutputError as e:
                emit(stage, "retry", str(e))
                return False, f"{e} Answer again with only the corrected JSON object."
            parsed[stage] = value
            emit(stage, "done", message)
            return True, output.raw
        guardrail.__name__ = f"check_{stage}"
        return guardrail

    def do_analyze(raw):
        doc = checks.parse(RequirementsDoc, raw)
        errs = checks.check_requirements(doc)
        if errs:
            raise checks.AgentOutputError(" ".join(errs))
        return doc, f"{len(doc.requirements)} requirements, {len(doc.questions)} questions for the BA"

    def do_design(raw):
        suite = checks.parse(TestSuite, raw)
        req_ids = {r.id for r in parsed["analyze"].requirements}
        errs = checks.check_cases(suite.test_cases, req_ids)
        if errs:
            raise checks.AgentOutputError(" ".join(errs[:10]))
        cov = checks.coverage(parsed["analyze"], suite)
        facts = [f"Measured by the system: {cov.percent}% of requirements have at least one test case."]
        if cov.uncovered:
            facts.append("Requirements with NO test case: " + ", ".join(cov.uncovered) + ".")
        if cov.without_negative:
            facts.append("Requirements tested only with positive cases: " + ", ".join(cov.without_negative) + ".")
        tasks["review"].description += "\n" + " ".join(facts)
        return suite, f"{len(suite.test_cases)} test cases, coverage {cov.percent}%"

    def do_review(raw):
        rep = checks.parse(ReviewReport, raw)
        high = sum(f.severity == "High" for f in rep.findings)
        return rep, f"{len(rep.findings)} findings ({high} high)"

    def do_revise(raw):
        rev = checks.parse(Revision, raw)
        req_ids = {r.id for r in parsed["analyze"].requirements}
        errs = checks.check_cases(rev.add + rev.update, req_ids)
        if errs:
            raise checks.AgentOutputError(" ".join(errs[:10]))
        final, changes = checks.apply_revision(parsed["design"], rev)
        parsed["final"], parsed["changes"] = final, changes
        tasks["automate"].description += (
            "\nThe final suite after revision (use these ids):\n"
            + "\n".join(f"- {c.id} [{c.type}] {c.title} ({', '.join(c.requirement_ids)})" for c in final.test_cases))
        return rev, (f"added {len(changes['added'])}, updated {len(changes['updated'])}, "
                     f"removed {len(changes['removed'])}")

    def do_automate(raw):
        plan = checks.parse(AutomationPlan, raw)
        known = {c.id for c in parsed["final"].test_cases}
        unknown = [i.test_case_id for i in plan.items if i.test_case_id not in known]
        if unknown:
            raise checks.AgentOutputError(f"Unknown test case ids {', '.join(unknown[:8])}; use only the final suite's ids.")
        auto = sum(i.layer != "Manual only" for i in plan.items)
        return plan, f"{auto} to automate, {len(plan.items) - auto} manual"

    steps = {"analyze": ("analyst", do_analyze, []), "design": ("designer", do_design, ["analyze"]),
             "review": ("reviewer", do_review, ["analyze", "design"]),
             "revise": ("designer", do_revise, ["analyze", "design", "review"]),
             "automate": ("strategist", do_automate, ["analyze"])}
    tasks: dict[str, Task] = {}
    for name, (agent_key, fn, ctx) in steps.items():
        tasks[name] = Task(name=name, agent=agents[agent_key], context=[tasks[c] for c in ctx],
                           guardrail=guarded(name, fn), guardrail_max_retries=max_retries, **t_cfg[name])

    def task_started(stage):
        emit(stage, "working", f"{AGENT_NAMES[stage]} is working…")

    order = list(steps)

    def on_task_done(output):
        nxt = order.index(output.name) + 1 if output.name in order else len(order)
        if nxt < len(order):
            task_started(order[nxt])

    crew = Crew(agents=list(agents.values()), tasks=list(tasks.values()), process=Process.sequential,
                verbose=False, memory=False, cache=False, task_callback=on_task_done, max_rpm=max_rpm)
    task_started("analyze")
    try:
        crew.kickoff(inputs={"brd": text, "project": project, "max_requirements": max_requirements,
                             "max_cases_per_requirement": max_cases_per_requirement})
    except Exception as e:  # a stage exhausted its retries, or the LLM call failed
        stage = next((s for s in order if s not in parsed), "")
        last = next((ev["message"] for ev in reversed(events) if ev["status"] == "retry"), "")
        detail = f" Last problem: {last}" if last else ""
        raise CrewFailed(f"{AGENT_NAMES.get(stage, 'The crew')} couldn't finish: {str(e)[:400]}{detail}") from e

    doc, draft = parsed["analyze"], parsed["design"]
    return CrewResult(
        requirements=doc, draft=draft, review=parsed["review"], revision=parsed["revise"], final=parsed["final"],
        automation=parsed["automate"], changes=parsed["changes"],
        coverage_before=checks.coverage(doc, draft), coverage_after=checks.coverage(doc, parsed["final"]),
        events=events, seconds=round(time.time() - started, 1), truncated=truncated,
    )
