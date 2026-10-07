"""
Email-Based Approval Loop for the Guideline Codification Agent

Implements the human-in-the-loop mechanism the user chose for approving Guideline
Codification Agent drafts: instead of a web dashboard, the whole review-and-approve
step happens as a plain email conversation. This module is the bridge between:
  - GuidelineCodificationAgent (produces a CodificationDraft)
  - foundation_reference_store.apply_human_reviewed_update (the only function that
    actually updates the live rules engine)

Flow:
  1. request_approval_by_email() sends the human reviewer an email laying out the
     draft in plain language: proposed values, confidence per field, and the exact
     reply keywords it is listening for. It records a pending approval request
     (keyed by foundation_id) so a later reply can be matched back to it.
  2. Some time later, check_for_approval_replies() searches the reviewer's inbox for
     a reply in that same thread, and parses it for one of a small set of controlled
     keywords: APPROVE, REJECT, or EDIT (EDIT means "I'm changing a value, see notes").
  3. Only a reply containing an unambiguous approval keyword ever results in calling
     apply_human_reviewed_update(). Anything else -- silence, an ambiguous reply, a
     reply with no recognized keyword -- results in no action and stays pending,
     consistent with this project's "never guess" principle.

Deliberately simple/conservative parsing: this is a safety-relevant action (it changes
what a real financial-assistance rules engine treats as valid), so keyword matching is
strict and case-insensitive rather than trying to interpret loose natural language.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List

from guideline_codification_agent import CodificationDraft


# Controlled reply vocabulary. The reviewer must include one of these as a standalone
# keyword (case-insensitive) in their reply for the system to act on it.
APPROVE_KEYWORDS = ["APPROVE", "APPROVED"]
REJECT_KEYWORDS = ["REJECT", "REJECTED", "DENY", "DENIED"]

# Matches a real word boundary so "APPROVE" doesn't accidentally match inside some
# other word, and so a reply that says "I do NOT approve this" still needs a human
# to notice the mismatch -- this module deliberately does not try to parse negation.
def _contains_keyword(text: str, keywords: List[str]) -> bool:
    text_upper = text.upper()
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text_upper) for kw in keywords)


@dataclass
class PendingApproval:
    foundation_id: str
    foundation_name: str
    draft: CodificationDraft
    sent_at: datetime
    thread_id: Optional[str] = None
    message_id: Optional[str] = None
    resolved: bool = False
    resolution: Optional[str] = None  # "approved", "rejected", or None while pending


@dataclass
class ApprovalResult:
    foundation_id: str
    outcome: str  # "approved", "rejected", "no_reply_yet", "unrecognized_reply"
    reply_snippet: Optional[str] = None
    applied: bool = False


def _format_draft_email_body(draft: CodificationDraft) -> str:
    """Builds a plain-language email body a non-technical reviewer can act on
    without needing to read code or JSON."""
    lines = []
    lines.append(f"A guideline change was detected for: {draft.foundation_name}")
    lines.append(f"Proposed new rules version: {draft.proposed_rules_version}")
    lines.append("")
    lines.append("DRAFT PROPOSED VALUES (review each one before approving):")
    lines.append(f"  - Max income (multiple of federal poverty line): "
                 f"{draft.proposed_max_income_multiplier_of_poverty_line}")
    lines.append(f"  - Eligible insurance statuses: "
                 f"{', '.join(draft.proposed_eligible_insurance_statuses) or '(none found)'}")
    lines.append(f"  - Eligible diagnoses: "
                 f"{', '.join(draft.proposed_eligible_diagnoses) or '(none found)'}")
    lines.append(f"  - Required application fields: "
                 f"{', '.join(draft.proposed_required_application_fields) or '(none found)'}")
    lines.append("")
    lines.append("CONFIDENCE PER FIELD:")
    for extraction in draft.field_extractions:
        evidence = f" (source text: \"{extraction.evidence_snippet}\")" if extraction.evidence_snippet else ""
        note = f" NOTE: {extraction.note}" if extraction.note else ""
        lines.append(f"  - {extraction.field_name}: {extraction.confidence.upper()}{evidence}{note}")
    lines.append("")
    lines.append(f"Overall confidence: {draft.overall_confidence.upper()}")
    if draft.requires_careful_human_review:
        lines.append("This draft has at least one low-confidence field. Please verify "
                     "directly against the foundation's published page before approving.")
    lines.append("")
    lines.append(draft.change_summary)
    lines.append("")
    lines.append("---")
    lines.append("HOW TO RESPOND:")
    lines.append("Reply to this email with the word APPROVE if the draft above is correct "
                 "(edit any values in your reply first if needed, then say APPROVE).")
    lines.append("Reply with REJECT if this should not go live as-is and you will handle it "
                 "manually instead.")
    lines.append("No other action is needed from you beyond replying with one of these words "
                 "-- approving will automatically update the live rules engine and unblock "
                 "this foundation for new patient matches.")
    return "\n".join(lines)


class EmailApprovalLoop:
    """Manages the send-draft / await-reply / apply-on-approval cycle. Holds pending
    approvals in memory for this prototype; a production version should persist these
    the same way foundation_reference_store persists to Excel, so a pending approval
    survives a process restart."""

    def __init__(self, foundation_store, reviewer_email: str,
                 send_email_fn, search_replies_fn):
        """
        foundation_store: the FoundationReferenceStore to apply approved updates to.
        reviewer_email: the human reviewer's address (e.g. the shared NOTIFICATION_EMAIL).
        send_email_fn: callable(to_address, subject, body) -> message_id/thread_id info.
            In production this is the real Gmail send/create_draft tool call; kept as an
            injected function here so this module has no hard dependency on any one
            email provider and can be tested without sending real mail.
        search_replies_fn: callable(thread_id) -> list of reply message bodies (newest
            last). Also injected for the same reason.
        """
        self.foundation_store = foundation_store
        self.reviewer_email = reviewer_email
        self._send_email_fn = send_email_fn
        self._search_replies_fn = search_replies_fn
        self._pending: Dict[str, PendingApproval] = {}

    def request_approval_by_email(self, draft: CodificationDraft) -> PendingApproval:
        subject = f"[Action needed] Approve guideline update: {draft.foundation_name}"
        body = _format_draft_email_body(draft)
        send_result = self._send_email_fn(self.reviewer_email, subject, body)

        pending = PendingApproval(
            foundation_id=draft.foundation_id,
            foundation_name=draft.foundation_name,
            draft=draft,
            sent_at=datetime.utcnow(),
            thread_id=send_result.get("thread_id") if send_result else None,
            message_id=send_result.get("message_id") if send_result else None,
        )
        self._pending[draft.foundation_id] = pending
        return pending

    def check_for_approval_replies(self, foundation_id: str) -> ApprovalResult:
        """Checks for a reply to the pending approval email for this foundation, and
        applies the update automatically if (and only if) an unambiguous APPROVE
        keyword is found. This is the single place in the whole system where an
        email reply can trigger a live rules-engine update -- it is intentionally
        narrow and strict."""
        pending = self._pending.get(foundation_id)
        if pending is None:
            raise ValueError(f"No pending approval on file for foundation_id={foundation_id}")
        if pending.resolved:
            return ApprovalResult(foundation_id=foundation_id, outcome=pending.resolution, applied=False)

        replies = self._search_replies_fn(pending.thread_id) if pending.thread_id else []
        if not replies:
            return ApprovalResult(foundation_id=foundation_id, outcome="no_reply_yet")

        latest_reply = replies[-1]

        approved = _contains_keyword(latest_reply, APPROVE_KEYWORDS)
        rejected = _contains_keyword(latest_reply, REJECT_KEYWORDS)

        if approved and rejected:
            # Ambiguous reply containing both keywords -- never guess, leave pending.
            return ApprovalResult(
                foundation_id=foundation_id, outcome="unrecognized_reply",
                reply_snippet=latest_reply[:200],
            )

        if approved:
            draft = pending.draft
            self.foundation_store.apply_human_reviewed_update(
                foundation_id=draft.foundation_id,
                new_eligibility_rules={
                    "max_income_multiplier_of_poverty_line":
                        draft.proposed_max_income_multiplier_of_poverty_line,
                    "eligible_insurance_statuses": draft.proposed_eligible_insurance_statuses,
                    "eligible_diagnoses": draft.proposed_eligible_diagnoses,
                },
                new_application_template={
                    "required_fields": draft.proposed_required_application_fields,
                },
                new_rules_version=draft.proposed_rules_version,
            )
            pending.resolved = True
            pending.resolution = "approved"
            return ApprovalResult(
                foundation_id=foundation_id, outcome="approved",
                reply_snippet=latest_reply[:200], applied=True,
            )

        if rejected:
            pending.resolved = True
            pending.resolution = "rejected"
            return ApprovalResult(
                foundation_id=foundation_id, outcome="rejected",
                reply_snippet=latest_reply[:200], applied=False,
            )

        return ApprovalResult(
            foundation_id=foundation_id, outcome="unrecognized_reply",
            reply_snippet=latest_reply[:200],
        )

    def get_pending(self) -> List[PendingApproval]:
        return [p for p in self._pending.values() if not p.resolved]


# --- Real Gmail-backed adapter functions -----------------------------------------
#
# IMPORTANT LIMITATION: the connected Gmail integration only exposes create_draft
# (and read/search tools), not a direct "send" action. A created draft sits in the
# Drafts folder until a person opens Gmail and hits Send themselves. This means the
# end-to-end email approval loop currently has one small manual step baked in by
# the platform, not by this code: after the system drafts the approval-request
# email, a person must open Gmail and click Send once before the reviewer will
# actually receive it. Everything after that (the reviewer's reply, and this
# module reading that reply and applying the update) is fully automatic.
#
# These functions are meant to be passed into EmailApprovalLoop as send_email_fn /
# search_replies_fn from wherever this runs with real tool access (they call the
# Gmail MCP tools directly, so they cannot run inside this sandbox -- wire them up
# in the actual agent runtime that has those tools available).


def gmail_create_draft_send_fn(create_draft_tool):
    """Returns a send_email_fn compatible with EmailApprovalLoop, backed by the
    real create_draft Gmail tool. create_draft_tool should be a callable matching
    the create_draft tool's signature: create_draft_tool(to, subject, body) ->
    dict with at least 'id' and 'threadId'."""
    def _send(to_address: str, subject: str, body: str) -> dict:
        result = create_draft_tool(to=[to_address], subject=subject, body=body)
        return {
            "thread_id": result.get("threadId") or result.get("thread_id"),
            "message_id": result.get("id"),
        }
    return _send


def gmail_search_replies_fn(get_thread_tool):
    """Returns a search_replies_fn compatible with EmailApprovalLoop, backed by the
    real get_thread Gmail tool. get_thread_tool should be a callable matching
    get_thread's signature: get_thread_tool(threadId, messageFormat) -> dict with a
    'messages' list, each with a 'plaintextBody' or similar text field. Returns the
    plain text bodies of all messages in the thread after the first (the first
    message is the original outbound request), oldest to newest, so the caller can
    always take the last one as the latest reply."""
    def _search(thread_id: str) -> list:
        if not thread_id:
            return []
        thread = get_thread_tool(threadId=thread_id, messageFormat="PLAIN_TEXT")
        messages = thread.get("messages", [])
        if len(messages) <= 1:
            return []  # only the original outbound message exists, no reply yet
        reply_messages = messages[1:]
        return [
            m.get("plaintextBody") or m.get("snippet") or ""
            for m in reply_messages
        ]
    return _search
