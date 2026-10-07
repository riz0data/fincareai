"""
Core Data Entities

Real code versions of the entities defined in data_model.md:
Patient Case, Eligibility Match, Escalation, Application, Outcome,
and Foundation Reference.

These are plain dataclasses for now (no database wiring yet) so the
orchestration and agent logic have real, typed objects to pass around.
Persistence (a real database) is a later step.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


class CaseStatus(Enum):
    IN_PROGRESS = "in_progress"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    ESCALATED = "escalated"
    SUBMITTED = "submitted"
    DORMANT = "dormant"          # repeated non-response, per orchestration.md
    COMPLETE = "complete"


class UrgencyTier(Enum):
    SAME_DAY = "same_day"
    STANDARD = "standard"


@dataclass
class PatientCase:
    case_id: str = field(default_factory=new_id)
    referring_practice_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: CaseStatus = CaseStatus.IN_PROGRESS
    patient_profile: Optional[object] = None   # a rules_engine.PatientProfile
    conversation_log: list = field(default_factory=list)


@dataclass
class EligibilityMatch:
    case_id: str
    matched_foundation_ids: list = field(default_factory=list)
    match_confidence: Optional[str] = None     # mirrors MatchConfidence.value
    rules_version: Optional[str] = None
    evaluated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Escalation:
    case_id: str
    reason: str = ""
    urgency_tier: UrgencyTier = UrgencyTier.STANDARD
    assigned_advocate_id: Optional[str] = None
    resolution: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None


@dataclass
class Application:
    case_id: str
    foundation_id: str = ""
    form_data: dict = field(default_factory=dict)
    status: str = "draft"                       # draft -> ready_for_review -> submitted
    human_reviewer_id: Optional[str] = None
    review_timestamp: Optional[datetime] = None
    reviewer_acknowledgment: bool = False        # must be True before submission


@dataclass
class Outcome:
    case_id: str
    foundation_id: str = ""
    funds_approved_amount: Optional[float] = None
    funds_applied_timestamp: Optional[datetime] = None
    verified: bool = False                       # True only if confirmed against actual bill
    time_to_outcome_days: Optional[float] = None


@dataclass
class FoundationReference:
    foundation_id: str
    name: str = ""
    eligibility_rules: dict = field(default_factory=dict)
    application_template: dict = field(default_factory=dict)
    rules_version: str = "v1"
    last_verified_at: Optional[datetime] = None
    source_reference: Optional[str] = None
