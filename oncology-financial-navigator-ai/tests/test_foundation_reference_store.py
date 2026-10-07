"""
Tests for the Foundation Reference Store and Daily Change Ticker
(app/data/foundation_reference_store.py), including Excel persistence.

Each test uses its own temp workbook path (via the tmp_path pytest fixture) so tests
never collide with each other or with the real prototype workbook, and never need
manual cleanup.
"""

import os
import pytest

from foundation_reference_store import (
    FoundationReferenceStore,
    FoundationReferenceRecord,
)


@pytest.fixture
def workbook_path(tmp_path):
    return str(tmp_path / "test_foundation_store.xlsx")


@pytest.fixture
def store(workbook_path):
    return FoundationReferenceStore(workbook_path=workbook_path)


def _make_record(foundation_id="fund_a", rules_version="v1"):
    return FoundationReferenceRecord(
        foundation_id=foundation_id,
        name="Fund A",
        eligibility_rules={"max_income_multiplier_of_poverty_line": 5.0},
        application_template={"required_fields": ["patient_full_name"]},
        rules_version=rules_version,
    )


def test_register_and_get_active_foundation(store):
    store.register_foundation(_make_record())
    active = store.get_active_foundation("fund_a")
    assert active is not None
    assert active.name == "Fund A"


def test_first_check_establishes_baseline_no_change(store):
    store.register_foundation(_make_record())
    outcome = store.run_daily_check("fund_a", lambda: "original content")
    assert outcome == "no_change"
    assert store.get_active_foundation("fund_a") is not None


def test_same_content_next_day_is_no_change(store):
    store.register_foundation(_make_record())
    store.run_daily_check("fund_a", lambda: "original content")
    outcome = store.run_daily_check("fund_a", lambda: "original content")
    assert outcome == "no_change"
    assert store.get_active_foundation("fund_a") is not None


def test_changed_content_blocks_foundation(store):
    store.register_foundation(_make_record())
    store.run_daily_check("fund_a", lambda: "original content")
    outcome = store.run_daily_check("fund_a", lambda: "CHANGED content")
    assert outcome == "change_detected"
    assert store.get_active_foundation("fund_a") is None


def test_fetch_failure_does_not_block_foundation(store):
    store.register_foundation(_make_record())
    store.run_daily_check("fund_a", lambda: "original content")

    def _boom():
        raise RuntimeError("network error")

    outcome = store.run_daily_check("fund_a", _boom)
    assert outcome == "fetch_failed"
    assert store.get_active_foundation("fund_a") is not None


def test_repeated_fetch_failures_are_logged_and_escalated(store):
    store.register_foundation(_make_record())
    store.run_daily_check("fund_a", lambda: "original content")

    def _boom():
        raise RuntimeError("network error")

    for _ in range(3):
        store.run_daily_check("fund_a", _boom)

    events = [entry["event"] for entry in store.get_audit_log()]
    assert events.count("fetch_failed") == 3
    assert "escalated_to_human_repeated_fetch_failure" in events


def test_apply_human_reviewed_update_unblocks_and_bumps_version(store):
    store.register_foundation(_make_record())
    store.run_daily_check("fund_a", lambda: "original content")
    store.run_daily_check("fund_a", lambda: "CHANGED content")
    assert store.get_active_foundation("fund_a") is None

    store.apply_human_reviewed_update(
        foundation_id="fund_a",
        new_eligibility_rules={"max_income_multiplier_of_poverty_line": 4.0},
        new_application_template={"required_fields": ["patient_full_name"]},
        new_rules_version="v2",
    )

    active = store.get_active_foundation("fund_a")
    assert active is not None
    assert active.rules_version == "v2"
    assert active.eligibility_rules["max_income_multiplier_of_poverty_line"] == 4.0


def test_unknown_foundation_id_raises(store):
    with pytest.raises(ValueError):
        store.run_daily_check("does_not_exist", lambda: "content")


def test_state_persists_across_a_simulated_restart(workbook_path):
    store1 = FoundationReferenceStore(workbook_path=workbook_path)
    store1.register_foundation(_make_record())
    store1.run_daily_check("fund_a", lambda: "original content")
    store1.run_daily_check("fund_a", lambda: "CHANGED content")

    assert os.path.exists(workbook_path)

    store2 = FoundationReferenceStore(workbook_path=workbook_path)
    assert store2.get_active_foundation("fund_a") is None
    assert store2._records["fund_a"].rules_version == "v1"


def test_human_reviewed_update_persists_across_a_simulated_restart(workbook_path):
    store1 = FoundationReferenceStore(workbook_path=workbook_path)
    store1.register_foundation(_make_record())
    store1.run_daily_check("fund_a", lambda: "original content")
    store1.run_daily_check("fund_a", lambda: "CHANGED content")
    store1.apply_human_reviewed_update(
        foundation_id="fund_a",
        new_eligibility_rules={"max_income_multiplier_of_poverty_line": 6.0},
        new_application_template={"required_fields": []},
        new_rules_version="v2",
    )

    store2 = FoundationReferenceStore(workbook_path=workbook_path)
    active = store2.get_active_foundation("fund_a")
    assert active is not None
    assert active.rules_version == "v2"
    assert active.eligibility_rules["max_income_multiplier_of_poverty_line"] == 6.0


def test_audit_log_persists_across_a_simulated_restart(workbook_path):
    store1 = FoundationReferenceStore(workbook_path=workbook_path)
    store1.register_foundation(_make_record())
    store1.run_daily_check("fund_a", lambda: "original content")
    store1.run_daily_check("fund_a", lambda: "CHANGED content")

    store2 = FoundationReferenceStore(workbook_path=workbook_path)
    events = [entry["event"] for entry in store2.get_audit_log()]
    assert "baseline_established" in events
    assert "change_detected_blocked_pending_human_review" in events


def test_autosave_false_does_not_write_file_until_manual_save(tmp_path):
    path = str(tmp_path / "manual_save.xlsx")
    store = FoundationReferenceStore(workbook_path=path, autosave=False)
    store.register_foundation(_make_record())
    assert not os.path.exists(path)
    store.save_to_excel()
    assert os.path.exists(path)
