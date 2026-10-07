"""
Tests for the deterministic eligibility rules engine (app/rules_engine/eligibility_rules.py).

These are the most safety-critical tests in the whole suite: this engine is the one
place that decides whether a real patient matches a real foundation, so it must never
guess. Every ambiguous-data case must come back AMBIGUOUS (escalate to a human), never
a guessed MATCH or NO_MATCH.
"""

import pytest

from eligibility_rules import (
    PatientProfile,
    FoundationRule,
    MatchConfidence,
    evaluate_eligibility,
    match_all_foundations,
    foundation_rule_from_reference_record,
)


@pytest.fixture
def generous_foundation():
    return FoundationRule(
        foundation_id="generous_fund",
        name="Generous Fund",
        max_income_multiplier_of_poverty_line=5.0,
    )


@pytest.fixture
def strict_foundation():
    return FoundationRule(
        foundation_id="strict_fund",
        name="Strict Fund",
        max_income_multiplier_of_poverty_line=2.0,
        eligible_diagnoses=["breast cancer"],
        eligible_insurance_statuses=["uninsured", "underinsured"],
    )


def test_match_within_income_limit(generous_foundation):
    patient = PatientProfile(household_size=1, annual_household_income=30000)
    assert evaluate_eligibility(patient, generous_foundation) == MatchConfidence.MATCH


def test_no_match_income_too_high(strict_foundation):
    patient = PatientProfile(
        household_size=1, annual_household_income=200000,
        diagnosis_code="breast cancer", insurance_status="uninsured",
    )
    assert evaluate_eligibility(patient, strict_foundation) == MatchConfidence.NO_MATCH


def test_no_match_wrong_diagnosis(strict_foundation):
    patient = PatientProfile(
        household_size=1, annual_household_income=20000,
        diagnosis_code="lung cancer", insurance_status="uninsured",
    )
    assert evaluate_eligibility(patient, strict_foundation) == MatchConfidence.NO_MATCH


def test_no_match_wrong_insurance(strict_foundation):
    patient = PatientProfile(
        household_size=1, annual_household_income=20000,
        diagnosis_code="breast cancer", insurance_status="private",
    )
    assert evaluate_eligibility(patient, strict_foundation) == MatchConfidence.NO_MATCH


def test_match_all_conditions_met(strict_foundation):
    patient = PatientProfile(
        household_size=1, annual_household_income=20000,
        diagnosis_code="breast cancer", insurance_status="uninsured",
    )
    assert evaluate_eligibility(patient, strict_foundation) == MatchConfidence.MATCH


def test_ambiguous_missing_income(generous_foundation):
    patient = PatientProfile(household_size=1, annual_household_income=None)
    assert evaluate_eligibility(patient, generous_foundation) == MatchConfidence.AMBIGUOUS


def test_ambiguous_missing_household_size(generous_foundation):
    patient = PatientProfile(household_size=None, annual_household_income=30000)
    assert evaluate_eligibility(patient, generous_foundation) == MatchConfidence.AMBIGUOUS


def test_ambiguous_unknown_household_size(generous_foundation):
    patient = PatientProfile(household_size=99, annual_household_income=30000)
    assert evaluate_eligibility(patient, generous_foundation) == MatchConfidence.AMBIGUOUS


def test_foundation_with_no_diagnosis_or_insurance_restriction_matches_anyone(generous_foundation):
    patient = PatientProfile(
        household_size=2, annual_household_income=50000,
        diagnosis_code="anything", insurance_status="anything",
    )
    assert evaluate_eligibility(patient, generous_foundation) == MatchConfidence.MATCH


def test_match_all_foundations_returns_one_result_per_foundation(generous_foundation, strict_foundation):
    patient = PatientProfile(
        household_size=1, annual_household_income=20000,
        diagnosis_code="breast cancer", insurance_status="uninsured",
    )
    results = match_all_foundations(patient, [generous_foundation, strict_foundation])
    assert results == {
        "generous_fund": MatchConfidence.MATCH,
        "strict_fund": MatchConfidence.MATCH,
    }


class _FakeRecord:
    def __init__(self, foundation_id, name, eligibility_rules, rules_version="v1"):
        self.foundation_id = foundation_id
        self.name = name
        self.eligibility_rules = eligibility_rules
        self.rules_version = rules_version


def test_foundation_rule_from_reference_record_adapter():
    record = _FakeRecord(
        foundation_id="fund_x", name="Fund X",
        eligibility_rules={
            "max_income_multiplier_of_poverty_line": 4.0,
            "eligible_diagnoses": ["lung cancer"],
            "eligible_insurance_statuses": ["medicaid"],
        },
        rules_version="v3",
    )
    rule = foundation_rule_from_reference_record(record)
    assert rule.foundation_id == "fund_x"
    assert rule.max_income_multiplier_of_poverty_line == 4.0
    assert rule.eligible_diagnoses == ["lung cancer"]
    assert rule.eligible_insurance_statuses == ["medicaid"]
    assert rule.rules_version == "v3"


def test_foundation_rule_from_reference_record_defaults_missing_fields():
    record = _FakeRecord(foundation_id="fund_y", name="Fund Y", eligibility_rules={})
    rule = foundation_rule_from_reference_record(record)
    assert rule.max_income_multiplier_of_poverty_line == 0.0
    assert rule.eligible_diagnoses == []
    assert rule.eligible_insurance_statuses == []
