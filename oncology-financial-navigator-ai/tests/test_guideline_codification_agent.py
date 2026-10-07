"""
Tests for the Guideline Codification Agent (Agent 5,
app/agents/guideline_codification_agent.py).

Focus areas: correct extraction on clean text, appropriately low confidence (never a
guess) on vague text, and the specific poverty-line regex bug found and fixed live in
an earlier session (must match both the "X% of the federal poverty line" and
"X percent of poverty level" phrasings).
"""

import pytest

from guideline_codification_agent import GuidelineCodificationAgent


@pytest.fixture
def agent():
    return GuidelineCodificationAgent()


def test_clean_structured_text_produces_high_confidence_fields(agent):
    # Note: overall_confidence is still dragged down to "low" here because no
    # known_diagnosis_keywords list was supplied, and diagnosis extraction is
    # deliberately always "low" confidence without one (see
    # test_diagnosis_extraction_is_conservative_without_keyword_list below) --
    # that is correct, cautious behavior, not a bug. This test checks that the
    # *other* fields it can confidently extract from clean text are high confidence.
    text = (
        "Household income must be at or below 400% of the federal poverty line. "
        "Patients must be uninsured or underinsured. Required: patient name, "
        "diagnosis code, household income."
    )
    draft = agent.codify(
        foundation_id="fund_a", foundation_name="Fund A",
        fetched_guideline_text=text, previous_rules_version="v1",
    )
    assert draft.proposed_max_income_multiplier_of_poverty_line == 4.0
    assert "uninsured" in draft.proposed_eligible_insurance_statuses
    assert "underinsured" in draft.proposed_eligible_insurance_statuses
    assert draft.proposed_rules_version == "v2"

    income_extraction = next(e for e in draft.field_extractions if e.field_name == "max_income_multiplier_of_poverty_line")
    insurance_extraction = next(e for e in draft.field_extractions if e.field_name == "eligible_insurance_statuses")
    assert income_extraction.confidence == "high"
    assert insurance_extraction.confidence == "high"


def test_clean_text_with_diagnosis_keyword_list_reaches_high_or_medium_overall_confidence(agent):
    # Same clean text, but this time with a known-diagnosis keyword list supplied so
    # every field has a real chance at non-low confidence, which is what overall
    # confidence should require before a human sees it flagged as reliable.
    text = (
        "Household income must be at or below 400% of the federal poverty line. "
        "Patients must be uninsured or underinsured, with breast cancer. "
        "Required: patient name, diagnosis code, household income."
    )
    draft = agent.codify(
        foundation_id="fund_a2", foundation_name="Fund A2",
        fetched_guideline_text=text, previous_rules_version="v1",
        known_diagnosis_keywords=["breast cancer", "lung cancer"],
    )
    assert draft.overall_confidence in ("high", "medium")


def test_percent_word_phrasing_also_matches(agent):
    # Regression test for the live bug fix: "percent of poverty level" phrasing
    # must match just like "% of the federal poverty line" does.
    text = "Household income must be at or below 250 percent of poverty level."
    draft = agent.codify(
        foundation_id="fund_b", foundation_name="Fund B",
        fetched_guideline_text=text, previous_rules_version="v1",
    )
    assert draft.proposed_max_income_multiplier_of_poverty_line == 2.5


def test_vague_text_yields_low_confidence_not_a_guess(agent):
    text = "Please contact us for more information about eligibility."
    draft = agent.codify(
        foundation_id="fund_c", foundation_name="Fund C",
        fetched_guideline_text=text, previous_rules_version="v1",
    )
    assert draft.proposed_max_income_multiplier_of_poverty_line is None
    assert draft.overall_confidence == "low"
    assert draft.requires_careful_human_review is True


def test_diagnosis_extraction_is_conservative_without_keyword_list(agent):
    text = "This fund is only for patients with a rare pediatric sarcoma diagnosis."
    draft = agent.codify(
        foundation_id="fund_d", foundation_name="Fund D",
        fetched_guideline_text=text, previous_rules_version="v1",
    )
    # No known_diagnosis_keywords supplied -> must not invent a diagnosis list.
    assert draft.proposed_eligible_diagnoses == []


def test_diagnosis_extraction_matches_supplied_keyword_list(agent):
    text = "For women currently being treated for breast cancer."
    draft = agent.codify(
        foundation_id="fund_e", foundation_name="Fund E",
        fetched_guideline_text=text, previous_rules_version="v1",
        known_diagnosis_keywords=["breast cancer", "lung cancer"],
    )
    assert draft.proposed_eligible_diagnoses == ["breast cancer"]


def test_proposed_rules_version_increments_numeric_version(agent):
    draft = agent.codify(
        foundation_id="fund_f", foundation_name="Fund F",
        fetched_guideline_text="some text", previous_rules_version="v7",
    )
    assert draft.proposed_rules_version == "v8"


def test_proposed_rules_version_falls_back_for_non_numeric_version(agent):
    draft = agent.codify(
        foundation_id="fund_g", foundation_name="Fund G",
        fetched_guideline_text="some text", previous_rules_version="initial",
    )
    assert draft.proposed_rules_version == "initial-draft"


def test_never_applies_to_the_live_rules_engine(agent):
    # The agent object must not expose any method that touches a foundation store
    # or applies anything -- it should only ever return a draft. This is a cheap
    # structural guard against someone accidentally wiring this agent to auto-apply.
    assert not hasattr(agent, "apply_human_reviewed_update")
    assert not hasattr(agent, "apply")


def test_required_application_fields_detected(agent):
    text = "Applicants must provide patient name and diagnosis code for verification."
    draft = agent.codify(
        foundation_id="fund_h", foundation_name="Fund H",
        fetched_guideline_text=text, previous_rules_version="v1",
    )
    assert "patient_full_name" in draft.proposed_required_application_fields
    assert "diagnosis_code" in draft.proposed_required_application_fields
