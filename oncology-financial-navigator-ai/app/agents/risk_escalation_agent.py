"""
Risk and Escalation Agent

Per agent_architecture.md (Agent 4):
Role: The judgment layer. Handles the cases that do not cleanly resolve through
deterministic rules, and is the trigger point for pulling in a live human.

Responsibilities:
  - Reason through borderline or ambiguous eligibility cases (e.g. weighing whether
    to pursue two foundations in parallel or in sequence).
  - Detect signals of distress, urgency, or complexity that warrant immediate live
    human contact rather than continued AI conversation.
  - Flag cases for the practice-facing shadow dashboard when a case needs human
    attention.

Explicitly does not: override a human reviewer's final decision. This agent only
recommends and escalates; a human always makes the final call (Human Review and
Sign-Off, per agent_architecture.md, is deliberately not an agent).

This agent sends its escalation alerts through the same single shared notification
address used everywhere else in the system (NOTIFICATION_EMAIL, defined once in
app/data/foundation_reference_store.py), never a hardcoded address of its own.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules_engine"))

from foundation_reference_store import send_email_alert, NOTIFICATION_EMAIL
from eligibility_rules import MatchConfidence


class UrgencyLevel(Enum):
    ROUTINE = "routine"          # ambiguous data, no distress signals -- queue for normal review
    PRIORITY = "priority"        # borderline eligibility, time-sensitive, or repeated ambiguity
    IMMEDIATE = "immediate"      # distress/crisis language detected -- needs a live human now


# Simple, explicit keyword-based distress detection. This is intentionally NOT an LLM
# call: distress detection is exactly the kind of judgment where a false negative is
# dangerous, so we start with a conservative, auditable keyword list that a human can
# read and extend, rather than an opaque model decision. This can be layered with a
# real LLM-based classifier later, but should never be the ONLY signal, per the
# project's core principle that safety-relevant judgment stays inspectable.
DISTRESS_KEYWORDS = [
    "can't afford", "cannot afford", "losing my home", "eviction", "evicted",
    "can't pay rent", "cannot pay rent", "skipping meals", "skip meals",
    "suicidal", "want to give up", "can't do this anymore", "cannot do this anymore",
    "utilities shut off", "shut off my", "no money for", "desperate", "emergency",
    "about to lose", "final notice", "collections",
]

URGENCY_KEYWORDS = [
    "surgery next week", "surgery tomorrow", "treatment starts", "starts monday",
    "deadline", "due tomorrow", "due today", "running out of time", "asap",
    "as soon as possible", "urgent",
]


@dataclass
class EscalationRecommendation:
    case_id: str
    urgency_level: UrgencyLevel
    reasons: List[str]
    recommended_action: str
    created_at: datetime = field(default_factory=datetime.utcnow)


class RiskAndEscalationAgent:
    """Reasons over ambiguous eligibility outcomes and free-text conversation signals
    to produce an EscalationRecommendation. Never makes a final decision itself --
    always hands off to a human, per agent_architecture.md."""

    def __init__(self, notify: bool = True):
        self.notify = notify

    def _detect_keywords(self, text: str, keyword_list: List[str]) -> List[str]:
        if not text:
            return []
        lowered = text.lower()
        return [kw for kw in keyword_list if kw in lowered]

    def assess(
        self,
        case_id: str,
        match_confidence: Optional[MatchConfidence] = None,
        candidate_match_count: int = 0,
        conversation_text: str = "",
        near_miss_reason: Optional[str] = None,
    ) -> EscalationRecommendation:
        """
        match_confidence: the MatchConfidence result from the rules engine, if available.
        candidate_match_count: how many foundations came back as candidates (0, 1, or many).
        conversation_text: raw free-text from the intake conversation, scanned for
            distress/urgency signals. This agent only pattern-matches on it; it does not
            interpret meaning the way the Intake Agent's LLM layer does.
        near_miss_reason: optional human-readable note on WHY a case is borderline, e.g.
            "household income is 5 percent above this foundation's cutoff."
        """
        reasons: List[str] = []
        urgency = UrgencyLevel.ROUTINE

        distress_hits = self._detect_keywords(conversation_text, DISTRESS_KEYWORDS)
        urgency_hits = self._detect_keywords(conversation_text, URGENCY_KEYWORDS)

        if distress_hits:
            urgency = UrgencyLevel.IMMEDIATE
            reasons.append(
                f"Distress language detected in patient conversation: {', '.join(distress_hits)}."
            )

        if urgency_hits and urgency != UrgencyLevel.IMMEDIATE:
            urgency = UrgencyLevel.PRIORITY
            reasons.append(
                f"Time-sensitive language detected: {', '.join(urgency_hits)}."
            )
        elif urgency_hits:
            reasons.append(
                f"Time-sensitive language also present: {', '.join(urgency_hits)}."
            )

        if match_confidence == MatchConfidence.AMBIGUOUS:
            reasons.append("Eligibility rules engine could not reach a confident match (ambiguous or missing data).")
            if urgency == UrgencyLevel.ROUTINE:
                urgency = UrgencyLevel.ROUTINE

        if near_miss_reason:
            reasons.append(f"Borderline eligibility: {near_miss_reason}.")
            if urgency == UrgencyLevel.ROUTINE:
                urgency = UrgencyLevel.PRIORITY

        if candidate_match_count > 1:
            reasons.append(
                f"{candidate_match_count} candidate foundations matched; sequencing or parallel "
                "pursuit needs a human decision rather than an automatic pick."
            )

        if not reasons:
            reasons.append("No specific risk signals detected; routing for standard review only.")

        if urgency == UrgencyLevel.IMMEDIATE:
            recommended_action = (
                "Contact patient directly and immediately; do not continue automated conversation."
            )
        elif urgency == UrgencyLevel.PRIORITY:
            recommended_action = (
                "Route to Patient Financial Advocate for priority review ahead of the normal queue."
            )
        else:
            recommended_action = "Route to standard human review queue."

        recommendation = EscalationRecommendation(
            case_id=case_id,
            urgency_level=urgency,
            reasons=reasons,
            recommended_action=recommended_action,
        )

        if self.notify:
            self._send_escalation_alert(recommendation)

        return recommendation

    def _send_escalation_alert(self, rec: EscalationRecommendation) -> None:
        subject = f"[{rec.urgency_level.value.upper()}] Case {rec.case_id} escalated for human review"
        body = (
            f"Case {rec.case_id} has been escalated by the Risk and Escalation Agent.\n\n"
            f"Urgency level: {rec.urgency_level.value}\n"
            f"Reasons:\n" + "\n".join(f"  - {r}" for r in rec.reasons) + "\n\n"
            f"Recommended action: {rec.recommended_action}\n\n"
            f"Reminder: this is a recommendation only. A human makes the final decision, "
            f"per agent_architecture.md. See the Human Operator Playbook, Alert 4."
        )
        send_email_alert(subject=subject, body=body)
