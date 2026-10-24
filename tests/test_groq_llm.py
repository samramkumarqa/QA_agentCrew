"""Run the crew through the real Groq LLM class, intercepting only the network call, and check
exactly what would be sent to Groq. (CrewAI adds fields such as "cache_breakpoint" that Groq rejects.)"""

import json

import litellm

from conftest import SAMPLE
from fakes import ANSWERS
from qacrew.crew import run_crew
from qacrew.llm import MESSAGE_FIELDS, make_llm

ORDER = [("Current Task: Read this business requirements document", "analyze"),
         ("Current Task: Write test cases", "design"), ("Current Task: Review the Test Designer", "review"),
         ("Current Task: You are revising YOUR test suite", "revise"), ("Current Task: Recommend which test cases", "automate")]


def test_requests_sent_to_groq_are_clean(monkeypatch):
    sent = []
    real = litellm.completion

    def fake_completion(**kw):
        sent.append(kw)
        text = "\n".join(m["content"] for m in kw["messages"] if isinstance(m.get("content"), str))
        stage = next(s for marker, s in ORDER if marker in text)
        return real(model=kw["model"], messages=kw["messages"], mock_response=json.dumps(ANSWERS[stage]))

    monkeypatch.setattr(litellm, "completion", fake_completion)
    r = run_crew(SAMPLE.read_text(), make_llm("gsk_test", "openai/gpt-oss-120b"), project="Swag Labs")
    assert r.coverage_after.percent == 100
    assert len(sent) == 5
    for kw in sent:
        assert kw["model"] == "groq/openai/gpt-oss-120b"
        for m in kw["messages"]:
            assert set(m) <= MESSAGE_FIELDS, f"unsupported message fields sent to Groq: {set(m) - MESSAGE_FIELDS}"
        assert kw.get("reasoning_effort") == "low" and kw.get("api_key") == "gsk_test"
