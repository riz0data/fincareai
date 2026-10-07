"""
Tests for the daily batch job runner (app/orchestration/daily_batch_job.py), which
chains: change detection -> automatic drafting -> email approval request.

The end-to-end multi-foundation test mirrors the live scenario tested manually in an
earlier session: two foundations change on the same day, both get drafted and emailed
independently, and approving only one leaves the other correctly untouched and pending.
"""

import pytest

from foundation_reference_store import FoundationReferenceStore, FoundationReferenceRecord
from guideline_codification_agent import GuidelineCodificationAgent
from email_approval_loop import EmailApprovalLoop
from daily_batch_job import run_daily_batch_job, check_all_pending_approvals


@pytest.fixture
def store(tmp_path):
    s = FoundationReferenceStore(workbook_path=str(tmp_path / "store.xlsx"))
    s.register_foundation(FoundationReferenceRecord(
        foundation_id="cancercare_copay", name="CancerCare Co-Payment Assistance",
        eligibility_rules={"max_income_multiplier_of_poverty_line": 5.0},
        application_template={"required_fields": ["patient_full_name"]}, rules_version="v1",
    ))
    s.register_foundation(FoundationReferenceRecord(
        foundation_id="pink_daisy", name="The Pink Daisy Project",
        eligibility_rules={"max_income_multiplier_of_poverty_line": 3.0},
        application_template={"required_fields": ["patient_full_name"]}, rules_version="v1",
    ))
    s.run_daily_check("cancercare_copay", lambda: "original content v1")
    s.run_daily_check("pink_daisy", lambda: "original content v1")
    return s


@pytest.fixture
def fake_email_backend():
    replies = {}

    def send_fn(to_address, subject, body):
        fid = "cancercare_copay" if "CancerCare" in subject else "pink_daisy"
        return {"thread_id": f"thread-{fid}", "message_id": f"msg-{fid}"}

    def search_fn(thread_id):
        return replies.get(thread_id, [])

    return {"send_fn": send_fn, "search_fn": search_fn, "replies": replies}


@pytest.fixture
def loop(store, fake_email_backend):
    return EmailApprovalLoop(store, "reviewer@example.com",
                              fake_email_backend["send_fn"], fake_email_backend["search_fn"])


@pytest.fixture
def agent():
    return GuidelineCodificationAgent()


def test_no_change_produces_no_draft_or_approval_request(store, agent, loop):
    fetch_fns = {
        "cancercare_copay": lambda: "original content v1",
        "pink_daisy": lambda: "original content v1",
    }
    results = run_daily_batch_job(store, fetch_fns, agent, loop)

    for r in results:
        assert r.check_outcome == "no_change"
        assert r.draft is None
        assert r.pending_approval is None
    assert len(loop.get_pending()) == 0


def test_change_detected_produces_draft_and_approval_request(store, agent, loop):
    fetch_fns = {
        "cancercare_copay": lambda: "Household income must be at or below 450 percent of the federal poverty line.",
        "pink_daisy": lambda: "original content v1",
    }
    results = run_daily_batch_job(store, fetch_fns, agent, loop)

    cc_result = next(r for r in results if r.foundation_id == "cancercare_copay")
    pd_result = next(r for r in results if r.foundation_id == "pink_daisy")

    assert cc_result.check_outcome == "change_detected"
    assert cc_result.draft is not None
    assert cc_result.pending_approval is not None
    assert store.get_active_foundation("cancercare_copay") is None

    assert pd_result.check_outcome == "no_change"
    assert pd_result.draft is None
    assert store.get_active_foundation("pink_daisy") is not None


def test_two_simultaneous_changes_are_handled_independently(store, agent, loop, fake_email_backend):
    fetch_fns = {
        "cancercare_copay": lambda: (
            "Household income must be at or below 450 percent of the federal poverty line. "
            "Patients must be uninsured or underinsured."
        ),
        "pink_daisy": lambda: (
            "Household income must be at or below 250 percent of poverty level. "
            "For women with breast cancer."
        ),
    }
    results = run_daily_batch_job(
        store, fetch_fns, agent, loop,
        known_diagnosis_keywords=["breast cancer", "lung cancer"],
    )

    assert all(r.check_outcome == "change_detected" for r in results)
    assert store.get_active_foundation("cancercare_copay") is None
    assert store.get_active_foundation("pink_daisy") is None
    assert len(loop.get_pending()) == 2

    # Approve only cancercare_copay.
    fake_email_backend["replies"]["thread-cancercare_copay"] = ["Confirmed. APPROVE"]

    check_results = check_all_pending_approvals(loop)
    cc_check = next(r for r in check_results if r.foundation_id == "cancercare_copay")
    pd_check = next(r for r in check_results if r.foundation_id == "pink_daisy")

    assert cc_check.outcome == "approved"
    assert cc_check.applied is True
    assert pd_check.outcome == "no_reply_yet"
    assert pd_check.applied is False

    # cancercare_copay unblocked and version-bumped; pink_daisy still blocked/pending.
    assert store.get_active_foundation("cancercare_copay") is not None
    assert store._records["cancercare_copay"].rules_version == "v2"
    assert store.get_active_foundation("pink_daisy") is None
    assert len(loop.get_pending()) == 1


def test_fetch_failure_produces_no_draft(store, agent, loop):
    def _boom():
        raise RuntimeError("network error")

    fetch_fns = {
        "cancercare_copay": _boom,
        "pink_daisy": lambda: "original content v1",
    }
    results = run_daily_batch_job(store, fetch_fns, agent, loop)
    cc_result = next(r for r in results if r.foundation_id == "cancercare_copay")
    assert cc_result.check_outcome == "fetch_failed"
    assert cc_result.draft is None
    assert cc_result.pending_approval is None
    # A single fetch failure must not block the foundation.
    assert store.get_active_foundation("cancercare_copay") is not None


def test_unknown_foundation_id_in_fetch_fns_raises(store, agent, loop):
    fetch_fns = {"not_a_real_foundation": lambda: "content"}
    with pytest.raises(ValueError):
        run_daily_batch_job(store, fetch_fns, agent, loop)


def test_check_all_pending_approvals_with_nothing_pending_returns_empty(store, agent, loop):
    fetch_fns = {
        "cancercare_copay": lambda: "original content v1",
        "pink_daisy": lambda: "original content v1",
    }
    run_daily_batch_job(store, fetch_fns, agent, loop)
    outcomes = check_all_pending_approvals(loop)
    assert outcomes == []
