# Human Operator Playbook

## Purpose

This is the day-to-day operating manual for the human staff member (Patient Financial
Advocate, or a designated data-maintenance owner) responsible for keeping the Oncology
Financial Navigator's Foundation Reference data trustworthy, and for handling the
escalations the system surfaces. It translates the system design into concrete, plain
steps: what alert you'll get, what it means, and exactly what to do about it.

This playbook assumes you have already read `data_model.md` (for the Foundation
Reference entity and Daily Automated Change Ticker) and `agent_architecture.md` (for how
the Eligibility Matching and Risk/Escalation agents work). It does not repeat the full
design reasoning found there; it focuses on the operator's actions.

**Notification email address.** All system alerts referenced in this playbook are sent
to a single shared inbox: `test@gmail.com`. This is a placeholder for now and should be
replaced with the real operations inbox before any production use. The point of using
one consistent address everywhere is so nothing falls through the cracks by going to the
wrong person's inbox.

---

## Alert 1: Daily Change Ticker -- No Change Detected

**What you'll see.** Nothing requiring action. The system logs a routine confirmation
internally (`last_verified_at` updates). No email is sent for this case, since it is the
expected, healthy outcome every single day and would otherwise create alert fatigue.

**What to do.** Nothing. Optionally, spot-check the audit log weekly to confirm checks
are actually running (see Alert 3 below for what a silent failure looks like instead).

---

## Alert 2: Daily Change Ticker -- Change Detected

**What you'll see.** An email to `test@gmail.com` with a subject line identifying the
foundation by name. As of the Guideline Codification Agent (Agent 5), this email no
longer just shows you the raw old-versus-new source text -- it links to a **draft**
proposed rule update that the agent has already prepared for you: a filled-in income
threshold, insurance statuses, diagnosis coverage, and required form fields, each
labeled with the agent's own confidence (high, medium, or low) and, where possible,
the exact snippet of source text it pulled each value from.

**What this means.** The foundation's published eligibility guidelines or application
form page has changed since the last check. The system has already automatically:
  - Blocked that foundation from being used for any brand-new patient matches.
  - Left all in-flight cases untouched; they continue under their original
    rules_version and are not affected by this block.
  - Run the Guideline Codification Agent against the new source text and prepared a
    draft rule update, so you are reviewing and correcting a draft rather than
    building the rule from a blank page.

**Who does this review.** This should be done by the same Patient Financial Advocate
role defined in `agent_architecture.md`, or a designated data-maintenance owner with
working knowledge of the partner foundations' eligibility structures. The important
qualification is not technical skill, it's familiarity with how these foundations
actually word their guidelines, so you can tell a genuine eligibility change apart
from routine rewording. Think of your role here as an editor checking a first draft
against the source, not a data-entry clerk starting from scratch.

**What to do, step by step.**
  1. Open the email and review the agent's draft rule update field by field.
  2. Pay closest attention to any field the agent marked **low confidence** -- this
     means it could not find a clear match in the source text and is explicitly
     telling you not to trust that field without reading the source yourself. A
     **high confidence** field with a quoted source snippet still deserves a quick
     sanity check, but usually needs less scrutiny.
  3. Visit the foundation's actual published page yourself to confirm the draft is
     accurate (not a scraping artifact, a temporary site outage, or a cosmetic
     wording change that doesn't actually affect eligibility or form fields).
  4. Edit any field the agent got wrong or left blank directly in the draft.
  5. If the change is real and affects eligibility rules or the form template,
     **approve** the corrected draft. Approving is the single action that both
     increments the rules_version (for example, v1 to v2) and automatically applies
     the update to the live rules engine -- you do not separately re-type or re-enter
     the rule anywhere. Never approve a draft without incrementing the version, since
     in-flight cases and audit history depend on version numbers staying meaningful.
  6. If, after review, the content is unchanged in any way that matters (a typo fix, a
     styling change), you may still choose to approve a version bump for traceability,
     or simply clear the block without a version change. Use your judgment, but
     document your reasoning in the internal notes field either way.
  7. Once you approve, the foundation automatically unblocks and becomes usable for
     new matches again immediately. Nothing reaches the live rules engine without
     this explicit approval step; the agent's draft alone never updates anything.

**Turnaround expectation.** Treat this as priority review, outside the normal monthly
review cadence, since new patients are blocked from this foundation until you act.

---

## Alert 3: Daily Change Ticker -- Fetch Failure

**What you'll see.** After a single failed check, an internal log entry only (no email
yet, to avoid over-alerting on a single transient network blip). After three consecutive
failed checks for the same foundation, an email to `test@gmail.com` flagging that the
foundation's source page has been unreachable repeatedly and needs human attention.

**What this means.** The automated check could not reach the foundation's page at all
(site down, URL changed, network issue) for multiple days in a row. An unmonitored
foundation is effectively an unverified one, so this needs a person to intervene rather
than let it silently go stale.

**What to do.**
  1. Try visiting the source page yourself. If it loads fine, the URL stored in
     `source_reference` may be outdated and needs correcting.
  2. If the page has moved or been restructured, update `source_reference` and treat
     this as an opportunity to re-verify the full eligibility rules and template while
     you're there, since a page restructure often coincides with content changes.
  3. If the page is confirmed genuinely down or the foundation program itself may have
     ended, use judgment on whether to temporarily suspend matching against that
     foundation entirely until you can confirm its status.

---

## Alert 4: Risk / Escalation Agent Flags a Case

**What you'll see.** An email to `test@gmail.com` when a patient case is escalated,
either because eligibility data was ambiguous (rules engine could not reach a confident
match or no-match) or because the Risk/Escalation Agent detected signs of distress or
urgency during intake.

**What this means.** The system deliberately does not guess in ambiguous situations. An
escalation means a human needs to make the actual judgment call the system was not
confident enough to make on its own.

**What to do.**
  1. Open the case record and review what data was gathered so far, and why it was
     flagged (missing field, conflicting answer, distress signal, or urgency flag).
  2. Follow up with the patient directly (per the callback flow in
     `orchestration.md`) to fill gaps or address the flagged concern.
  3. Make the actual eligibility or handling decision yourself; the system will not
     proceed further on this case until you do.

---

## General Principles For the Operator

  - The system is designed to hand you judgment calls, not routine work. If you find
    yourself getting flooded with alerts, that is itself a signal worth raising, since
    it likely means a rule or detection threshold needs tuning, not that you should
    start ignoring alerts.
  - Every version increment, every applied update, and every escalation resolution
    should leave a note in the system's audit trail, since the entire point of this
    architecture is that decisions are auditable after the fact.
  - When in doubt on any judgment call, escalate further rather than guess. This
    mirrors the same principle the automated agents themselves follow.
  - All notification email alerts described in this playbook route to the single
    shared address `test@gmail.com`. If this is ever changed, update it consistently
    everywhere, since fragmenting notifications across multiple inboxes was the exact
    problem this design is meant to avoid.
