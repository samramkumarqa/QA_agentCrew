"""A scripted LLM for offline tests: answers each task with prepared JSON, and can answer badly first
to exercise the guardrail retries."""

from __future__ import annotations

import json

from crewai.llms.base_llm import BaseLLM

REQS = {"requirements": [
    {"id": "REQ-01", "title": "Login", "description": "Registered users log in with username and password.",
     "acceptance_criteria": ["Valid credentials open the Products page", "Locked out users see an error"], "priority": "High"},
    {"id": "REQ-02", "title": "Add to cart", "description": "Users add products to the cart; the badge shows the count.",
     "acceptance_criteria": ["Badge shows the number of items"], "priority": "Medium"},
    {"id": "REQ-03", "title": "Checkout information", "description": "First name, last name and postal code are required.",
     "acceptance_criteria": ["Missing first name shows 'Error: First Name is required'"], "priority": "High"},
], "questions": [{"requirement_id": "REQ-02", "question": "Is there a maximum quantity per product?",
                  "why_it_matters": "Needed for boundary tests"}]}


def tc(i, reqs, title, typ="Positive", steps=None, expected="It works", prio="High"):
    return {"id": f"TC-{i:03d}", "requirement_ids": reqs, "title": title, "type": typ, "priority": prio,
            "preconditions": "", "steps": steps or ["Open the app", "Do the action"], "test_data": "", "expected_result": expected}


DESIGN = {"test_cases": [
    tc(1, ["REQ-01"], "Login with valid credentials", steps=["Open the login page", "Enter standard_user / secret_sauce", "Click Login"],
       expected="Products page is shown"),
    tc(2, ["REQ-01"], "Login as locked out user", "Negative", expected="Error: Sorry, this user has been locked out."),
    tc(3, ["REQ-02"], "Add backpack to cart", expected="Cart badge shows 1", prio="Medium"),
]}  # REQ-03 deliberately uncovered, REQ-02 positive only

REVIEW = {"findings": [
    {"kind": "uncovered", "target": "REQ-03", "severity": "High", "detail": "No test for required checkout fields.",
     "suggestion": "Add a negative case for a missing first name."},
    {"kind": "missing_negative", "target": "REQ-02", "severity": "Medium", "detail": "Only the happy path.",
     "suggestion": "Add removing an item and checking the badge."},
    {"kind": "vague_step", "target": "TC-003", "severity": "Low", "detail": "'Do the action' is vague.",
     "suggestion": "Say which button to click."},
], "summary": "Good login coverage; checkout is missing."}

REVISION = {"add": [
    tc(4, ["REQ-03"], "Checkout without first name", "Negative",
       steps=["Add a product", "Open the cart", "Click Checkout", "Leave First Name empty", "Click Continue"],
       expected="Error: First Name is required"),
    tc(5, ["REQ-02"], "Remove item updates badge", "Negative", expected="Badge disappears", prio="Medium"),
], "update": [tc(3, ["REQ-02"], "Add backpack to cart", steps=["Open Products", "Click 'Add to cart' on Sauce Labs Backpack"],
                 expected="Cart badge shows 1", prio="Medium")],
   "remove": [], "notes": "Added REQ-03 and REQ-02 negative cases; clarified TC-003."}

AUTOMATION = {"items": [
    {"test_case_id": "TC-001", "priority": "High", "layer": "UI", "reason": "Smoke test for every build."},
    {"test_case_id": "TC-004", "priority": "High", "layer": "API", "reason": "Validation rule checkable below the UI."},
    {"test_case_id": "TC-005", "priority": "Medium", "layer": "UI", "reason": "Cart state regression."},
    {"test_case_id": "TC-002", "priority": "Low", "layer": "Manual only", "reason": "Rare account state."},
], "summary": "Automate login and checkout validation first."}

ANSWERS = {"analyze": REQS, "design": DESIGN, "review": REVIEW, "revise": REVISION, "automate": AUTOMATION}


class ScriptedLLM(BaseLLM):
    """bad_first: {"design": "<bad answer>"} returns that once before the good answer."""

    def __init__(self, answers=None, bad_first=None, **kw):
        super().__init__(model="scripted", **kw)
        object.__setattr__(self, "_answers", answers or ANSWERS)
        object.__setattr__(self, "_bad", dict(bad_first or {}))
        object.__setattr__(self, "calls", [])

    def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None,
             from_agent=None, response_model=None):
        name = from_task.name if from_task else "?"
        prompt = messages if isinstance(messages, str) else "\n".join(m.get("content", "") for m in messages)
        self.calls.append((name, prompt))
        if name in self._bad:
            return self._bad.pop(name)
        return json.dumps(self._answers[name])

    def supports_function_calling(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 128_000
