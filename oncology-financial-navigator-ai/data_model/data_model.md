# Data Model

This document defines the core data entities that flow through the system, from first patient
contact through to verified outcome. This is the shared "shape" of information that every agent,
the rules engine, the human reviewer, and the tracking layer all read from and write to.

---

## Core Entity: Patient Case

The central record representing one patient's journey through the system.

- **case_id** — unique identifier for this patient's case.
- **referring_practice_id** — which small oncology practice's link or QR code originated this
  case (referral source only, per the external sources notes).
- **created_at** — timestamp of first patient contact. This is the anchor for all downstream
  causation and outcome tracking.
- **status** — current stage in the workflow (for example: intake_in_progress, matched,
  escalated, in_human_review, submitted, outcome_pending, outcome_verified, closed).
- **patient_profile** — structured data gathered by the Intake and Conversation Agent:
  diagnosis, insurance status, household income, household size, treatment cost information.
- **conversation_log** — record of the intake conversation, retained for quality review and to
  support conversational repair (clarifying follow-ups) without asking the patient to repeat
  themselves.

## Core Entity: Eligibility Match

Represents the output of the Eligibility Matching Agent for a given case.

- **match_id**, **case_id** — identifiers.
- **matched_foundation(s)** — which of the partner foundations (CancerCare, PAF, PAN
  Foundation, LLS Patient Aid) the patient appears eligible for, based on the current rules
  table.
- **match_confidence** — clean match, multiple candidate matches, or ambiguous (triggers
  escalation).
- **rules_version** — which version of the foundation eligibility rules table was used, since
  these criteria change over time and this must be auditable after the fact.

## Core Entity: Escalation

Represents a case (or sub-decision within a case) handed to the Risk and Escalation Agent and
potentially a human Patient Financial Advocate.

- **escalation_id**, **case_id** — identifiers.
- **reason** — why this was escalated (for example: borderline eligibility, distress signal,
  ambiguous multi-foundation decision).
- **urgency_tier** — determines response time target (for example: same-day live contact vs.
  standard queue).
- **assigned_advocate_id** — which advocate picked this up from the shared queue (nullable
  until claimed).
- **resolution** — how it was resolved, feeding back into the rules engine for potential new
  deterministic rules over time.

## Core Entity: Application

Represents the actual foundation application prepared by the Form Preparation Agent.

- **application_id**, **case_id** — identifiers.
- **foundation** — which foundation this specific application targets (a case may have more
  than one Application if applying to multiple foundations).
- **form_data** — the populated form fields.
- **status** — draft, ready_for_review, human_reviewed, submitted, rejected, approved.
- **human_reviewer_id**, **review_timestamp**, **reviewer_acknowledgment** — the human
  sign-off record; no Application can move to submitted without these populated.

## Core Entity: Outcome

The verified, tracked result of a submitted Application. This is the record that closes the loop
back to the original OIG-verification-gap thesis, proving a real dollar outcome resulted from
this specific intervention.

- **outcome_id**, **application_id**, **case_id** — identifiers.
- **funds_approved_amount** — dollar amount approved by the foundation, if any.
- **funds_applied_timestamp** — when the assistance actually applied against the patient's real
  bill (not just when it was approved on paper).
- **verified** — boolean/status indicating whether this outcome has been independently confirmed
  against the patient's actual bill, versus only self-reported by the foundation or practice.
- **time_to_outcome** — calculated from case created_at to funds_applied_timestamp; the key
  proof-of-impact metric for practices, foundations, and eventual funders.

---

## Why This Model Matters Architecturally

This data model is deliberately designed so that **causation, not just activity, is provable**:
every case can be traced from first contact, through which agent or human made which decision,
to a verified dollar outcome, with full timestamps and rules-version auditability at each step.
This is what allows the system to eventually support independently verified impact reporting,
the long-term revenue path discussed for funders such as pharmaceutical manufacturers.


---

## Core Entity: Foundation Reference (External Source Integration)

This is the bridge between the external assistance foundations and the rest of the data model.
It is a small, maintained reference table, not a live case record, holding the current
eligibility rules and application template for each partner foundation.

- **foundation_id** — identifier (CancerCare, PAF, PAN Foundation, LLS Patient Aid, etc).
- **eligibility_rules** — the current structured rules used by the Eligibility Matching Agent
  (income thresholds, diagnosis coverage, insurance requirements).
- **application_template** — the current form structure and required fields used by the Form
  Preparation Agent.
- **rules_version** — incremented each time this foundation's rules or template are updated;
  this is the same version number referenced by the Eligibility Match entity, so every past
  decision remains traceable to the exact rules in effect at the time.
- **last_verified_at** — timestamp of the last time this record was confirmed accurate against
  the foundation's actual published criteria.
- **source_reference** — link or citation to where this data came from (the foundation's own
  published guidelines or application page).

### How Refreshes Happen When a Foundation Updates Its Rules

Foundation eligibility criteria and forms are external and not under this system's control, so
staying current requires a defined, ongoing process rather than a one-time integration:

1. **Scheduled review cadence.** Each foundation reference record is reviewed on a fixed
   schedule (for example, monthly), regardless of whether a change is known to have happened,
   since foundations do not reliably announce changes in advance.
2. **Change monitoring.** Where available, automated monitoring (for example, checking a
   foundation's public eligibility page for changes) flags a record for early review outside the
   normal cadence, rather than waiting for the next scheduled check.
3. **Human verification before activation.** A person, ideally a Patient Financial Advocate who
   understands the practical implications, confirms any detected change against the foundation's
   actual published guidelines before it goes live, since acting on a false or partial change
   could incorrectly reject or approve real patients.
4. **Version increment, not overwrite.** When a change is confirmed, the rules_version number
   increments and the new rules become active going forward. The prior version is retained, not
   deleted, so past decisions remain auditable against the rules that were actually in effect
   when they were made.
5. **In-flight case handling.** Cases already in progress when a rules update happens continue
   under the rules_version they started with, unless the change is favorable to the patient and
   can be reasonably reapplied; this avoids a patient being penalized mid-process by a rule
   tightening they had no way to anticipate.
6. **Escalation feedback loop.** As noted earlier, patterns surfacing repeatedly through the
   Escalation entity can themselves prompt a review of whether a foundation's actual current
   criteria differ from what is recorded, closing the loop between real-world friction and
   reference data accuracy.


---

## Daily Automated Change Ticker (Foundation Source Monitoring)

In addition to the scheduled monthly review, a daily automated ticker actively checks each
partner foundation's published source for changes, rather than relying solely on periodic human
review to catch updates.

- **Frequency.** Runs once per day, per foundation, against each foundation's published
  eligibility guidelines page and application form page (source_reference on the Foundation
  Reference entity).
- **Mechanism.** A scheduled job fetches the current published content and computes a hash or
  structured diff against the last known version stored for that foundation. This detects
  wording, threshold, or form-field changes without requiring a person to manually re-read the
  page every day.
- **No change detected.** The check logs a routine confirmation (last_verified_at updates) and
  nothing further happens; this creates a running audit trail proving the data was actively kept
  current, not just assumed current.
- **Change detected.** The ticker does not update the live rules automatically. Instead, it:
  - Flags the Foundation Reference record for priority human review, outside the normal monthly
    cadence.
  - Notifies a Patient Financial Advocate (or a designated data-maintenance owner) with a
    side-by-side of the old and new content.
  - Blocks the Eligibility Matching Agent from using the affected foundation's rules for new
    matches until a human confirms and increments the rules_version, per the verification step
    already defined above. In-flight cases are handled per the existing rule (they continue
    under their original rules_version).
- **Failure handling.** If a daily check fails to run or a source page is unreachable, this is
  logged and retried, and repeated failures escalate to a human rather than silently going
  stale, since an unmonitored foundation is effectively an unverified one.

This daily ticker is what keeps the Foundation Reference entity genuinely trustworthy over time,
turning "we reviewed this last month" into "we actively check this every single day and a human
signs off on anything that actually changed."
