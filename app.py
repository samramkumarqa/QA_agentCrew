"""Streamlit UI for the QA Agent Crew: BRD in, reviewed and traceable test pack out."""

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from qacrew.checks import traceability
from qacrew.crew import CrewFailed, run_crew
from qacrew.documents import DocumentError, read_document
from qacrew.excel import build_workbook
from qacrew.llm import MODELS, friendly_error, make_llm

ROOT = Path(__file__).parent
SAMPLE = ROOT / "samples" / "swag_labs_brd.md"
load_dotenv()

st.set_page_config(page_title="QA Agent Crew", page_icon="🤝", layout="wide")


def configured_key() -> str:
    try:
        key = st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        key = ""
    return key or os.getenv("GROQ_API_KEY", "")


ICON = {"working": "⏳", "done": "✅", "retry": "🔁"}

# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.header("Settings")
    key = configured_key()
    if key:
        st.success("Groq API key configured", icon="🔑")
    else:
        key = st.text_input("Groq API key", type="password", help="Free at console.groq.com. Not stored.")
    model = st.selectbox("Model", list(MODELS), format_func=lambda m: MODELS[m])
    max_reqs = st.slider("Maximum requirements", 4, 20, 10,
                         help="Fewer requirements = fewer tokens; helps with Groq's free-tier rate limits.")
    max_cases = st.slider("Maximum test cases per requirement", 1, 5, 3)
    st.divider()
    st.markdown("**The crew**")
    st.markdown("1. Requirements Analyst\n2. Test Designer\n3. QA Reviewer\n4. Test Designer (revision)\n"
                "5. Automation Strategist")
    st.caption("Built with CrewAI · Groq · Streamlit")

st.title("🤝 QA Agent Crew")
st.markdown(
    "A team of AI agents turns a requirements document into a **reviewed, traceable test pack**. "
    "The Analyst extracts requirements and questions for the BA, the Designer writes test cases, the "
    "Reviewer checks them against the requirements, and the Designer fixes what the Reviewer found."
)

# ---------------------------------------------------------------- 1 · document

st.subheader("1 · Requirements document")
c1, c2 = st.columns([3, 2])
with c1:
    upload = st.file_uploader("BRD (PDF, Word, Markdown or text)", type=["pdf", "docx", "md", "txt"])
with c2:
    st.write("No document handy?")
    use_sample = st.button("Use sample BRD (Swag Labs shop)")
    st.download_button("Download sample BRD", SAMPLE.read_bytes(), SAMPLE.name)

try:
    if upload is not None and st.session_state.get("doc_name") != upload.name:
        st.session_state.doc_text = read_document(upload.name, upload.getvalue())
        st.session_state.doc_name = upload.name
        st.session_state.pop("result", None)
    elif use_sample:
        st.session_state.doc_text = SAMPLE.read_text(encoding="utf-8")
        st.session_state.doc_name = SAMPLE.name
        st.session_state.pop("result", None)
except DocumentError as e:
    st.error(str(e))

doc = st.session_state.get("doc_text")
if not doc:
    st.stop()
name = st.session_state.doc_name
project = Path(name).stem.replace("_", " ").replace("-", " ").strip() or "the application"
st.success(f"**{name}** loaded: {len(doc.split()):,} words", icon="📄")
with st.expander("Preview the document"):
    st.text(doc[:4000] + ("…" if len(doc) > 4000 else ""))

# ---------------------------------------------------------------- 2 · run

st.subheader("2 · Run the crew")
if not key:
    st.warning("Add a Groq API key in the sidebar to continue.")
    st.stop()

if st.button("🚀 Run the agents", type="primary"):
    status = st.status("The crew is working…", expanded=True)
    lines: dict[str, object] = {}

    def show(ev):
        slot = lines.setdefault(ev["stage"], status.empty())
        text = f"{ICON.get(ev['status'], '•')} **{ev['agent']}**: {ev['message']}  · {ev['t']}s"
        if ev["status"] == "retry":
            status.write(f"🔁 **{ev['agent']}** answer rejected, asked to fix: {ev['message'][:300]}")
        else:
            slot.markdown(text)

    try:
        result = run_crew(doc, make_llm(key, model), project=project, on_event=show,
                          max_requirements=max_reqs, max_cases_per_requirement=max_cases, max_rpm=25)
    except (CrewFailed, ValueError) as e:
        status.update(label="The crew stopped", state="error")
        st.error(friendly_error(e))
        st.stop()
    except Exception as e:
        status.update(label="The crew stopped", state="error")
        st.error(friendly_error(e))
        st.stop()
    status.update(label=f"Done in {result.seconds:.0f} s", state="complete", expanded=False)
    st.session_state.result = result
    st.session_state.result_model = model
    st.session_state.approved = {c.id: True for c in result.final.test_cases}

result = st.session_state.get("result")
if not result:
    st.stop()

# ---------------------------------------------------------------- 3 · results

st.subheader("3 · Review the results")
if result.truncated:
    st.info("The document was long, so only its first part was analysed.", icon="✂️")
m = st.columns(5)
m[0].metric("Requirements", len(result.requirements.requirements))
m[1].metric("Questions for the BA", len(result.requirements.questions))
m[2].metric("Test cases", len(result.final.test_cases),
            delta=f"+{len(result.final.test_cases) - len(result.draft.test_cases)} after review"
            if len(result.final.test_cases) != len(result.draft.test_cases) else None)
m[3].metric("Requirement coverage", f"{result.coverage_after.percent}%",
            delta=f"{result.coverage_after.percent - result.coverage_before.percent:+d} pts after review"
            if result.coverage_after.percent != result.coverage_before.percent else None)
m[4].metric("Review findings", len(result.review.findings))

tabs = st.tabs(["✅ Test cases", "🔍 Review", "🧭 Traceability", "📋 Requirements & BA questions",
                "🤖 Automation plan", "🕒 Agent log"])
plan = {i.test_case_id: i for i in result.automation.items}
changed = set(result.changes["added"]) | set(result.changes["updated"])

with tabs[0]:
    st.caption("Untick a test case to leave it out of the download. ✨ = added or rewritten after the review.")
    df = pd.DataFrame([{
        "✅": st.session_state.approved.get(c.id, True), "ID": c.id + (" ✨" if c.id in changed else ""),
        "Requirement": ", ".join(c.requirement_ids), "Title": c.title, "Type": c.type, "Priority": c.priority,
        "Steps": "\n".join(f"{i}. {s}" for i, s in enumerate(c.steps, 1)), "Test data": c.test_data,
        "Expected result": c.expected_result,
        "Automation": f"{plan[c.id].layer} · {plan[c.id].priority}" if c.id in plan else "",
    } for c in result.final.test_cases])
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=[c for c in df.columns if c != "✅"],
                            column_config={"✅": st.column_config.CheckboxColumn("✅", width="small")}, key="tc_editor")
    for c, ok in zip(result.final.test_cases, edited["✅"]):
        st.session_state.approved[c.id] = bool(ok)

with tabs[1]:
    st.markdown(f"**Reviewer's summary:** {result.review.summary}")
    if result.review.findings:
        st.dataframe(pd.DataFrame([{"Severity": f.severity, "Kind": f.kind.replace('_', ' '), "Target": f.target,
                                    "Finding": f.detail, "Suggestion": f.suggestion} for f in result.review.findings]),
                     hide_index=True, width="stretch")
    ch = result.changes
    st.markdown(f"**Designer's revision:** added {len(ch['added'])} ({', '.join(ch['added']) or '-'}), updated "
                f"{len(ch['updated'])} ({', '.join(ch['updated']) or '-'}), removed {len(ch['removed'])} "
                f"({', '.join(ch['removed']) or '-'}).")
    if result.revision.notes:
        st.markdown(f"> {result.revision.notes}")
    st.markdown(f"Coverage before review **{result.coverage_before.percent}%** → after **{result.coverage_after.percent}%**."
                + (f" Still not covered: {', '.join(result.coverage_after.uncovered)}." if result.coverage_after.uncovered else ""))

with tabs[2]:
    st.dataframe(pd.DataFrame([{"Requirement": t["requirement"], "Title": t["title"],
                                "Test cases": ", ".join(t["test_cases"]), "Types": ", ".join(t["types"]),
                                "Status": ("✅ " if t["status"] == "Covered" else "⚠️ ") + t["status"]}
                               for t in traceability(result.requirements, result.final)]),
                 hide_index=True, width="stretch")

with tabs[3]:
    st.dataframe(pd.DataFrame([{"ID": r.id, "Title": r.title, "Priority": r.priority, "Description": r.description,
                                "Acceptance criteria": "\n".join(f"• {a}" for a in r.acceptance_criteria)}
                               for r in result.requirements.requirements]), hide_index=True, width="stretch")
    st.markdown("**Questions for the BA** (gaps or ambiguities in the document)")
    if result.requirements.questions:
        for q in result.requirements.questions:
            st.markdown(f"- **{q.requirement_id or 'General'}**: {q.question}"
                        + (f" *({q.why_it_matters})*" if q.why_it_matters else ""))
    else:
        st.caption("None.")

with tabs[4]:
    st.markdown(result.automation.summary)
    titles = {c.id: c.title for c in result.final.test_cases}
    st.dataframe(pd.DataFrame([{"Test case": i.test_case_id, "Title": titles.get(i.test_case_id, ""),
                                "Priority": i.priority, "Layer": i.layer, "Reason": i.reason}
                               for i in result.automation.items]), hide_index=True, width="stretch")

with tabs[5]:
    for ev in result.events:
        if ev["status"] != "working":
            st.markdown(f"`{ev['t']:>6}s` {ICON.get(ev['status'], '•')} **{ev['agent']}**: {ev['message']}")

approved = {cid for cid, ok in st.session_state.approved.items() if ok}
st.download_button(
    f"⬇️ Download test pack (.xlsx, {len(approved)} test cases)",
    build_workbook(result, project, st.session_state.get("result_model", model), approved),
    f"{project.replace(' ', '_')}_test_pack.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", disabled=not approved,
)
st.caption("The Test Cases sheet can be loaded straight into the AI Automation Code Generator to produce Playwright code.")
