# Orchestration

This document defines how the four agents, the human review step, and the supporting systems
(rules engine, foundation reference data, tracking) are actually wired together into one
coherent, end-to-end flow. It also defines state management, wait/timeout behavior, human
handoff behavior, and failure handling.

**Voice/conversation layer assumption:** the Intake and Conversation Agent's spoken interface
will initially use an open-source conversational voice stack (for pilot purposes, to keep cost
near zero), with a future option to migrate to a paid, healthcare-grade empathetic voice platform
(such as Hippocratic AI or ElevenLabs) once the concept is validated. This is a swappable
component behind the same agent interface, not a change to the orchestration logic itself.

---

## Phase 0: Trust-Building (Explicit Gate Before Data Collection)

Per design discussion, the opening conversation is treated as its own distinct phase with its
own success gate, not just the first few turns of generic intake.

- **Goal of this phase:** the patient feels enough comfort and trust to continue, not merely
  that they answered a question.
- **What happens:** the Intake Agent introduces itself, explains what the tool is, names the
  real partner foundations it works with, and explicitly states a human is available by phone or
  video at any time.
- **Gate condition:** the Intake Agent monitors for signals of hesitation, discomfort, or
  resistance in the patient's responses (for example, short/reluctant answers, expressed
  distrust, silence). If detected, the agent slows down, reassures again, or proactively offers
  the live human option, rather than proceeding into structured data collection.
- **Only once this gate passes** does the case move into Phase 1 (structured information
  gathering). This is enforced as an actual orchestration checkpoint, not a soft instruction.

---

## Phase 1: Structured Information Gathering

- Intake Agent conversationally gathers diagnosis, insurance status, household income and size,
  and treatment cost information, per the data model's patient_profile fields.
- Conversational repair (clarifying follow-ups) happens inline, handled by the same agent,
  no handoff needed for this.
- Once sufficient structured data is gathered, the case status updates and control passes to the
  Eligibility Matching Agent.

## Phase 2: Eligibility Matching

- Eligibility Matching Agent checks structured patient data against the current Foundation
  Reference rules (see data model), tagged with the active rules_version.
- **Clean match (single or multiple candidate foundations):** case proceeds to Phase 3.
- **Ambiguous or borderline result:** case is handed to the Risk and Escalation Agent (Phase 2a).

## Phase 2a: Escalation (Conditional Branch)

- Risk and Escalation Agent reasons through the ambiguous case and either resolves it with a
  recommended path forward, or flags it for a live Patient Financial Advocate per the
  urgency-tiered queue defined in the agent architecture.
- A live human can also be requested by the patient at any point in Phases 0-2, not only when
  the system itself escalates; this runs in parallel to, and can interrupt, the AI flow rather
  than requiring the AI conversation to fully end first.
- Once resolved (by the agent or an advocate), the case returns to the main flow at Phase 3.

## Phase 3: Form Preparation

- Form Preparation Agent selects the correct foundation-specific application template(s) from
  the Foundation Reference data and populates them from the patient's structured data.
- Output status: ready_for_review. No submission happens from this step.

## Phase 4: Human Review and Sign-Off

- A Patient Financial Advocate reviews the prepared application for accuracy and
  appropriateness.
- Advocate formally acknowledges with the patient (per design principle: human decides, AI
  prepares).
- Only after this sign-off does application status become eligible to move to submitted.

## Phase 5: Submission and Tracking

- Application is submitted to the matched foundation(s).
- Outcome entity is created, timestamped, and tracked per the data model, through to verified
  funds_applied_timestamp.

---

## Wait, Timeout, and Re-Engagement Behavior

- If a patient goes quiet mid-conversation (any phase before submission), the case is not
  dropped; it holds its current state and status.
- A defined timeout window triggers a gentle, non-pushy automated follow-up (for example, after
  24 hours of inactivity), offering to continue where they left off or to connect with a live
  human instead.
- Repeated non-response after a small number of follow-ups moves the case to a
  low-priority/dormant status, still visible to advocates on the shadow dashboard, rather than
  being silently closed.

## Human Handoff Behavior

- A live human request triggers an attempt to connect the patient to an available Patient
  Financial Advocate in real time (call or video), pulling from the shared escalation queue.
- **If a human is available:** the AI-led conversation pauses for that case (the AI does not
  keep talking in parallel with a live human on the same channel), and the advocate sees the
  same case data the agents have already gathered, so the patient never has to repeat
  themselves.
- **If no human is available:** the system does not simply drop the patient or leave them
  waiting silently. Instead, it clearly and empathetically tells the patient a human is not
  available right now, offers to take a voicemail or message, and asks whether the patient
  wants to leave that message. Once the message is taken, the earliest available advocate is
  notified to follow up with the patient directly (by phone or their preferred contact method)
  as soon as possible.
- **After the message is taken, the AI proactively offers a choice**, rather than leaving the
  patient stuck waiting: it asks whether the patient would like to continue working with the AI
  in the meantime while they wait for the human callback, or would prefer to stop here and wait.
  This keeps the patient moving forward if they want to, without ever pretending a human is
  available when one is not.
- If the patient chooses to continue with the AI after leaving a message, the case proceeds
  through the normal AI-led flow, and the pending human callback is tracked separately (linked
  to the case) so the advocate still follows up as promised, regardless of how far the AI
  conversation gets in the meantime.
- After a live human interaction (real-time or a callback) concludes, the case can either
  continue in the AI-led flow (if the advocate resolved only a specific question) or remain
  human-led through to completion, depending on advocate judgment.

## Failure Handling

- **Agent failure or low-confidence output:** retried once automatically; if it fails again,
  the case escalates to a human rather than looping indefinitely or guessing.
- **Foundation Reference data unavailable or flagged stale** (per the daily ticker): the
  Eligibility Matching Agent is blocked from using that foundation's rules for new matches, per
  the data model's change-detection behavior, and the case is held or redirected to
  alternative foundations if eligible.
- **Any failure that would otherwise leave a patient without a next step** defaults to offering
  the live human option, consistent with the "human safety net always available" design
  principle.

---

## Case State Visibility

Every phase transition updates the Patient Case status field defined in the data model, so at
any moment, an advocate (or the practice-facing shadow dashboard) can see exactly where a given
patient is in the journey: intake_in_progress, matched, escalated, in_human_review, submitted,
outcome_pending, outcome_verified, or closed/dormant.


---

## Reducing Patient Drop-Off During Information Gathering

Because Phase 1 (structured information gathering) is where sustained back-and-forth happens,
and because patients are dealing with a serious diagnosis and financial stress, this phase
carries real risk of hesitation or abandonment. Beyond the Phase 0 trust gate, the following
are built into the ongoing conversation itself, not just the opening:

- **Progressive, not front-loaded, disclosure.** The AI does not ask for all sensitive
  information up front. It gathers information in small, logically grouped steps (for example,
  diagnosis and treatment stage first, financial details later), so the patient never faces a
  long, overwhelming set of questions at once.
- **Explain the "why" before asking sensitive questions.** Before asking for income or household
  details, the AI briefly explains why that specific information is needed (for example, "this
  helps me check which programs you qualify for"), rather than asking cold, which research shows
  reduces perceived intrusiveness and builds continued trust.
- **Visible, honest progress indication.** The patient is told roughly how much is left (for
  example, "just two more quick questions"), so the process feels bounded rather than
  open-ended, which is a known driver of form and conversation abandonment.
- **Continuous, real-time hesitation monitoring, not just at Phase 0.** The same tone and
  hesitation detection used in the trust-building gate continues through the entire information
  gathering phase, not just at the start; if hesitation resurfaces mid-conversation (for example,
  when a sensitive financial question is asked), the agent should pause, reassure, and re-offer
  the live human option again at that specific moment, not just once at the beginning.
- **Save-and-resume by design.** Nothing is lost if a patient stops mid-conversation. Per the
  existing timeout behavior, the case holds state and a gentle follow-up re-engages them,
  explicitly reassuring them they will not need to start over.
- **Low-effort exit that is not a dead end.** If a patient wants to stop, the AI does not treat
  this as a failure state; it offers the voicemail/human-callback path defined above as a
  graceful off-ramp, rather than the conversation simply ending.

---

## Human-to-AI Handback (Partial Human Involvement, Not All-or-Nothing)

A core design goal: when a human advocate steps in, they should be able to do a small piece of
work and hand the rest back to the AI to continue, rather than the case becoming permanently
human-led once a person is involved at all. This keeps the human safety net efficient and
scalable, since advocates should spend time only on the specific piece that needed judgment.

- **Structured handback notes, not just a resolved case.** When an advocate finishes their
  portion of a case (for example, resolving one ambiguous eligibility question, or manually
  confirming a detail the AI could not), they log a short structured note: what was done, what
  the AI should do next, and any specific instruction or caution for the AI to follow going
  forward (for example, "patient is anxious about the income question, be extra gentle there").
- **The AI resumes with full context, not a cold restart.** Just as the advocate saw everything
  the AI had already gathered, the AI resumes with everything the advocate did and noted, so
  the patient is never asked to repeat information or re-explain their situation to the AI after
  a human touched the case.
- **Granular handback, not phase-level.** Handback can happen mid-phase, not just at phase
  boundaries; an advocate might resolve a single question within Phase 1 and immediately return
  the rest of that same phase to the AI, rather than the whole phase needing to be human-led.
  This is what makes "a human does a little bit of work" genuinely possible rather than
  theoretical.
- **Explicit advocate discretion to keep a case human-led.** If an advocate judges that a
  patient specifically needs continued human attention (per their own judgment, not a fixed
  rule), they can flag the case to remain human-led rather than handing back, overriding the
  default handback behavior. This preserves human judgment as the final authority, consistent
  with the core design principle.
- **This handback loop is itself tracked.** Each handoff between AI and human, in either
  direction, is logged with a timestamp on the Patient Case record, so the full journey, who did
  what and when, remains auditable end to end, feeding the same causation and proof-of-impact
  tracking defined in the data model.


---

## Daily Batch Job: Foundation Reference Maintenance (Separate From the Patient Flow)

This is a distinct, separate orchestration flow from the patient-facing Phases 0 through 5
above. It runs on a schedule (once per day, per foundation), independently of any individual
patient case, and its job is to keep the Foundation Reference data (see data_model.md) both
current and safe to keep matching new patients against.

**Step 1: Change detection.** For each registered foundation, `run_daily_check()` in
`foundation_reference_store.py` fetches the foundation's published source content and hashes it
against the last known version. Outcome is one of `no_change`, `change_detected`, or
`fetch_failed`, exactly as defined in the Human Operator Playbook's Alerts 1 through 3.

**Step 2: Automatic drafting (only on `change_detected`).** The Guideline Codification Agent
(Agent 5, see `agent_architecture.md`) is run automatically against the newly fetched content,
producing a `CodificationDraft`: proposed values for income threshold, insurance eligibility,
diagnosis coverage, and required application fields, each tagged with a confidence level and,
where possible, the exact source snippet it was drawn from. This step is fully automated and
requires no human action yet.

**Step 3: Email approval request.** The draft is immediately handed to the Email Approval Loop
(`email_approval_loop.py`), which formats it into a plain-language email and creates a Gmail
draft addressed to the reviewer. Per the platform's current tool limitations, a person must
open Gmail and click Send once to actually deliver this email; this is the one manual touchpoint
in an otherwise automated pipeline (see local_setup_and_testing.md, section 7a, for the full
setup detail).

**Step 4: Human review by reply.** The reviewer reads the draft email, checks it against the
foundation's actual published page, and replies directly in the same thread with the single
keyword `APPROVE` or `REJECT`. No dashboard, form, or separate tool is needed for this step by
design, keeping the reviewer's actual workload to reading one email and sending one short reply.

**Step 5: Automatic application on approval.** When the approval check next runs, it reads the
reply. An unambiguous `APPROVE` automatically calls `apply_human_reviewed_update()`, which
increments the foundation's rules_version, updates the live rules engine, and unblocks the
foundation for new patient matches, all without further manual steps. A `REJECT`, an ambiguous
reply containing both keywords, or a reply with no recognized keyword at all results in no
change being applied and the foundation remaining blocked, consistent with this system's
"never guess" principle; the human owner should then follow up manually outside this flow.

**Relationship to the patient-facing flow.** These two flows only intersect at one point: while
a foundation is blocked (between `change_detected` and an approved update), Phase 2 (Eligibility
Matching) cannot return that foundation as a new match for any patient, per the Failure Handling
section above. In-flight cases that were already matched under a previous rules_version are
completely unaffected and continue under that version, regardless of what happens in this batch
flow.
