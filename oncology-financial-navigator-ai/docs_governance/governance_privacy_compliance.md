# Governance, Privacy, and Compliance Considerations

This document covers the privacy, compliance, and governance considerations inherent to a
system that handles sensitive patient medical, financial, and personal information, and that
uses AI in a patient-facing capacity. This is not a substitute for formal legal or compliance
review; it defines the design intent and the questions that must be answered with qualified
counsel before any real deployment.

---

## Core Governance Principle: AI Assists, Humans Decide

Repeated throughout this design, and restated here as the central governance safeguard: the AI
never makes a final, unilateral decision that affects a patient's application or submission. It
gathers information, matches against rules, and prepares documents. A human always reviews and
formally signs off before submission. This narrows the AI's role specifically to reduce
liability and trust risk, and should remain a non-negotiable design constraint through any future
iteration.

## Data Privacy

- **Sensitive data categories handled:** diagnosis and health information, insurance status,
  household income and financial information, personally identifying information. This spans
  both health data and financial data privacy regimes.
- **HIPAA applicability** must be formally assessed with qualified counsel: whether this system,
  its operator, and its foundation partners are covered entities or business associates under
  HIPAA, and what business associate agreements are required with any practice or foundation
  data is exchanged with.
- **Data minimization.** The system should only collect what is strictly necessary for
  eligibility matching and application preparation, consistent with the progressive disclosure
  design already built into orchestration.
- **Practice-facing dashboard privacy.** As defined in tracking and observability, practices see
  only aggregate statistics and escalation flags, never individual patient case detail, by
  design.
- **Data retention policy.** Must be explicitly defined (how long conversation logs, application
  data, and outcome data are retained, and the process for patient-requested deletion), rather
  than retained indefinitely by default.

## Compliance Considerations

- **State and federal health data regulations** beyond HIPAA (for example, state-level health
  data privacy laws) must be reviewed, particularly given plans to eventually operate across
  multiple states and practices.
- **Foundation and program compliance.** Each partner foundation may have its own data handling
  and application submission requirements; these must be reviewed per foundation, not assumed
  uniform.
- **AI-specific disclosure.** Patients should be clearly and explicitly told they are interacting
  with an AI system, not a human, at the start of every conversation, and reminded of the human
  escalation option throughout, consistent with emerging AI transparency norms and patient trust
  research referenced in the original design discussion.
- **Non-diagnostic, non-clinical scope boundary.** The system must be explicitly designed and
  documented to never provide medical advice, diagnosis, or clinical guidance of any kind; its
  scope is strictly financial assistance navigation.

## Open Governance Questions Requiring Qualified Counsel

- HIPAA and business associate agreement scope, as above.
- Nonprofit incorporation structure and 501(c)(3) status process.
- Liability insurance needs for a patient-facing AI system handling financial and health
  information.
- Data sharing agreements with foundation partners.

This document should be revisited and expanded as real answers to these questions are obtained,
rather than treated as final guidance.
