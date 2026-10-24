# 🤝 QA Agent Crew: multi-agent test design with a built-in review

A team of AI agents built with **CrewAI** turns a business requirements document into a **reviewed,
traceable test pack**. Unlike a single prompt, the agents check each other's work: a QA Reviewer
inspects the Test Designer's suite against the requirements, and the Designer fixes what it finds.

**Live demo:** [appqaagentcrew.streamlit.app](https://appqaagentcrew.streamlit.app) · Built with CrewAI · Groq · Streamlit

> Part 5 of a QA AI toolkit:
> [AI Test Case Generator](https://github.com/samramkumarqa/GenerativeAI) ·
> [AI Automation Code Generator](https://github.com/samramkumarqa/QA_generateAutomationcodes) ·
> [Playwright Test Fixer](https://github.com/samramkumarqa/QA_playwrightMCP) ·
> [Jira Defect Assistant](https://github.com/samramkumarqa/QA_jiraDefectMCP) ·
> **QA Agent Crew**

## The crew

| # | Agent | Produces | Checked by the system |
|---|---|---|---|
| 1 | **Requirements Analyst** | Numbered requirements with acceptance criteria and priority, plus **questions for the BA** where the document is vague or silent | Unique `REQ-` ids |
| 2 | **Test Designer** | Positive, negative and boundary test cases with steps, test data and expected results, each linked to requirement ids | Unknown requirement ids, duplicate ids, missing steps or expected results; then **coverage is measured** |
| 3 | **QA Reviewer** | Findings: uncovered requirements, happy-path-only requirements, vague steps, weak expected results, duplicates, wrong mappings | Gets the **measured coverage facts** with the suite, so it starts from what is really missing |
| 4 | **Test Designer (revision)** | Only the changes: test cases to add, rewrite or remove | Same checks; the changes are applied to the suite |
| 5 | **Automation Strategist** | What to automate first and at which layer (UI, API, Unit, manual), with reasons | Only ids from the final suite |

Every agent answers in JSON. A guardrail parses and validates each answer; if it is broken or breaks a
rule, the agent gets the exact problem back and tries again. The app shows this live.

## What you get

- **Metrics:** requirements, BA questions, test cases, and **coverage before and after the review**
  (e.g. 67% → 100%), review findings.
- **Tabs:** test cases (with an ✅ approve checkbox; ✨ marks cases added or rewritten after review),
  review findings and the revision, a **traceability matrix**, requirements with BA questions, the
  automation plan, and the agent log.
- **Excel test pack:** Summary, Test Cases, Requirements, Traceability, Review Findings, BA Questions,
  Automation Plan. The **Test Cases sheet has the same columns as the AI Test Case Generator**, so it
  loads straight into the [AI Automation Code Generator](https://github.com/samramkumarqa/QA_generateAutomationcodes)
  to produce Playwright code.

The sample BRD (Swag Labs shop) matches the practice site used by the Automation Code Generator, and it
leaves some rules unstated on purpose (session timeout, maximum quantity, tax rounding) for the Analyst to raise.

## Run locally

```bash
git clone https://github.com/samramkumarqa/QA_agentCrew.git
cd QA_agentCrew
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your free Groq key from console.groq.com
streamlit run app.py
```

On Streamlit Cloud, add `GROQ_API_KEY = "gsk_..."` under App settings → Secrets (Python 3.12). The key is
never shown in the app.

**Groq free tier:** the crew makes about five model calls per run. If you hit the tokens-per-minute limit,
lower *Maximum requirements* in the sidebar or switch to the 20B model.

## Project layout

```
app.py                  Streamlit UI: document → live crew run → review tabs → Excel
qacrew/
  config/agents.yaml    the four agents' roles, goals and backstories
  config/tasks.yaml     the five tasks and the JSON each must return
  crew.py               builds and runs the crew; guardrails, coverage hand-off, live events
  schemas.py            Pydantic models for every agent's output
  checks.py             JSON parsing, rule checks, coverage, traceability, applying the revision
  excel.py              the test pack
  documents.py          PDF / Word / Markdown / text input
  llm.py                Groq models via CrewAI's LiteLLM provider
samples/swag_labs_brd.md
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
The tests run the real CrewAI crew offline with a scripted LLM: the full five-stage run, bad answers sent
back with the reason, the coverage facts reaching the Reviewer, the Excel sheets (read back with the
Automation Code Generator's own reader when it's checked out next to this repo), and the Streamlit app
clicked through end to end, including a check that the API key never appears on screen.

## Version history
- **2.0**: rebuilt on CrewAI 1.x and Groq. The agents now receive the document (1.0 only passed its file
  name), outputs are validated with retries, a review-and-revision round with measured coverage, BA
  questions, traceability, automation plan, Excel compatible with the Automation Code Generator, tests.
  The API key is no longer partly displayed.
- **1.0**: first CrewAI version on Gemini.
