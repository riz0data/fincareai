"""
Tests for the Email-Based Approval Loop (app/orchestration/email_approval_loop.py).

Uses injected fake send_email_fn / search_replies_fn throughout, exactly as the module
was designed to be tested -- no real email is ever sent by this suite.
"""

import pytest

from foundation_reference_store import FoundationReferenceStore, FoundationReferenceRecord
from guideline_codification_agent import GuidelineCodificationAgent
from email_approval_loop import EmailApprovalLoop


@pytest.fixture
def store(tmp_path):
    s = FoundationReferenceStore(workbook_path=str(tmp_path / "store.xlsx"))
    s.register_foundation(FoundationReferenceRecord(
        foundation_id="fund_a", name="Fund A",
        eligibility_rules={"max_income_multiplier_of_poverty_line": 5.0},
        application_template={"required_fields": ["patient_full_name"]},
        rules_version="v1",
    ))
    s.run_daily_check("fund_a", lambda: "original content")  # baseline
    s.run_daily_check("fund_a", lambda: "CHANGED content")   # now blocked, pending review
    return s


@pytest.fixture
def draft(store):
    agent = GuidelineCodificationAgent()
    return agent.codify(
        foundation_id="fund_a", foundation_name="Fund A",
        fetched_guideline_text="Household income must be at or below 400% of the federal poverty line.",
        previous_rules_version=store._records["fund_a"].rules_version,
    )


@pytest.fixture
def fake_email_backend():
    sent = {}
    replies = {}

    def send_fn(to_address, subject, body):
        sent["to"] = to_address
        sent["subject"] = subject
        sent["body"] = body
        return {"thread_id": "thread-1", "message_id": "msg-1"}

    def search_fn(thread_id):
        return replies.get(thread_id, [])

    return {"send_fn": send_fn, "search_fn": search_fn, "sent": sent, "replies": replies}


@pytest.fixture
def loop(store, fake_email_backend):
    return EmailApprovalLoop(
        store, "reviewer@example.com",
        fake_email_backend["send_fn"], fake_email_backend["search_fn"],
    )


def test_request_approval_sends_email_and_records_pending(loop, draft, fake_email_backend):
    pending = loop.request_approval_by_email(draft)
    assert pending.foundation_id == "fund_a"
    assert pending.resolved is False
    assert "Fund A" in fake_email_backend["sent"]["subject"]
    assert len(loop.get_pending()) == 1


def test_no_reply_yet_leaves_foundation_blocked(loop, draft, store):
    loop.request_approval_by_email(draft)
    result = loop.check_for_approval_replies("fund_a")
    assert result.outcome == "no_reply_yet"
    assert store.get_active_foundation("fund_a") is None


def test_approve_reply_applies_update_and_unblocks(loop, draft, store, fake_email_backend):
    loop.request_approval_by_email(draft)
    fake_email_backend["replies"]["thread-1"] = ["Looks right. APPROVE"]

    result = loop.check_for_approval_replies("fund_a")

    assert result.outcome == "approved"
    assert result.applied is True
    active = store.get_active_foundation("fund_a")
    assert active is not None
    assert active.rules_version == "v2"
    assert len(loop.get_pending()) == 0


def test_approve_is_idempotent_on_recheck(loop, draft, store, fake_email_backend):
    loop.request_approval_by_email(draft)
    fake_email_backend["replies"]["thread-1"] = ["APPROVE"]
    loop.check_for_approval_replies("fund_a")

    # Calling again should not error or re-apply / double-bump the version.
    result2 = loop.check_for_approval_replies("fund_a")
    assert result2.outcome == "approved"
    assert result2.applied is False  # already resolved, nothing new applied
    assert store._records["fund_a"].rules_version == "v2"


def test_reject_reply_leaves_rules_engine_untouched(loop, draft, store, fake_email_backend):
    loop.request_approval_by_email(draft)
    fake_email_backend["replies"]["thread-1"] = ["This is wrong. REJECT"]

    result = loop.check_for_approval_replies("fund_a")

    assert result.outcome == "rejected"
    assert result.applied is False
    assert store._records["fund_a"].rules_version == "v1"
    assert store.get_active_foundation("fund_a") is None  # stays blocked


def test_ambiguous_reply_with_both_keywords_is_never_guessed(loop, draft, store, fake_email_backend):
    loop.request_approval_by_email(draft)
    fake_email_backend["replies"]["thread-1"] = ["I approve some of this but REJECT the income part"]

    result = loop.check_for_approval_replies("fund_a")

    assert result.outcome == "unrecognized_reply"
    assert result.applied is False
    assert store._records["fund_a"].rules_version == "v1"


def test_unrecognized_reply_leaves_case_pending(loop, draft, store, fake_email_backend):
    loop.request_approval_by_email(draft)
    fake_email_backend["replies"]["thread-1"] = ["Can you give me more detail on this?"]

    result = loop.check_for_approval_replies("fund_a")

    assert result.outcome == "unrecognized_reply"
    assert result.applied is False
    assert len(loop.get_pending()) == 1  # still pending, not resolved


def test_checking_unknown_foundation_raises(loop):
    with pytest.raises(ValueError):
        loop.check_for_approval_replies("does_not_exist")
