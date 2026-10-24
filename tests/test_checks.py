import pytest

from fakes import DESIGN, REQS, REVISION
from qacrew.checks import (AgentOutputError, apply_revision, check_cases, check_requirements, coverage, extract_json,
                           parse, traceability)
from qacrew.schemas import RequirementsDoc, Revision, TestSuite


def test_extract_json_tolerates_fences_and_chatter():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go:\n{"a": {"b": 2}}\nThanks!') == {"a": {"b": 2}}
    with pytest.raises(AgentOutputError, match="single JSON object"):
        extract_json("no json here")


def test_parse_reports_field_errors():
    with pytest.raises(AgentOutputError, match=r"test_cases\.0\.steps: Field required"):
        parse(TestSuite, '{"test_cases": [{"id": "TC-001", "requirement_ids": ["REQ-01"], "title": "x", "expected_result": "y"}]}')
    s = parse(TestSuite, '{"test_cases": [{"id": "TC-001", "requirement_ids": ["REQ-01"], "title": "x", "type": "negative", '
                         '"priority": "high", "steps": ["a"], "expected_result": "y"}]}')
    assert (s.test_cases[0].type, s.test_cases[0].priority) == ("Negative", "High")  # case-insensitive


def test_structural_checks():
    doc = RequirementsDoc.model_validate(REQS)
    assert check_requirements(doc) == []
    bad = RequirementsDoc.model_validate({"requirements": [REQS["requirements"][0], {**REQS["requirements"][0], "id": "R1"}]})
    assert any("REQ-01" in e for e in check_requirements(bad))
    suite = TestSuite.model_validate(DESIGN)
    assert check_cases(suite.test_cases, {"REQ-01", "REQ-02", "REQ-03"}) == []
    errs = check_cases(suite.test_cases, {"REQ-01"})
    assert any("unknown requirement(s) REQ-02" in e for e in errs)


def test_coverage_revision_and_traceability():
    doc, suite = RequirementsDoc.model_validate(REQS), TestSuite.model_validate(DESIGN)
    cov = coverage(doc, suite)
    assert (cov.percent, cov.uncovered, cov.without_negative) == (67, ["REQ-03"], ["REQ-02"])
    final, ch = apply_revision(suite, Revision.model_validate(REVISION))
    assert ch == {"added": ["TC-004", "TC-005"], "updated": ["TC-003"], "removed": []}
    assert coverage(doc, final).percent == 100
    clash = Revision.model_validate({"add": [{**DESIGN["test_cases"][0], "title": "new"}], "remove": ["TC-002"]})
    final2, ch2 = apply_revision(suite, clash)
    assert ch2["added"] == ["TC-004"] and [c.id for c in final2.test_cases] == ["TC-001", "TC-003", "TC-004"]
    rows = traceability(doc, final)
    assert rows[2] == {"requirement": "REQ-03", "title": "Checkout information", "test_cases": ["TC-004"],
                       "types": ["Negative"], "status": "Covered"}
