"""
Cron Entry Point: Daily Foundation Reference Batch Job

This is the standalone, command-line-runnable script that a cron job (or any external
scheduler) actually calls once a day. It exists because run_daily_batch_job() and
check_all_pending_approvals() (see app/orchestration/daily_batch_job.py) are written as
plain functions taking live objects as arguments -- the right shape for testing, but not
something cron can invoke directly. This script is the thin, real-world wrapper around
them: it builds the real store, agent, and approval loop, defines how each foundation's
source page is actually fetched, and calls the two batch functions in sequence.

USAGE (see the crontab example at the bottom of this file):
    python3 run_daily_batch_job_cron.py

WHAT THIS DOES NOT YET DO (see local_setup_and_testing.md section 7a and the
orchestration.md "Daily Batch Job" section for the full picture):
  - It does not yet know how to actually fetch each foundation's real published page.
    FETCH_SOURCE_FNS below is a placeholder that must be filled in with real HTTP
    fetches (or scraping, or an API call) once specific partner foundations and their
    source URLs are finalized. Every foundation this runs against MUST have a real
    fetch function here, or run_daily_batch_job() will raise a ValueError for it.
  - It still requires a human to open Gmail and click Send once per drafted approval
    email, per the platform's create_draft-only limitation. This script gets the draft
    created and waiting; it cannot send it.
  - It does not retry itself if it crashes mid-run; rely on cron's own failure/alerting
    behavior (e.g. mailing stderr, or wrapping this call in a monitored job runner) until
    a more robust retry wrapper is written.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orchestration"))

from foundation_reference_store import FoundationReferenceStore, NOTIFICATION_EMAIL
from guideline_codification_agent import GuidelineCodificationAgent
from email_approval_loop import EmailApprovalLoop, gmail_create_draft_send_fn, gmail_search_replies_fn
from daily_batch_job import run_daily_batch_job, check_all_pending_approvals


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("daily_batch_job_cron")


# --- Real per-foundation source fetch functions --------------------------------------
# PLACEHOLDER: replace each lambda below with a real fetch (e.g. requests.get(url).text,
# or a proper scraper if the page needs JS rendering) once source URLs are finalized for
# each partner foundation. Every foundation registered in the store needs an entry here.
def _fetch_not_yet_implemented(foundation_name: str):
    def _fetch():
        raise NotImplementedError(
            f"No real fetch function has been implemented yet for '{foundation_name}'. "
            f"Add one to FETCH_SOURCE_FNS in run_daily_batch_job_cron.py before this "
            f"foundation can be checked by the daily job."
        )
    return _fetch


FETCH_SOURCE_FNS = {
    # "cancercare_copay": lambda: requests.get("https://www.cancercare.org/co_payment_assistance_foundation").text,
    # "pink_daisy": lambda: requests.get("https://thepinkdaisyproject.com/apply").text,
}


def build_runtime():
    """Constructs the real store, agent, and approval loop this cron job uses.
    Kept as its own function so a future test can call it too, if needed."""
    store = FoundationReferenceStore()  # uses DEFAULT_WORKBOOK_PATH, autosave=True

    agent = GuidelineCodificationAgent()

    # NOTE: wire these to the real Gmail MCP tool callables at the call site that
    # actually has tool access (this script's sys.path/imports assume it runs inside
    # an environment where those tools are reachable -- see the module docstring in
    # email_approval_loop.py for the exact expected tool call shapes).
    send_fn = gmail_create_draft_send_fn(create_draft_tool=None)   # TODO: inject real tool
    search_fn = gmail_search_replies_fn(get_thread_tool=None)      # TODO: inject real tool

    approval_loop = EmailApprovalLoop(
        foundation_store=store,
        reviewer_email=NOTIFICATION_EMAIL,
        send_email_fn=send_fn,
        search_replies_fn=search_fn,
    )
    return store, agent, approval_loop


def main():
    store, agent, approval_loop = build_runtime()

    # Only check foundations we actually have a real fetch function for -- fail loud
    # and early (in the log) about the rest, rather than silently skipping them.
    registered_ids = set(store._records.keys())
    fetchable_ids = set(FETCH_SOURCE_FNS.keys())
    missing = registered_ids - fetchable_ids
    if missing:
        logger.warning(
            "No fetch function configured for %d registered foundation(s), skipping "
            "this run: %s", len(missing), ", ".join(sorted(missing)),
        )

    active_fetch_fns = {fid: fn for fid, fn in FETCH_SOURCE_FNS.items() if fid in registered_ids}

    if not active_fetch_fns:
        logger.info("No foundations with a real fetch function are registered yet. "
                     "Nothing to check today.")
    else:
        logger.info("Running daily change check for %d foundation(s)...", len(active_fetch_fns))
        results = run_daily_batch_job(store, active_fetch_fns, agent, approval_loop)
        for r in results:
            logger.info("Foundation %s: %s%s", r.foundation_id, r.check_outcome,
                        " (draft created, approval email drafted)" if r.draft else "")

    logger.info("Checking for approval replies on any pending drafts...")
    approval_outcomes = check_all_pending_approvals(approval_loop)
    for outcome in approval_outcomes:
        logger.info("Pending approval for %s: %s (applied=%s)",
                    outcome.foundation_id, outcome.outcome, outcome.applied)

    logger.info("Daily batch job run complete.")


if __name__ == "__main__":
    main()


# --- Crontab example -------------------------------------------------------------
#
# To run this once every day at 6:00 AM server time, add a line like this via
# `crontab -e` (adjust the python3 and script paths to match the actual deployment
# environment):
#
#   0 6 * * * /usr/bin/python3 /path/to/oncology-financial-navigator-ai/app/orchestration/run_daily_batch_job_cron.py >> /var/log/oncology_navigator_batch_job.log 2>&1
#
# The ">> ... 2>&1" part appends both normal output and errors to a log file, so a
# failed run leaves a record instead of vanishing silently -- check that log file
# periodically, or better, pipe it into whatever alerting/monitoring the eventual
# production deployment uses.
