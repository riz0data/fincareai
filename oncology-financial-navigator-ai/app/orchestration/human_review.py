"""
Human Review and Targeted Re-Contact

Per agent_architecture.md, Human Review and Sign-Off is deliberately NOT an agent --
it is the accountability checkpoint where a person checks every prepared application
for accuracy and appropriateness before submission. This module implements that step
as code, plus the targeted re-contact flow for when a reviewer finds missing or
inconsistent data.

Design principle for re-contact (per this session's discussion): when a human reviewer
catches a gap, the system does NOT restart intake from scratch. It reopens the case in
a narrow, targeted way -- asking the patient only for the specific missing or unclear
fields -- and re-contacts them through whichever channel they originally used. This
keeps the patient experience respectful of their time and avoids the frustration of
re-answering questions they already answered.

Flow:
  1. Reviewer examines a prepared Application (from form_preparation_agent.py).
  2. If complete and correct -> approve -> status becomes "approved_ready_to_submit".
  3. If gaps found -> reviewer specifies exactly which fields are missing/unclear ->
     a RecontactRequest is generated -> patient is re-contacted through their original
     channel, asked ONLY those fields -> answers come back in -> the Application is
     updated in place -> case returns to the reviewer's queue for a final check.
  4. This can loop more than once if needed, but each loop is narrow and auditable.

All alerts route through the same shared NOTIFICATION_EMAIL used everywhere else in
this codebase, defined once in app/data/foundation_reference_store.py.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
from foundation_reference_store import send_email_alert


class ReviewOutcome(Enum):
    APPROVED = "approved_ready_to_submit"
    SENT_BACK_FOR_RECONTACT = "sent_back_for_recontact"


class RecontactChannel(Enum):
    PHONE_CALL = "phone_call"
    SMS = "sms"
    EMAIL = "email"
    PORTAL_MESSAGE = "portal_message"


def recontact_channel_from_patient_preference(preferred_contact_channel):
    """Maps the patient's stated preference, captured once during intake
    (see intake_agent.py's CONTACT_PREFERENCE_QUESTION / stub_extract_contact_channel),
    onto a RecontactChannel. Falls back to PHONE_CALL only if the patient's
    preference was never captured or came back unclear, since a phone call is the
    most universally reachable default -- never silently drop a case with no
    contact path."""
    if preferred_contact_channel is None:
        return RecontactChannel.PHONE_CALL
    try:
        return RecontactChannel(preferred_contact_channel)
    except ValueError:
        return RecontactChannel.PHONE_CALL


@dataclass
class RecontactRequest:
    case_id: str
    missing_fields: List[str]
    reviewer_note: str
    channel: RecontactChannel
    created_at: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_answers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ReviewDecision:
    case_id: str
    outcome: ReviewOutcome
    reviewer_name: str
    notes: str
    recontact_request: Optional[RecontactRequest] = None
    decided_at: datetime = field(default_factory=datetime.utcnow)


class HumanReviewStep:
    """Represents the human review checkpoint. Not an agent -- every decision here is
    made by a person; this class just structures and records that decision, and drives
    the targeted re-contact flow when needed."""

    def __init__(self):
        self._recontact_requests: Dict[str, RecontactRequest] = {}
        self._audit_log: List[dict] = []

    def review_application(
        self,
        case_id: str,
        application_status: str,
        application_missing_fields: Optional[List[str]],
        reviewer_name: str,
        approve: bool,
        notes: str = "",
        original_contact_channel: RecontactChannel = RecontactChannel.PHONE_CALL,
    ) -> ReviewDecision:
        """
        application_status / application_missing_fields come straight off the
        Application entity produced by form_preparation_agent.py (its "_missing_fields"
        key, if present in form_data).
        approve: the human reviewer's actual decision. This function never decides on
        its own -- it only records and routes what the human decided.
        """
        if approve:
            decision = ReviewDecision(
                case_id=case_id,
                outcome=ReviewOutcome.APPROVED,
                reviewer_name=reviewer_name,
                notes=notes,
            )
            self._audit_log.append({
                "case_id": case_id,
                "event": "approved_ready_to_submit",
                "reviewer": reviewer_name,
                "timestamp": decision.decided_at,
            })
            return decision

        # Reviewer is sending it back. Figure out exactly what's missing, preferring
        # what the reviewer explicitly flagged over what the form-prep agent flagged,
        # since a human may catch things (e.g. an inconsistent answer) automation can't.
        missing = application_missing_fields or []
        if not missing:
            missing = ["reviewer_flagged_field_not_specified"]

        recontact = RecontactRequest(
            case_id=case_id,
            missing_fields=missing,
            reviewer_note=notes,
            channel=original_contact_channel,
        )
        self._recontact_requests[case_id] = recontact

        decision = ReviewDecision(
            case_id=case_id,
            outcome=ReviewOutcome.SENT_BACK_FOR_RECONTACT,
            reviewer_name=reviewer_name,
            notes=notes,
            recontact_request=recontact,
        )

        self._audit_log.append({
            "case_id": case_id,
            "event": "sent_back_for_recontact",
            "reviewer": reviewer_name,
            "missing_fields": missing,
            "channel": original_contact_channel.value,
            "timestamp": decision.decided_at,
        })

        send_email_alert(
            subject=f"Case {case_id}: sent back for targeted re-contact",
            body=(
                f"Reviewer {reviewer_name} sent case {case_id} back for re-contact.\n"
                f"Missing/unclear fields: {', '.join(missing)}\n"
                f"Reviewer note: {notes}\n"
                f"Patient will be re-contacted via {original_contact_channel.value}, asked ONLY "
                f"for the fields above -- intake is not restarted from scratch."
            ),
        )

        return decision

    def resolve_recontact(self, case_id: str, answers: Dict[str, str]) -> RecontactRequest:
        """Called once the patient has responded with the specific missing fields.
        Only accepts answers for fields that were actually requested, so a re-contact
        stays narrow and doesn't silently overwrite unrelated data."""
        request = self._recontact_requests.get(case_id)
        if request is None:
            raise ValueError(f"No open recontact request for case_id={case_id}")

        unexpected = [f for f in answers if f not in request.missing_fields]
        if unexpected:
            raise ValueError(
                f"Received answers for fields that were not requested: {unexpected}. "
                "A targeted recontact should only update the specific fields flagged "
                "by the reviewer."
            )

        request.resolved_answers.update(answers)
        still_missing = [f for f in request.missing_fields if f not in request.resolved_answers]

        if not still_missing:
            request.resolved = True
            self._audit_log.append({
                "case_id": case_id,
                "event": "recontact_resolved_returned_to_review_queue",
                "timestamp": datetime.utcnow(),
            })

        return request

    def get_audit_log(self) -> List[dict]:
        return list(self._audit_log)
