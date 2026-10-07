"""
Foundation Reference Store and Daily Change Ticker

Implements the Foundation Reference entity and the Daily Automated Change Ticker
exactly as designed in data_model.md. This is the single source of truth that the
Eligibility Matching (rules engine) and Form Preparation agents should read from,
rather than each hardcoding their own placeholder foundation data.

Key behaviors, per data_model.md:
  - New foundation data changes are detected daily by comparing a hash of the
    fetched source content against the last known hash.
  - No change -> log a routine confirmation, update last_verified_at.
  - Change detected -> do NOT auto-update live rules. Block the affected
    foundation from being used for NEW matches, notify a human, and wait for
    manual review and an explicit rules_version increment.
  - In-flight cases keep using the rules_version they were originally matched
    under (handled by callers reading rules_version off the EligibilityMatch/
    Application, not by this store).
  - A failed or unreachable check is logged, retried, and escalated to a human
    on repeated failure, rather than silently going stale.

PERSISTENCE (added this session): for this prototype, persistence is a single
Excel workbook rather than a real database. This was a deliberate prototype-stage
choice: it is enough to survive a process restart, and it doubles as something a
non-technical operator can open directly to eyeball the current state, which fits
this project's human-in-the-loop philosophy. A production deployment should
replace this with a real database (e.g. Postgres), per local_setup_and_testing.md.
The workbook has two sheets: "foundations" (one row per FoundationReferenceRecord)
and "audit_log" (one row per logged event, append-only). Every mutating method
auto-saves to the workbook so nothing is lost between runs.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Callable, Dict, List

from openpyxl import Workbook, load_workbook


DEFAULT_WORKBOOK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foundation_reference_store.xlsx")

FOUNDATIONS_SHEET = "foundations"
AUDIT_LOG_SHEET = "audit_log"

FOUNDATIONS_HEADERS = [
    "foundation_id", "name", "eligibility_rules_json", "application_template_json",
    "rules_version", "last_verified_at", "source_reference", "last_known_hash",
    "blocked_for_new_matches", "consecutive_fetch_failures",
]

AUDIT_LOG_HEADERS = ["foundation_id", "event", "timestamp", "detail_json"]


@dataclass
class FoundationReferenceRecord:
    foundation_id: str
    name: str
    eligibility_rules: dict = field(default_factory=dict)
    application_template: dict = field(default_factory=dict)
    rules_version: str = "v1"
    last_verified_at: Optional[datetime] = None
    source_reference: Optional[str] = None

    # Internal bookkeeping for the daily ticker, not part of the original
    # data_model.md entity fields, but needed to actually implement the ticker.
    last_known_hash: Optional[str] = None
    blocked_for_new_matches: bool = False
    consecutive_fetch_failures: int = 0


# --- Notifications ------------------------------------------------------------------
# Single shared address for ALL system email alerts (ticker changes, fetch failures,
# escalations). Intentionally centralized in one place so every notification path
# reads from here, per the operator playbook's requirement that alerts never fragment
# across different inboxes. This is a placeholder address pending a real ops inbox.
NOTIFICATION_EMAIL = "test@gmail.com"


def send_email_alert(subject: str, body: str, to_address: str = NOTIFICATION_EMAIL) -> None:
    """Stub for sending an email alert. In this sandbox there is no real mail server
    to send through, so this just prints/logs what would be sent. A production
    deployment would replace this with a real email provider call (e.g. SES, SendGrid),
    but every call site in this file should keep routing through this one function and
    the NOTIFICATION_EMAIL constant, never a hardcoded address of its own."""
    print(f"[EMAIL ALERT -> {to_address}] Subject: {subject}\n{body}\n")


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _dt_to_str(dt: Optional[datetime]) -> str:
    return dt.isoformat() if dt else ""


def _str_to_dt(s) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    return datetime.fromisoformat(str(s))


class FoundationReferenceStore:
    """Foundation Reference store, persisted to a single Excel workbook (prototype
    stage -- see module docstring). Both the rules engine and the form preparation
    agent should read foundation data through this store's get_active_foundation()
    method, never hardcoded.

    If workbook_path points to an existing file, its contents are loaded on init.
    Every mutating call (register_foundation, run_daily_check,
    apply_human_reviewed_update) saves the full current state back to that file
    immediately afterward, so the workbook always reflects the latest state."""

    def __init__(self, workbook_path: str = DEFAULT_WORKBOOK_PATH, autosave: bool = True):
        self.workbook_path = workbook_path
        self.autosave = autosave
        self._records: Dict[str, FoundationReferenceRecord] = {}
        self._audit_log: List[dict] = []

        if os.path.exists(self.workbook_path):
            self.load_from_excel()

    # --- Excel persistence -----------------------------------------------------

    def save_to_excel(self, path: Optional[str] = None) -> None:
        """Writes the full current state (all foundation records + the full audit
        log) to the Excel workbook, overwriting any previous contents. Called
        automatically after every mutation when autosave=True."""
        target_path = path or self.workbook_path
        wb = Workbook()

        ws_f = wb.active
        ws_f.title = FOUNDATIONS_SHEET
        ws_f.append(FOUNDATIONS_HEADERS)
        for record in self._records.values():
            ws_f.append([
                record.foundation_id,
                record.name,
                json.dumps(record.eligibility_rules),
                json.dumps(record.application_template),
                record.rules_version,
                _dt_to_str(record.last_verified_at),
                record.source_reference or "",
                record.last_known_hash or "",
                record.blocked_for_new_matches,
                record.consecutive_fetch_failures,
            ])

        ws_a = wb.create_sheet(AUDIT_LOG_SHEET)
        ws_a.append(AUDIT_LOG_HEADERS)
        for entry in self._audit_log:
            core_keys = {"foundation_id", "event", "timestamp"}
            detail = {k: v for k, v in entry.items() if k not in core_keys}
            ws_a.append([
                entry.get("foundation_id", ""),
                entry.get("event", ""),
                _dt_to_str(entry.get("timestamp")) if isinstance(entry.get("timestamp"), datetime) else str(entry.get("timestamp", "")),
                json.dumps(detail, default=str),
            ])

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        wb.save(target_path)

    def load_from_excel(self, path: Optional[str] = None) -> None:
        """Reads foundation records and the audit log back from the Excel
        workbook, replacing whatever is currently in memory. Called automatically
        on init if the workbook file already exists."""
        source_path = path or self.workbook_path
        wb = load_workbook(source_path)

        self._records = {}
        if FOUNDATIONS_SHEET in wb.sheetnames:
            ws_f = wb[FOUNDATIONS_SHEET]
            rows = list(ws_f.iter_rows(min_row=2, values_only=True))
            for row in rows:
                if row[0] is None:
                    continue
                (foundation_id, name, rules_json, template_json, rules_version,
                 last_verified_at, source_reference, last_known_hash,
                 blocked, failures) = row
                record = FoundationReferenceRecord(
                    foundation_id=foundation_id,
                    name=name,
                    eligibility_rules=json.loads(rules_json) if rules_json else {},
                    application_template=json.loads(template_json) if template_json else {},
                    rules_version=rules_version or "v1",
                    last_verified_at=_str_to_dt(last_verified_at),
                    source_reference=source_reference or None,
                    last_known_hash=last_known_hash or None,
                    blocked_for_new_matches=bool(blocked),
                    consecutive_fetch_failures=int(failures) if failures else 0,
                )
                self._records[record.foundation_id] = record

        self._audit_log = []
        if AUDIT_LOG_SHEET in wb.sheetnames:
            ws_a = wb[AUDIT_LOG_SHEET]
            rows = list(ws_a.iter_rows(min_row=2, values_only=True))
            for row in rows:
                if row[0] is None and row[1] is None:
                    continue
                foundation_id, event, timestamp, detail_json = row
                entry = {
                    "foundation_id": foundation_id,
                    "event": event,
                    "timestamp": _str_to_dt(timestamp),
                }
                if detail_json:
                    entry.update(json.loads(detail_json))
                self._audit_log.append(entry)

    def _autosave(self) -> None:
        if self.autosave:
            self.save_to_excel()

    # --- Core store operations ---------------------------------------------------

    def register_foundation(self, record: FoundationReferenceRecord):
        self._records[record.foundation_id] = record
        self._autosave()

    def get_active_foundation(self, foundation_id: str) -> Optional[FoundationReferenceRecord]:
        """Returns the foundation record ONLY if it is not currently blocked
        for new matches. Per data_model.md, a foundation flagged by the ticker
        for a detected-but-unreviewed change must not be used for new matches."""
        record = self._records.get(foundation_id)
        if record is None or record.blocked_for_new_matches:
            return None
        return record

    def get_audit_log(self) -> List[dict]:
        return list(self._audit_log)

    def run_daily_check(self, foundation_id: str, fetch_source_fn: Callable[[], str]) -> str:
        """
        Runs one daily ticker check for a single foundation.
        fetch_source_fn is a callable that fetches the foundation's current
        published source content (a real implementation would fetch the actual
        eligibility guidelines / form page here; tests below use a stub function).

        Returns one of: "no_change", "change_detected", "fetch_failed".
        """
        record = self._records.get(foundation_id)
        if record is None:
            raise ValueError(f"Unknown foundation_id: {foundation_id}")

        try:
            fetched_content = fetch_source_fn()
        except Exception as exc:
            record.consecutive_fetch_failures += 1
            self._audit_log.append({
                "foundation_id": foundation_id,
                "event": "fetch_failed",
                "timestamp": datetime.utcnow(),
                "detail": str(exc),
                "consecutive_failures": record.consecutive_fetch_failures,
            })
            if record.consecutive_fetch_failures >= 3:
                self._audit_log.append({
                    "foundation_id": foundation_id,
                    "event": "escalated_to_human_repeated_fetch_failure",
                    "timestamp": datetime.utcnow(),
                })
                send_email_alert(
                    subject=f"[Action needed] Source unreachable 3+ days: {record.name}",
                    body=(
                        f"The published source for '{record.name}' (foundation_id={foundation_id}) "
                        f"has failed to load for {record.consecutive_fetch_failures} consecutive "
                        f"daily checks. This foundation is effectively unmonitored until someone "
                        f"investigates. See the Human Operator Playbook, Alert 3, for next steps."
                    ),
                )
            self._autosave()
            return "fetch_failed"

        new_hash = _hash_content(fetched_content)
        record.consecutive_fetch_failures = 0

        if record.last_known_hash is None:
            record.last_known_hash = new_hash
            record.last_verified_at = datetime.utcnow()
            self._audit_log.append({
                "foundation_id": foundation_id,
                "event": "baseline_established",
                "timestamp": record.last_verified_at,
            })
            self._autosave()
            return "no_change"

        if new_hash == record.last_known_hash:
            record.last_verified_at = datetime.utcnow()
            self._audit_log.append({
                "foundation_id": foundation_id,
                "event": "no_change",
                "timestamp": record.last_verified_at,
            })
            self._autosave()
            return "no_change"

        # Change detected: do NOT auto-update. Block new matches, flag for human review.
        record.blocked_for_new_matches = True
        record.last_known_hash = new_hash  # so we don't re-alert on the same change repeatedly
        self._audit_log.append({
            "foundation_id": foundation_id,
            "event": "change_detected_blocked_pending_human_review",
            "timestamp": datetime.utcnow(),
        })
        send_email_alert(
            subject=f"[Action needed] Change detected: {record.name}",
            body=(
                f"The published source for '{record.name}' (foundation_id={foundation_id}) "
                f"has changed since the last check. New matches are now BLOCKED for this "
                f"foundation pending your review. In-flight cases are unaffected and continue "
                f"under rules_version={record.rules_version}. Please review the source page and "
                f"either apply an updated rules_version or clear the block. See the Human "
                f"Operator Playbook, Alert 2, for step-by-step instructions."
            ),
        )
        self._autosave()
        return "change_detected"

    def apply_human_reviewed_update(
        self,
        foundation_id: str,
        new_eligibility_rules: dict,
        new_application_template: dict,
        new_rules_version: str,
    ):
        """Called only after a human has reviewed a detected change and approved it.
        Per data_model.md: version increments, never overwrites silently, and this
        is the only path that unblocks a foundation for new matches again."""
        record = self._records.get(foundation_id)
        if record is None:
            raise ValueError(f"Unknown foundation_id: {foundation_id}")

        record.eligibility_rules = new_eligibility_rules
        record.application_template = new_application_template
        record.rules_version = new_rules_version
        record.blocked_for_new_matches = False
        record.last_verified_at = datetime.utcnow()

        self._audit_log.append({
            "foundation_id": foundation_id,
            "event": "human_reviewed_update_applied",
            "new_rules_version": new_rules_version,
            "timestamp": record.last_verified_at,
        })
        self._autosave()
