# Tracking and Observability

This document defines how the system observes itself end to end, turning the data model and
orchestration logic into real, provable outcomes and operational visibility. This is the layer
that produces the proof-of-impact evidence referenced throughout the design doc, and it doubles
as the observability architecture piece of the AI architecture portfolio story.

---

## Purpose

Two distinct audiences need visibility into this system, and they need different things:

1. **Practices** (the referring small oncology practices) need a lightweight, aggregate view
   that proves the tool is working and flags anything requiring their attention, without adding
   any operational burden to them.
2. **The nonprofit's own team** (advocates, and eventually funders such as pharmaceutical
   manufacturers) need detailed, end-to-end, per-case observability to operate the system day to
   day and to produce independently verifiable proof-of-impact reporting.

---

## What Gets Tracked, End to End

Every Patient Case is tracked from first contact through verified outcome, per the data model:

- **Timestamps at every phase transition** (Phase 0 through Phase 5, per orchestration), so the
  full timeline of a case is reconstructable after the fact.
- **Every AI-to-human and human-to-AI handoff**, with structured handback notes, per the
  orchestration design, creating a full audit trail of who did what and when.
- **Rules_version used at the moment of each eligibility decision**, so decisions remain
  explainable against the exact criteria in effect at the time, even after foundation rules
  change later.
- **Outcome data**: funds_approved_amount, funds_applied_timestamp, and verified status,
  answering the causation question directly: did this specific intervention lead to this
  specific dollar outcome landing on the patient's real bill.

## Key Metrics

- **Time to outcome** — from first patient contact to funds actually applied against a real
  bill; the core proof-of-impact metric.
- **Completion rate** — percentage of patients who complete the process versus drop off, and at
  which phase, directly measuring the patient-trust and drop-off-prevention design goals.
- **Escalation rate** — percentage of cases requiring human involvement, and the split between
  quick single-question handbacks versus fully human-led cases; this is the metric that
  determines advocate staffing needs as patient volume grows.
- **Human availability performance** — how often a live human was available on request versus
  routed to voicemail/callback, and how quickly callbacks were completed against the
  urgency-tiered service targets.
- **Verified dollar impact** — total funds independently confirmed as applied to real patient
  bills, the number that eventually supports pitching independently verified impact reporting to
  funders.
- **Foundation data currency** — from the daily ticker, how current and accurate the Foundation
  Reference data has been kept, itself a trust and quality metric for the system.

## Practice-Facing Shadow Dashboard

A lightweight, aggregate-only view for referring practices:

- Aggregate usage stats (for example, number of patients referred, number matched, number
  completed), never individual patient case detail, preserving patient privacy.
- An escalation flag for complex cases, so a practice is aware if one of their patients needed
  significant human involvement, without exposing sensitive case content.
- Explicitly no operational burden: this dashboard is for visibility and reassurance, not a
  worklist the practice is expected to act on, consistent with the zero-touch design principle.

## Internal Advocate and Operations View

- Full case-level detail, current phase, full handoff history and notes, per the orchestration
  and data model.
- The shared escalation queue itself, with urgency tiers, so advocates can see and claim
  available work in real time.
- Foundation Reference health, surfaced from the daily ticker, so stale or flagged data is
  visible operationally, not just logged silently.

## Independent Verification, Not Self-Reported

A deliberate design principle carried through from the original research: outcome data is
tracked as **verified** only when confirmed against the patient's actual bill, not merely when a
foundation or the system itself reports an approval. This distinction is what allows this system
to eventually offer something genuinely differentiated: independently verified, patient-level
proof of impact, rather than the vendor-self-reported outcome data that is the current industry
norm.

## Why This Matters for the AI Architecture Portfolio

This tracking and observability layer is the clearest demonstration of a mature, production-
minded AI architecture: multi-agent handoffs are logged and auditable, decisions are versioned
and explainable after the fact, and system health (foundation data currency, human availability
performance) is monitored continuously rather than assumed. This is the same observability
discipline discussed as the central challenge in AI governance more broadly, applied concretely
to a real, high-stakes patient-facing system.
