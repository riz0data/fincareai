"""
Daily Batch Job Runner: Foundation Reference Maintenance

Chains together the fully-automated portion of the daily batch job described in
orchestration.md ("Daily Batch Job: Foundation Reference Maintenance"):

  1. run_daily_check() on the Foundation Reference Store, per foundation.
  2. On change_detected only: run the Guideline Codification Agent against the newly
     fetched content to produce a draft.
  3. Hand that draft to the Email Approval Loop to create the Gmail draft requesting
     human approval.

This is as far as automation goes without a person: per the platform limitation
documented in local_setup_and_testing.md section 7a, a human must still open Gmail and
click Send once to actually deliver the approval-request email. Everything up to that
point, and everything after the human's APPROVE/REJECT reply, is handled by this module
and email_approval_loop.py respectively, with no other manual step in between.

This module intentionally does NOT decide when to run (no scheduler baked in) -- call
run_daily_batch_job() from whatever scheduling mechanism the deployment uses (cron, a
scheduled cloud function, etc.), once per day.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from guideline_codification_agent import GuidelineCodificationAgent, CodificationDraft
from email_approval_loop import EmailApprovalLoop, PendingApproval


@dataclass
class BatchJobResult:
    foundation_id: str
    check_outcome: str  # "no_change", "change_detected", "fetch_failed"
    draft: Optional[CodificationDraft] = None
    pending_approval: Optional[PendingApproval] = None


def run_daily_batch_job(
    foundation_store,
    fetch_source_fns: Dict[str, Callable[[], str]],
    codification_agent: GuidelineCodificationAgent,
    approval_loop: EmailApprovalLoop,
    known_diagnosis_keywords: Optional[List[str]] = None,
    previous_guideline_texts: Optional[Dict[str, str]] = None,
) -> List[BatchJobResult]:
    """
    Runs the full automated batch flow across every registered foundation.

    foundation_store: the FoundationReferenceStore holding all registered foundations.
    fetch_source_fns: maps foundation_id -> a callable fetching that foundation's current
        published source content (same shape run_daily_check already expects).
    codification_agent: a GuidelineCodificationAgent instance.
    approval_loop: an EmailApprovalLoop instance already wired to the real (or test)
        send/search functions and this same foundation_store.
    known_diagnosis_keywords: optional shared diagnosis keyword list passed through to
        the codification agent for every foundation checked this run.
    previous_guideline_texts: optional map of foundation_id -> last known raw guideline
        text, purely so the codification agent can produce a more informative
        change_summary; safe to omit.

    Returns one BatchJobResult per foundation checked, so a caller (or a test) can
    inspect exactly what happened without needing to re-derive it from logs.
    """
    results: List[BatchJobResult] = []
    previous_guideline_texts = previous_guideline_texts or {}

    for foundation_id, fetch_fn in fetch_source_fns.items():
        record = foundation_store._records.get(foundation_id)
        if record is None:
            raise ValueError(f"Unknown foundation_id in fetch_source_fns: {foundation_id}")

        previous_rules_version = record.rules_version

        # Wrap fetch_fn so we can capture the fetched text for the codification agent
        # without fetching twice (run_daily_check only returns a status, not the text).
        captured_text = {}
        def _capturing_fetch(fn=fetch_fn, capture=captured_text):
            text = fn()
            capture["text"] = text
            return text

        check_outcome = foundation_store.run_daily_check(foundation_id, _capturing_fetch)

        result = BatchJobResult(foundation_id=foundation_id, check_outcome=check_outcome)

        if check_outcome == "change_detected":
            fetched_text = captured_text.get("text", "")
            draft = codification_agent.codify(
                foundation_id=foundation_id,
                foundation_name=record.name,
                fetched_guideline_text=fetched_text,
                previous_rules_version=previous_rules_version,
                known_diagnosis_keywords=known_diagnosis_keywords,
                previous_guideline_text=previous_guideline_texts.get(foundation_id),
            )
            result.draft = draft

            pending = approval_loop.request_approval_by_email(draft)
            result.pending_approval = pending

        results.append(result)

    return results


def check_all_pending_approvals(approval_loop: EmailApprovalLoop) -> list:
    """Convenience wrapper: checks every foundation currently awaiting approval for a
    reply, applying updates automatically wherever APPROVE was found. Call this on its
    own schedule (for example, hourly), separately from run_daily_batch_job, since
    replies can arrive well after the batch job that requested them ran."""
    outcomes = []
    for pending in approval_loop.get_pending():
        outcome = approval_loop.check_for_approval_replies(pending.foundation_id)
        outcomes.append(outcome)
    return outcomes
