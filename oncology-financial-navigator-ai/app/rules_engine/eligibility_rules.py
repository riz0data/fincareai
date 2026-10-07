"""
Deterministic Eligibility Rules Engine

This module contains NO AI or LLM calls. It takes structured patient data
(already gathered by the Intake Agent) and evaluates it against explicit,
auditable eligibility rules for each partner foundation.

Design principle (from agent_architecture.md):
The Eligibility Matching Agent calls into this engine. The engine itself
is plain, testable, deterministic Python logic, so every match decision
can be explained and audited, with no hallucination risk.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MatchConfidence(Enum):
    MATCH = "match"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"  # triggers escalation to a human advocate


@dataclass
class PatientProfile:
    """Minimal structured fields needed for eligibility matching.
    In the real system this is populated by the Intake Agent from conversation."""
    diagnosis_code: Optional[str] = None          # e.g. ICD-10 code or cancer type string
    household_size: Optional[int] = None
    annual_household_income: Optional[float] = None
    insurance_status: Optional[str] = None         # e.g. "insured", "underinsured", "uninsured"
    state: Optional[str] = None
    treatment_type: Optional[str] = None           # e.g. "chemotherapy", "radiation"


@dataclass
class FoundationRule:
    """Mirrors the Foundation Reference entity from data_model.md.
    In production this is loaded from the daily-updated Foundation Reference
    store, not hardcoded -- hardcoded here only as a starting placeholder."""
    foundation_id: str
    name: str
    max_income_multiplier_of_poverty_line: float   # e.g. 5.0 = 500% of federal poverty line
    eligible_diagnoses: list = field(default_factory=list)  # empty list = all diagnoses eligible
    eligible_insurance_statuses: list = field(default_factory=list)
    rules_version: str = "v1"


# Federal poverty line placeholder by household size (2026 illustrative figures).
# In production this should be sourced/updated the same way Foundation Reference data is.
FEDERAL_POVERTY_LINE_BY_HOUSEHOLD_SIZE = {
    1: 15650,
    2: 21150,
    3: 26650,
    4: 32150,
}


def evaluate_eligibility(patient: PatientProfile, foundation: FoundationRule) -> MatchConfidence:
    """
    Evaluates a single patient against a single foundation's rules.
    Returns MATCH, NO_MATCH, or AMBIGUOUS (ambiguous = send to human advocate).
    """

    # Missing critical data -> cannot decide automatically -> escalate, don't guess.
    if patient.annual_household_income is None or patient.household_size is None:
        return MatchConfidence.AMBIGUOUS

    poverty_line = FEDERAL_POVERTY_LINE_BY_HOUSEHOLD_SIZE.get(patient.household_size)
    if poverty_line is None:
        # Household size outside our known table -- don't guess, escalate.
        return MatchConfidence.AMBIGUOUS

    income_limit = poverty_line * foundation.max_income_multiplier_of_poverty_line

    if patient.annual_household_income > income_limit:
        return MatchConfidence.NO_MATCH

    if foundation.eligible_diagnoses and patient.diagnosis_code not in foundation.eligible_diagnoses:
        return MatchConfidence.NO_MATCH

    if foundation.eligible_insurance_statuses and patient.insurance_status not in foundation.eligible_insurance_statuses:
        return MatchConfidence.NO_MATCH

    return MatchConfidence.MATCH


def match_all_foundations(patient: PatientProfile, foundations: list) -> dict:
    """Runs a patient against every known foundation. Returns a dict of
    foundation_id -> MatchConfidence, exactly the shape needed to populate
    the Eligibility Match entity from data_model.md."""
    results = {}
    for foundation in foundations:
        results[foundation.foundation_id] = evaluate_eligibility(patient, foundation)
    return results


# --- Adapter: build a FoundationRule from a live FoundationReferenceStore record --------
# This is what connects the deterministic rules engine to the daily-updated Foundation
# Reference store (app/data/foundation_reference_store.py), instead of relying on
# hardcoded foundation data. If the store returns None (foundation missing or currently
# blocked due to a pending unreviewed change), callers must treat that as "cannot match
# against this foundation right now" and escalate/skip, never fall back to guessing.
def foundation_rule_from_reference_record(record) -> "FoundationRule":
    """record is a FoundationReferenceRecord from foundation_reference_store.py.
    Import is intentionally deferred/duck-typed here to avoid a circular import
    between the rules engine and the data layer."""
    rules = record.eligibility_rules
    return FoundationRule(
        foundation_id=record.foundation_id,
        name=record.name,
        max_income_multiplier_of_poverty_line=rules.get("max_income_multiplier_of_poverty_line", 0.0),
        eligible_diagnoses=rules.get("eligible_diagnoses", []),
        eligible_insurance_statuses=rules.get("eligible_insurance_statuses", []),
        rules_version=record.rules_version,
    )
