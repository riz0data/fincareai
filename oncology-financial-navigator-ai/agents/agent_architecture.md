# Agent Architecture

This document defines the specialized agents that collaborate behind the scenes to move a
patient case from first contact through to a submitted, human-reviewed financial assistance
application. It also defines the boundary between agent judgment and deterministic rule-based
logic, per the core design principle established in the design doc.

---

## Design Principle Recap

- The **conversation itself** is agent-led, because patients describe their situations in
  natural, unstructured, often emotional language that a rigid form handles poorly.
- **Eligibility decisions** are deterministic, rule-based logic wherever possible, for
  auditability, predictability, and zero hallucination risk on decisions that affect real
  financial applications.
- Agents are pulled back in specifically for **conversational repair** (clarifying incomplete
  answers) and **genuinely ambiguous or borderline cases** the rules engine cannot cleanly
  resolve.
- A **human always reviews and signs off** before anything is submitted. No agent submits an
  application unilaterally.

---

## Agent 1: Intake and Conversation Agent

**Role:** The patient-facing voice of the system. Opens the interaction, builds trust, and
conducts the natural-language conversation that gathers the patient's situation.

**Responsibilities:**
- Open with an empathetic, plain-language introduction: what this tool is, that it connects to
  real, established assistance foundations, and that a human is available at any time.
- Conversationally gather diagnosis, insurance status, household income and size, and treatment
  cost information.
- Ask natural clarifying follow-up questions when an answer is incomplete or ambiguous.
- Hand off structured, clean data to the Eligibility Matching Agent once gathered.

**Explicitly does not:** decide eligibility, fill out or submit any application, or make any
financial determination.

---

## Agent 2: Eligibility Matching Agent

**Role:** Applies deterministic rules to the structured data gathered by the Intake Agent,
matching the patient against real foundation eligibility criteria (for example, CancerCare,
the Patient Advocate Foundation, the PAN Foundation, LLS Patient Aid).

**Responsibilities:**
- Run the patient's structured data against a maintained, auditable rules table of foundation
  eligibility criteria (income thresholds, diagnosis coverage, insurance requirements).
- Return a clean match, multiple candidate matches, or flag the case as ambiguous.
- Escalate ambiguous or borderline cases (for example, a patient just outside one foundation's
  income cutoff) to the Risk and Escalation Agent for further reasoning rather than a flat
  rejection.

**Explicitly does not:** interpret free-text conversation directly; only operates on
structured data handed to it.

---

## Agent 3: Form Preparation Agent

**Role:** Prepares the actual application, populating the correct foundation-specific form with
the patient's structured data, modeled on Dollar For's proven auto-fill pattern.

**Responsibilities:**
- Select the correct application template for the matched foundation.
- Populate all required fields accurately from the structured patient data.
- Assemble any required supporting documentation checklist for the patient.
- Pass the completed, unsubmitted application to human review.

**Explicitly does not:** submit any application. Output always stops at "ready for human
review."

---

## Agent 4: Risk and Escalation Agent

**Role:** The judgment layer. Handles the cases that do not cleanly resolve through
deterministic rules, and is the trigger point for pulling in a live human.

**Responsibilities:**
- Reason through borderline or ambiguous eligibility cases (for example, weighing whether to
  pursue two foundations in parallel or in sequence).
- Detect signals of distress, urgency, or complexity that warrant immediate live human contact
  rather than continued AI conversation.
- Flag cases for the practice-facing shadow dashboard when a case needs human attention.

**Explicitly does not:** override a human reviewer's final decision; this agent recommends and
escalates, it does not have final authority.

---

## Agent 5: Guideline Codification Agent

**Role:** Reads the raw, unstructured guideline text fetched by the Daily Automated Change
Ticker (in `foundation_reference_store.py`) and drafts a proposed structured rule update, so a
human reviewer edits and approves a draft rather than writing eligibility logic from scratch
every time a foundation's page changes.

**Trigger:** Runs automatically as part of the same daily batch job as the ticker, immediately
after `run_daily_check()` returns `"change_detected"` for a given foundation. It is not a
standalone or on-demand agent; it only activates on a detected content change.

**Responsibilities:**
- Take the newly fetched guideline content (and, where available, the previous known version)
  as input.
- Extract candidate structured fields in the same shape the rules engine already expects:
  income threshold (as a multiplier of the federal poverty line), eligible insurance statuses,
  diagnosis coverage, and required application fields.
- Produce a clearly labeled **draft**, never a final rule: the output is a proposed
  `FoundationRule`-shaped object plus a plain-language summary of what appears to have changed
  since the last version, so the human reviewer does not have to re-read the entire source page
  from scratch to spot the delta.
- Flag its own confidence and call out ambiguous or unclear source text explicitly, rather than
  guessing silently, consistent with the project's zero-hallucination principle for anything
  that affects real eligibility decisions.
- Hand the draft to the same human-review step already used elsewhere (per the Human Operator
  Playbook, Alert 2), where an operator compares it against the live source page, edits as
  needed, and only then calls `apply_human_reviewed_update()` to actually version and activate
  it.

**Explicitly does not:** call `apply_human_reviewed_update()` itself, update the live rules
engine directly, or unblock a foundation for new matches. Its output is always a draft awaiting
explicit human sign-off, exactly like every other agent-produced artifact in this system.

**Why not a vector database:** this agent processes one already-identified document at a time,
the specific page the ticker just fetched for one specific foundation, so there is no
similarity search or retrieval-across-many-documents step involved. This is a structured
extraction task, not a retrieval task.

---

## Human Review and Sign-Off (Not an Agent, By Design)

A human reviewer checks every prepared application for accuracy and appropriateness, and
formally acknowledges it with the patient before submission. This is a deliberate design
boundary, not an agent, to keep final accountability with a person.

---

## Orchestration Summary (Handoff Flow)

Patient contact -> Intake and Conversation Agent -> (structured data) -> Eligibility Matching
Agent -> (clean match) -> Form Preparation Agent -> (ambiguous case) -> Risk and Escalation
Agent -> (live human requested at any point) -> Human Review and Sign-Off -> Submission ->
Tracking and Observability.

Full orchestration logic (state management, triggers, and failure handling) is defined
separately in the orchestration artifact.


---

## Human Reviewer Role: Qualifications and Escalation Management

### Who Handles Escalations

Escalated cases should route to a trained **Patient Financial Advocate**, a role modeled closely
on the real, established "oncology financial navigator" job function. This is not a generic
support agent; the role requires:

- Working knowledge of insurance structures (Medicare, Medicaid, private, underinsured
  scenarios) and how they interact with foundation eligibility rules.
- Familiarity with the specific application requirements of the core partner foundations
  (CancerCare, Patient Advocate Foundation, PAN Foundation, LLS Patient Aid).
- Trained communication skills for speaking with patients in a vulnerable emotional and
  financial state, similar in spirit to Dollar For's centralized Patient Advocate review model,
  where a human reviews every case before it goes out, regardless of which hospital or practice
  the patient came from.

Because the practices themselves have no financial navigation staff (that is the gap this
project exists to close), these advocates are part of the nonprofit's own central team, not
practice employees. This mirrors Dollar For's model of a small, central team of advocates
serving patients across many unaffiliated sites, rather than each site staffing its own.

### Escalation Queue and Workflow Management

- **Tiered routing.** Not all escalations are equal. The Risk and Escalation Agent should tag
  each case with a reason and urgency level when it hands off, for example: "borderline
  eligibility, no urgency" versus "patient distress signal, needs live contact today."
- **Shared queue, not 1:1 assignment.** Escalated cases enter a shared queue visible to all
  available advocates, rather than being locked to one person, so a case is not stuck waiting on
  a single advocate's availability.
- **Service-level targets by tier.** For example, a live-contact-requested or distress-flagged
  case should be responded to within a defined short window (such as same business day), while a
  routine borderline-eligibility case awaiting a judgment call can queue for standard review
  turnaround.
- **Caseload-based staffing ratio.** The number of advocates needed scales with patient
  volume and escalation rate, not with the number of practices. As real pilot data comes in on
  what percentage of cases actually escalate, this ratio should be measured and used to plan
  hiring, rather than assumed upfront.
- **Every escalation still ends at human sign-off.** Regardless of tier, the same human review
  and acknowledgment step applies before any application is submitted; escalation determines who
  spends more time and judgment on the case, not whether a human is involved at all, since a
  human is already involved in every case by design.
- **Escalation outcomes feed back into the rules engine.** When an advocate resolves an
  ambiguous case, that resolution should be logged and periodically reviewed so genuinely
  recurring patterns can be turned into new deterministic rules over time, reducing future
  escalations for the same scenario.


---

## External Sources and Dependencies

This system does not create new assistance money or new eligibility programs, it orchestrates
access to real, existing external sources. These are the key external dependencies the workflow
relies on:

### Assistance Foundations (Eligibility Rules and Funding)
- **CancerCare Co-Payment Assistance Foundation** — copay and treatment cost assistance.
- **Patient Advocate Foundation (PAF) Co-Pay Relief** — copay assistance and free case
  management; PAF and the PAN Foundation announced a merger in March 2026, so this may
  consolidate into a single partner relationship over time.
- **PAN Foundation** — copay assistance across a range of diagnoses.
- **LLS Patient Aid Program** — assistance specific to blood cancers.

Each foundation is an external source of both **eligibility criteria** (feeding the Eligibility
Matching Agent's rules table) and **application forms** (feeding the Form Preparation Agent's
templates). These criteria and forms change over time and must be monitored and kept current,
this is a real, ongoing maintenance dependency, not a one-time integration.

### Practices (Patient Referral Source)
Small independent oncology practices are the entry point into the workflow, handing patients the
URL or QR code. The practice is a source of patient referral only, not a source of eligibility
data or funds, consistent with the zero-touch, zero-staff-effort design principle.

### Insurance Status Verification
Patient-reported insurance information (Medicare, Medicaid, private, underinsured) feeds
eligibility logic. A future, more advanced version of this system could integrate directly with
insurance eligibility verification services rather than relying solely on patient self-report,
though the initial design relies on patient-reported data reviewed by a human.

### Human Advocate Network
As defined above, the pool of trained Patient Financial Advocates is an internal resource, not
external, but is worth naming here as the "external-facing" layer between this system and the
live phone or video safety net promised to patients.

### Precedent and Design Template Sources (Not Live Dependencies)
Two real-world organizations informed this design but are not integrated dependencies:
- **Dollar For**, whose self-serve-plus-automation-plus-human-review workflow for hospital
  charity care is the direct model for this system's Form Preparation Agent and human
  sign-off pattern.
- **TailorMed**, whose staffed, enterprise-oriented model at larger health systems defines the
  competitive gap this zero-touch design is built to fill for small, under-resourced practices.
