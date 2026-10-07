# Zero-Touch AI Financial Navigator for Oncology Patients

An AI-guided, human-safeguarded system that connects cancer patients at small, under-resourced
oncology practices to real financial assistance programs, with zero staff effort required from
the practice.

## Why This Exists

Cancer patients face severe, well-documented financial toxicity: cancer patients are more than
twice as likely to declare bankruptcy as those without a cancer diagnosis, and some patients have
depleted their life savings within two years of diagnosis. Fewer than half of community oncology
practices routinely provide financial counselors, and this gap is concentrated at small,
independent practices, well over a million cancer patients a year go through treatment with no
one proactively connecting them to help that already exists. See `01_design_doc.md` for the full
problem statement, market sizing, and competitive landscape.

## What This Is

A patient-facing tool, handed out by a practice via a URL or QR code, where an empathetic
AI-guided conversation helps a patient find and apply to real, established assistance foundations
(CancerCare, the Patient Advocate Foundation, the PAN Foundation, LLS Patient Aid), with a live
human always available as a safety net, and a human always reviewing and signing off before
anything is submitted.

## What This Is Not

- Not a clinical or diagnostic tool; strictly financial assistance navigation.
- Not a decision-maker; the AI prepares, a human always decides and signs off.
- Not a staffed enterprise platform; this is specifically designed for practices with no
  financial navigator on staff, requiring zero operational effort from the practice.

## Repository Structure

- `01_design_doc.md` — problem statement, current manual process, and full proposed solution.
- `agents/` — the four specialized agents (intake/conversation, eligibility matching, form
  preparation, risk/escalation), their responsibilities and boundaries, the human review role,
  escalation management, and external source dependencies.
- `data_model/` — the core data entities (patient case, eligibility match, escalation,
  application, outcome, foundation reference), including the daily automated change ticker that
  keeps foundation eligibility rules and forms current.
- `orchestration/` — how the agents, human review, and supporting systems are wired together
  end to end: the trust-building gate, information gathering, escalation, human handoff
  (including the no-human-available voicemail/callback flow), human-to-AI handback, drop-off
  prevention, and failure handling.
- `tracking_observability/` — how the system tracks outcomes end to end, key metrics, the
  practice-facing shadow dashboard, and the independent-verification approach to proof of impact.
- `docs_governance/` — privacy, compliance, and governance considerations, including open
  questions requiring qualified legal counsel.

## Dual Purpose of This Project

This system is designed to serve two goals at once:

1. **A real nonprofit tool** addressing a large, documented gap in cancer financial toxicity
   support at small oncology practices.
2. **An end-to-end AI architecture demonstration**, showcasing agentic system design,
   multi-agent orchestration, human-in-the-loop safety patterns, data and observability pipeline
   design, and privacy/governance-by-design, in one coherent, real-world system.

## Status

Design and architecture phase complete. Application code has not yet been built; see
`docs_governance/` for open questions to resolve before active build and deployment,
including legal, compliance, and founder-involvement questions.
