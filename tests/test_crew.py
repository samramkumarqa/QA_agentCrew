import json

import pytest

from conftest import SAMPLE
from fakes import AUTOMATION, ANSWERS, ScriptedLLM
from qacrew.crew import CrewFailed, run_crew

BRD = SAMPLE.read_text()


def test_full_crew_run():
    events = []
    llm = ScriptedLLM()
    r = run_crew(BRD, llm, project="Swag Labs", on_event=events.append)
    assert [c[0] for c in llm.calls] == ["analyze", "design", "review", "revise", "automate"]
    # The old version never gave the agents the document; make sure the Analyst sees it now.
    analyst_prompt = llm.calls[0][1]
    assert "Tax is 8% of the item total." in analyst_prompt and "At most 12" in analyst_prompt
    # The Reviewer gets coverage facts measured by the system, not guessed by a model.
    review_prompt = llm.calls[2][1]
    assert "Requirements with NO test case: REQ-03." in review_prompt
    assert "Requirements tested only with positive cases: REQ-02." in review_prompt
    # The strategist sees the final ids, including the ones the revision added.
    assert "- TC-004 [Negative] Checkout without first name (REQ-03)" in llm.calls[4][1]
    assert (r.coverage_before.percent, r.coverage_after.percent) == (67, 100)
    assert [c.id for c in r.final.test_cases] == ["TC-001", "TC-002", "TC-003", "TC-004", "TC-005"]
    assert r.final.test_cases[2].steps[1] == "Click 'Add to cart' on Sauce Labs Backpack"  # updated by revision
    done = [(e["agent"], e["message"]) for e in events if e["status"] == "done"]
    assert done == [("Requirements Analyst", "3 requirements, 1 questions for the BA"),
                    ("Test Designer", "3 test cases, coverage 67%"), ("QA Reviewer", "3 findings (1 high)"),
                    ("Test Designer (revision)", "added 2, updated 1, removed 0"),
                    ("Automation Strategist", "3 to automate, 1 manual")]


def test_bad_answers_are_sent_back_with_the_reason():
    bad = '{"test_cases": [{"id": "TC-001", "requirement_ids": ["REQ-9"], "title": "x", "steps": [], "expected_result": ""}]}'
    llm = ScriptedLLM(bad_first={"design": bad, "analyze": "Sure! Here are the requirements."})
    events = []
    r = run_crew(BRD, llm, on_event=events.append)
    retries = [e["message"] for e in events if e["status"] == "retry"]
    assert retries[0].startswith("The answer must be a single JSON object")
    assert "TC-001 refers to unknown requirement(s) REQ-9" in retries[1]
    second_design = [p for n, p in llm.calls if n == "design"][1]
    assert "REQ-9" in second_design  # the feedback reached the agent
    assert r.coverage_after.percent == 100


def test_unknown_ids_in_automation_plan_are_rejected():
    plan = {**AUTOMATION, "items": AUTOMATION["items"] + [{"test_case_id": "TC-099", "priority": "Low", "layer": "UI", "reason": "x"}]}
    llm = ScriptedLLM(bad_first={"automate": json.dumps(plan)})
    events = []
    run_crew(BRD, llm, on_event=events.append)
    assert any("Unknown test case ids TC-099" in e["message"] for e in events if e["status"] == "retry")


def test_gives_up_with_a_clear_message():
    class AlwaysBad(ScriptedLLM):
        def call(self, messages, **kw):
            name = kw.get("from_task").name if kw.get("from_task") else ""
            return "not json" if name == "design" else super().call(messages, **kw)

    with pytest.raises(CrewFailed, match="Test Designer couldn't finish.*single JSON object"):
        run_crew(BRD, AlwaysBad(), max_retries=1)
    with pytest.raises(ValueError, match="too short"):
        run_crew("tiny", ScriptedLLM())
    assert set(ANSWERS) == {"analyze", "design", "review", "revise", "automate"}
