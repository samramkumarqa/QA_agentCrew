"""Click through the Streamlit app with the scripted LLM."""

from streamlit.testing.v1 import AppTest

from conftest import ROOT
from fakes import ScriptedLLM

SECRET = "gsk_supersecretvalue123"


def _app(monkeypatch):
    import qacrew.llm
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    monkeypatch.setattr(qacrew.llm, "make_llm", lambda key, model: ScriptedLLM())
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)


def _all_text(at):
    parts = []
    for kind in ("markdown", "caption", "success", "info", "warning", "error", "text", "metric", "title", "subheader"):
        for el in getattr(at, kind, []):
            parts.append(str(getattr(el, "value", "")) + str(getattr(el, "label", "")))
    return "\n".join(parts)


def test_sample_run_review_and_download(monkeypatch):
    at = _app(monkeypatch)
    at.run()
    assert not at.exception
    next(b for b in at.button if b.label.startswith("Use sample BRD")).click().run()
    assert any("swag_labs_brd.md" in s.value for s in at.success)
    next(b for b in at.button if b.label.startswith("🚀 Run the agents")).click().run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics == {"Requirements": "3", "Questions for the BA": "1", "Test cases": "5",
                       "Requirement coverage": "100%", "Review findings": "3"}
    dl = next(b for b in at.get("download_button") if "test pack" in b.proto.label)
    assert "5 test cases" in dl.proto.label
    assert SECRET not in _all_text(at)  # the key is never shown


def test_untick_leaves_case_out(monkeypatch):
    at = _app(monkeypatch)
    at.run()
    next(b for b in at.button if b.label.startswith("Use sample BRD")).click().run()
    next(b for b in at.button if b.label.startswith("🚀 Run the agents")).click().run()
    at.session_state.approved["TC-002"] = False
    at.run()
    dl = next(b for b in at.get("download_button") if "test pack" in b.proto.label)
    assert "4 test cases" in dl.proto.label
