"""
LangGraph Orchestration: Intake -> Eligibility Matching -> Escalation / Human Review

Wires together the real modules already built and tested in this repo:
  - app/agents/intake_agent.py       (IntakeAgent, text-only prototype)
  - app/rules_engine/eligibility_rules.py  (PatientProfile, FoundationRule,
                                             match_all_foundations, MatchConfidence)
  - app/data/entities.py             (PatientCase, EligibilityMatch, Escalation, CaseStatus)

This implements, as a LangGraph StateGraph, the first slice of the phase design in
orchestration.md:
    Phase 1 (Structured Information Gathering)
      -> Phase 2 (Eligibility Matching)
      -> Phase 2a (Escalation) if ambiguous
      -> Phase 4 (Human Review) if a match is found

IMPORTANT NOTE ON VALIDATION:
This graph was written and reasoned through carefully against the real LangGraph API
(StateGraph, TypedDict state, add_node, add_edge, add_conditional_edges, START, END),
matching the pattern used throughout LangGraph's own documentation and examples.
However, LangGraph could not be installed in the sandbox this repo was built in
(no package index access), so this file has NOT been executed end-to-end on this
machine. Before relying on it, run it locally per docs_governance/local_setup_and_testing.md
and confirm it behaves as expected -- treat this as reviewed-but-unverified code,
not as proven code, until you've run it yourself.
"""

import os
import sys
from typing import TypedDict, Optional, List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules_engine"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

from intake_agent import IntakeAgent
from eligibility_rules import FoundationRule, match_all_foundations, MatchConfidence
from entities import PatientCase, EligibilityMatch, Escalation, CaseStatus, UrgencyTier

from langgraph.graph import StateGraph, START, END


# --- Placeholder foundation list -----------------------------------------------------
# In production this is loaded from the Foundation Reference store (data_model.md),
# refreshed by the daily automated change ticker. Hardcoded here only to make this
# graph runnable end to end as a first slice.
KNOWN_FOUNDATIONS: List[FoundationRule] = [
    FoundationRule(
        foundation_id="cancercare_copay",
        name="CancerCare Co-Payment Assistance",
        max_income_multiplier_of_poverty_line=5.0,
        eligible_insurance_statuses=["underinsured", "uninsured"],
    ),
]


# --- Graph State ------------------------------------------------------------------
# LangGraph passes a single state object between nodes. We keep it as a TypedDict,
# the standard, documented LangGraph pattern, rather than inventing a custom object.
class NavigatorState(TypedDict, total=False):
    case: PatientCase
    intake_agent: IntakeAgent
    simulated_answers: List[str]           # test harness only, see bottom of file
    simulated_answer_index: int            # test harness only, see bottom of file
    eligibility_match: Optional[EligibilityMatch]
    escalation: Optional[Escalation]
    next_step: str                         # used to drive conditional routing


# --- Node: Intake -------------------------------------------------------------------
def intake_node(state: NavigatorState) -> NavigatorState:
    """Drives the IntakeAgent through all required questions.
    In a real deployment this node would pause after each question and wait for the
    next real user turn; for this first prototype slice it drains a simulated answer
    list synchronously so the whole graph can be exercised in one run (see
    docs_governance/local_setup_and_testing.md for how to test this properly, including
    swapping this for real turn-by-turn interaction)."""
    agent = state["intake_agent"]
    answers = state["simulated_answers"]
    idx = state.get("simulated_answer_index", 0)

    while not agent.is_complete() and idx < len(answers):
        agent.submit_answer(answers[idx])
        idx += 1

    state["case"].patient_profile = agent.get_completed_profile()
    state["simulated_answer_index"] = idx
    return state


# --- Node: Eligibility Matching (deterministic, no AI) -------------------------------
def eligibility_node(state: NavigatorState) -> NavigatorState:
    """Calls the deterministic rules engine directly. Per agent_architecture.md and
    01_design_doc.md, eligibility decisions are NEVER made by an LLM."""
    profile = state["case"].patient_profile
    results = match_all_foundations(profile, KNOWN_FOUNDATIONS)

    matched_ids = [fid for fid, confidence in results.items() if confidence == MatchConfidence.MATCH]
    is_ambiguous = any(confidence == MatchConfidence.AMBIGUOUS for confidence in results.values())

    match_confidence = "ambiguous" if is_ambiguous else ("match" if matched_ids else "no_match")

    state["eligibility_match"] = EligibilityMatch(
        case_id=state["case"].case_id,
        matched_foundation_ids=matched_ids,
        match_confidence=match_confidence,
        rules_version=KNOWN_FOUNDATIONS[0].rules_version if KNOWN_FOUNDATIONS else None,
    )

    # Route based on outcome -- this drives the conditional edge below.
    if is_ambiguous:
        state["next_step"] = "escalate"
    elif matched_ids:
        state["next_step"] = "human_review"
    else:
        state["next_step"] = "no_match_end"

    return state


# --- Node: Escalation (ambiguous case -> human advocate) -----------------------------
def escalation_node(state: NavigatorState) -> NavigatorState:
    """Per agent_architecture.md: ambiguous cases are never guessed on, they are
    routed to a human Patient Financial Advocate."""
    state["escalation"] = Escalation(
        case_id=state["case"].case_id,
        reason="Eligibility matching returned an ambiguous result (missing or unrecognized data).",
        urgency_tier=UrgencyTier.STANDARD,
    )
    state["case"].status = CaseStatus.ESCALATED
    return state


# --- Node: Human Review (match found -> awaiting sign-off) ---------------------------
def human_review_node(state: NavigatorState) -> NavigatorState:
    """Per agent_architecture.md and data_model.md: a match never auto-submits.
    It always stops here, awaiting human sign-off. Application preparation
    (Form Preparation Agent) is a later build step that would run before this node
    in a fuller graph."""
    state["case"].status = CaseStatus.AWAITING_HUMAN_REVIEW
    return state


# --- Node: No match end ---------------------------------------------------------------
def no_match_node(state: NavigatorState) -> NavigatorState:
    """No foundation matched. In a fuller build this would trigger the orchestration.md
    'graceful non-dead-end exit' -- offering the live human path rather than a dead end.
    Marked here as a clear extension point."""
    state["case"].status = CaseStatus.COMPLETE
    return state


# --- Conditional routing function -----------------------------------------------------
def route_after_eligibility(state: NavigatorState) -> str:
    """Reads the next_step flag set by eligibility_node and tells LangGraph which
    node to go to next. This is the standard LangGraph conditional-edge pattern."""
    return state["next_step"]


# --- Build the graph --------------------------------------------------------------
def build_navigator_graph():
    graph = StateGraph(NavigatorState)

    graph.add_node("intake", intake_node)
    graph.add_node("eligibility", eligibility_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("no_match_end", no_match_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "eligibility")

    # Conditional branch out of eligibility, matching orchestration.md's Phase 2 / 2a split.
    graph.add_conditional_edges(
        "eligibility",
        route_after_eligibility,
        {
            "escalate": "escalation",
            "human_review": "human_review",
            "no_match_end": "no_match_end",
        },
    )

    graph.add_edge("escalation", END)
    graph.add_edge("human_review", END)
    graph.add_edge("no_match_end", END)

    return graph.compile()


# --- Local test harness ---------------------------------------------------------------
# Run this file directly (after installing langgraph locally, per
# docs_governance/local_setup_and_testing.md) to exercise the graph end to end with
# the same simulated conversation used to test intake_agent.py earlier in this build.
if __name__ == "__main__":
    compiled_graph = build_navigator_graph()

    case = PatientCase(referring_practice_id="practice_001")

    initial_state: NavigatorState = {
        "case": case,
        "intake_agent": IntakeAgent(),
        "simulated_answers": [
            "I have breast cancer, stage two",
            "three",                 # deliberately fixed vs. earlier bug ("There's three of us at home")
            "around 58000 a year",
            "I would say we are underinsured",
            "North Carolina",
        ],
        "simulated_answer_index": 0,
    }

    final_state = compiled_graph.invoke(initial_state)

    print("Final case status:", final_state["case"].status)
    print("Eligibility match:", final_state["eligibility_match"])
    print("Escalation:", final_state.get("escalation"))
