"""
Form Preparation Agent

Per agent_architecture.md (Agent 3):
Role: Prepares the actual application, populating the correct foundation-specific
form with the patient's structured data, modeled on Dollar For's proven auto-fill
pattern.

Responsibilities:
  - Select the correct application template for the matched foundation.
  - Populate all required fields accurately from the structured patient data.
  - Assemble any required supporting documentation checklist for the patient.
  - Pass the completed, unsubmitted application to human review.

Explicitly does not: submit any application. Output always stops at
"ready for human review."

This agent contains NO AI/LLM calls -- it is a deterministic mapping step,
consistent with the project's principle that only the conversational intake
layer needs an LLM.

UPDATED: this agent now reads application templates from the live
FoundationReferenceStore (app/data/foundation_reference_store.py), the same
store the daily change ticker updates, instead of a hardcoded dictionary. If
the store has no active (non-blocked) record for a foundation, this agent
refuses to prepare a form, exactly as it already refused for unknown
foundations, since a blocked foundation means its data may be stale or
mid-review per data_model.md.
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules_engine"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

from eligibility_rules import PatientProfile
from entities import Application
from foundation_reference_store import FoundationReferenceStore


class FormPreparationAgent:
    """Takes a matched foundation_id and a completed PatientProfile, and produces
    an Application entity populated and ready for human review. Never submits.
    Reads its application template live from a FoundationReferenceStore instance."""

    def __init__(self, foundation_store: FoundationReferenceStore):
        self.foundation_store = foundation_store

    def prepare_application(
        self,
        case_id: str,
        foundation_id: str,
        profile: PatientProfile,
        patient_full_name: Optional[str] = None,
    ) -> Application:
        record = self.foundation_store.get_active_foundation(foundation_id)

        if record is None:
            # Either unknown, or currently blocked pending human review of a
            # detected change (data_model.md daily ticker behavior). Either way,
            # do not guess or fabricate a form -- escalate instead.
            raise ValueError(
                f"No active application template available for foundation_id='{foundation_id}'. "
                "This foundation is either unknown or currently blocked pending human review "
                "of a detected change. This case should be escalated to a human rather than "
                "proceeding, per orchestration.md failure handling for Foundation Reference data."
            )

        template = record.application_template
        required_fields = template.get("required_fields", [])

        source_values = {
            "patient_full_name": patient_full_name,
            "diagnosis_code": profile.diagnosis_code,
            "household_size": profile.household_size,
            "annual_household_income": profile.annual_household_income,
            "insurance_status": profile.insurance_status,
            "state": profile.state,
        }

        form_data = {}
        missing_fields = []
        for field_name in required_fields:
            value = source_values.get(field_name)
            form_data[field_name] = value
            if value is None:
                missing_fields.append(field_name)

        application = Application(
            case_id=case_id,
            foundation_id=foundation_id,
            form_data=form_data,
            status="ready_for_review" if not missing_fields else "incomplete_needs_data",
        )

        if missing_fields:
            application.form_data["_missing_fields"] = missing_fields

        return application

    def get_supporting_documents_checklist(self, foundation_id: str) -> list:
        record = self.foundation_store.get_active_foundation(foundation_id)
        if record is None:
            return []
        return record.application_template.get("supporting_documents_checklist", [])
