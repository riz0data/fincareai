# Local Setup, Deployment, and Testing Guide

This document walks through how to get this project running on your own machine, since
LangGraph and other dependencies could not be installed or run inside the build sandbox used to
create this repo. Everything up through the Intake Agent has already been written and tested
logically; this guide is what lets you actually run and verify it yourself, and continue building
from here.

---

## 1. Prerequisites

- Python 3.10 or newer installed on your machine.
- This repository pulled down locally (see your existing GitHub workflow for the lakehouse repo
  as a reference for how you like to do this).
- A terminal you're comfortable working in.

## 2. Create a Virtual Environment

Always work inside a virtual environment for this project, rather than installing packages
system-wide, to keep dependencies isolated and reproducible.

Steps:
- Navigate into the project folder root, `oncology-financial-navigator-ai`.
- Create a virtual environment named `venv`.
- Activate that virtual environment before installing anything or running any code.

## 3. Install Dependencies

Once the virtual environment is active, install the required packages. At minimum, for the
pieces built so far and the next planned step, you will need: LangGraph, for the orchestration
graph we are about to wire together; and Python's standard library covers everything else used
so far, including the rules engine and data entities, no other installs needed yet.

A `requirements.txt` file should be created at the project root listing these packages with
pinned versions once you confirm what installs cleanly on your machine, so the environment is
reproducible later.

## 4. Project Structure Reference

- `app/rules_engine/eligibility_rules.py` — deterministic eligibility logic. No dependencies
  beyond the Python standard library.
- `app/data/entities.py` — core data entities (patient case, eligibility match, escalation,
  application, outcome, foundation reference). No dependencies beyond the Python standard
  library.
- `app/agents/intake_agent.py` — text-only intake conversation agent. Currently uses a stubbed
  extraction function in place of a real LLM call; this is the next known upgrade, flagged
  clearly in the code comments.
- `app/orchestration/` — where the LangGraph wiring will live, connecting the intake agent to
  the rules engine and future agents, following the phase design in `orchestration.md`.

## 5. Running the Existing Pieces Locally

Each module built so far was tested with an inline simulation rather than a formal test suite.
To rerun those same checks locally:

- Run `eligibility_rules.py`'s logic by importing it in a Python shell or script, creating a
  `PatientProfile` and a `FoundationRule`, and calling `evaluate_eligibility`. Confirm it returns
  match, no match, or ambiguous as expected for a few sample cases.
- Run `entities.py` similarly, creating one of each entity and confirming they link together
  correctly by `case_id`.
- Run `intake_agent.py` by creating an `IntakeAgent`, feeding it simulated answers in sequence
  through `submit_answer`, and confirming `get_completed_profile` returns a fully populated
  profile at the end.

It is worth formalizing these into a real automated test suite (using `pytest`) in the `tests/`
folder that already exists at the project root, rather than relying on manual inline checks going
forward, as the project grows.

## 6. Known Issue To Fix Locally

The intake agent's field extraction is currently a simple stub, not a real LLM call. It was
caught failing on natural phrasing like "there's three of us at home" because it only looks for
numeric digits. This must be replaced with a real LLM-based extraction step before this agent is
trustworthy with real patient conversation. This is the highest-priority fix once you are set up
locally.

## 7. Testing Philosophy Going Forward

- Test each new piece in isolation before wiring it into the larger orchestration graph, the same
  incremental approach used throughout this build.
- Deliberately test edge cases and messy, natural-language-style inputs, not just clean expected
  inputs, since real patients will not answer in clean structured formats.
- Confirm that missing or ambiguous data always results in an escalation rather than a guess,
  since that is a core safety principle of this whole system.
- Once the LangGraph orchestration is wired up, test that a full case can flow end to end from
  intake through eligibility matching, and that escalation branches correctly trigger when
  expected.

## 7a. Guideline Codification Agent: Email-Based Approval Setup

The Guideline Codification Agent (Agent 5) and its email approval loop
(`app/orchestration/email_approval_loop.py`) let a human reviewer approve or reject a
proposed rule update by replying to an email, instead of using a web dashboard. This
section documents exactly how to set that up and run it for real, since it depends on
the connected Gmail integration rather than being fully self-contained code.

**How the pieces fit together:**
- `guideline_codification_agent.py` reads the raw guideline text the daily ticker fetched
  and produces a `CodificationDraft` (a proposed rule, never applied automatically).
- `email_approval_loop.py` turns that draft into a plain-language email, sends it to the
  reviewer, and later checks the reply for the keyword `APPROVE` or `REJECT`. Only an
  unambiguous `APPROVE` reply triggers `apply_human_reviewed_update()`, which is the one
  function that actually updates the live rules engine and unblocks the foundation.
- The module has two implementations of the send/search functions: fully injectable fake
  ones (used in the inline tests already run against this module, so the approve, reject,
  and ambiguous-reply paths are all verified), and real Gmail-backed adapter functions
  (`gmail_create_draft_send_fn`, `gmail_search_replies_fn`) near the bottom of the same
  file, meant to be wired up wherever this actually runs with real Gmail tool access.

**Important manual step, by platform design, not a bug in this code.** The connected
Gmail integration only exposes a `create_draft` action, there is no direct "send email"
tool available. That means when the system is ready to request approval, it will create
a draft sitting in the Drafts folder, but a person must open Gmail and click Send once
before the reviewer actually receives it. Once that draft is sent and the reviewer
replies, everything else, reading the reply, checking for the approval keyword, and
applying the update, is fully automatic with no further manual step.

**One-time setup checklist:**
1. Confirm the Gmail account connected to this integration is the one that should send
   these approval-request emails, and that `NOTIFICATION_EMAIL` in
   `foundation_reference_store.py` (currently the placeholder `test@gmail.com`) is updated
   to the real reviewer's address before any real use.
2. When the daily batch job detects a change and runs the Codification Agent, call
   `EmailApprovalLoop.request_approval_by_email()` using the real
   `gmail_create_draft_send_fn` adapter. This creates the draft.
3. **Manually open Gmail and click Send on that draft.** This is the one deliberate human
   touchpoint in an otherwise automated pipeline, and it exists only because of the
   platform's tool limitations, not the design.
4. The reviewer reads the email and replies directly in the same thread with `APPROVE` or
   `REJECT` (case-insensitive, must appear as a standalone word).
5. When `check_for_approval_replies()` is next run (on a schedule, or on demand), it reads
   that thread via `gmail_search_replies_fn`, and if `APPROVE` was found, applies the
   update automatically. Nothing further needs to be sent or clicked at this stage.

**Testing this locally before connecting real Gmail.** The inline tests already run
against `email_approval_loop.py` use fake, injectable send/search functions, so the full
approve, reject, and ambiguous-reply logic can be verified without touching a real
inbox. Use that same pattern to test any future changes to the approval logic itself;
only switch to the real `gmail_create_draft_send_fn` / `gmail_search_replies_fn` adapters
when testing the actual end-to-end email flow.

## 7b. Running the Daily Batch Job on a Schedule (Cron)

`app/orchestration/daily_batch_job.py` defines the batch job logic as plain functions
(`run_daily_batch_job`, `check_all_pending_approvals`) that take live objects as
arguments, which is the right shape for the automated test suite but not something a
scheduler can call directly. `app/orchestration/run_daily_batch_job_cron.py` is the
thin, real, command-line-runnable wrapper around them: it builds the real Foundation
Reference Store, the Codification Agent, and the Email Approval Loop, then calls both
batch functions in sequence.

**What still needs to be filled in before this can run for real:**
- `FETCH_SOURCE_FNS` in that file is currently empty. Each registered foundation needs
  a real fetch function added there (an HTTP request to its published guidelines page,
  at minimum) before the daily check will actually look at it. Until then, the script
  runs harmlessly and just logs that nothing is configured yet.
- The Gmail `send_fn` / `search_fn` adapters are wired up but passed `None` for the
  actual tool callables. These need to be injected with real Gmail MCP tool access at
  the point this script actually runs, per the adapter functions' docstrings in
  `email_approval_loop.py`.

**Scheduling it with cron**, once both of the above are filled in: add a line like this
via `crontab -e` (once per day, for example at 6 AM server time):

    0 6 * * * /usr/bin/python3 /path/to/oncology-financial-navigator-ai/app/orchestration/run_daily_batch_job_cron.py >> /var/log/oncology_navigator_batch_job.log 2>&1

This appends both normal output and errors to a log file rather than letting a failed
run vanish silently. The script logs, per foundation, whether it found no change, a
detected change with a new approval draft created, or a fetch failure, and separately
logs the outcome of checking any pending approval replies, so the log file alone is
usually enough to confirm a given day's run behaved as expected.

## 8. Deployment (Later Stage, Not Yet Applicable)

Deployment considerations, hosting the app, setting up the QR code and URL entry point, and
connecting the real voice layer, all come after the core orchestration logic is proven locally.
This section should be filled in once that stage is reached; deploying before the core logic is
solid would be premature.
