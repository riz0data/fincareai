"""
run_demo.py -- Oncology Financial Navigator, local demo walkthrough

Run this with:   python3 run_demo.py

This simulates ONE patient going through the Intake Agent (with a fake LLM
standing in for a real model call, so this runs instantly with no API key
needed) and then matches that patient against a few sample assistance
foundations using the real, deterministic rules engine.

Nothing here is hardcoded eligibility logic -- the rules engine making the
match/no-match/ambiguous decision is the same real code used throughout the
project. Only the LLM call itself is faked, purely so this demo doesn't need
an API key to run tonight.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "agents"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "rules_engine"))

from intake_agent import IntakeAgent
from llm_field_extraction import LLMFieldExtractor
from eligibility_rules import FoundationRule, match_all_foundations, MatchConfidence


def fake_llm(prompt: str) -> str:
    """Stands in for a real model call during this demo. A real deployment
    would call Claude, GPT, or similar here instead -- see the commented-out
    example at the bottom of app/agents/llm_field_extraction.py."""
    lower = prompt.lower()
    answer_section = prompt.rsplit("Patient's answer:", 1)[-1].strip().strip('"').lower()

    if "total number of people in the patient" in lower:
        return json.dumps({"value": 3, "confidence": "high"})
    if "annual household income" in lower:
        return json.dumps({"value": 32000, "confidence": "high"})
    if "uninsured" in lower and "underinsured" in lower and "classify" in lower:
        return json.dumps({"value": "uninsured", "confidence": "high"})
    if "preferred contact method" in lower:
        return json.dumps({"value": "sms", "confidence": "high"})
    # Simple cleanup for the free-text demo fields (diagnosis/state) so the
    # printed output looks like a real extracted value, not the raw sentence.
    if "field \'state\'" in lower:
        for state_name in ["ohio", "california", "texas", "florida", "new york", "pennsylvania"]:
            if state_name in answer_section:
                return json.dumps({"value": state_name.title(), "confidence": "high"})
    if "field \'diagnosis_code\'" in lower:
        if "breast" in answer_section:
            return json.dumps({"value": "Breast Cancer, Stage II", "confidence": "high"})
    return json.dumps({"value": answer_section.title(), "confidence": "high"})


SAMPLE_ANSWERS = [
    "I was just diagnosed with breast cancer, stage two.",
    "There are three of us at home, me, my husband, and our son.",
    "We make about 32 thousand dollars a year combined.",
    "I don't have any health insurance right now.",
    "I live in Ohio.",
    "Text message is easiest for me.",
]


SAMPLE_FOUNDATIONS = [
    FoundationRule(
        foundation_id="cancercare_001",
        name="CancerCare Co-Payment Assistance Foundation",
        max_income_multiplier_of_poverty_line=5.0,
        eligible_diagnoses=[],
        eligible_insurance_statuses=["uninsured", "underinsured"],
    ),
    FoundationRule(
        foundation_id="pan_foundation_001",
        name="PAN Foundation",
        max_income_multiplier_of_poverty_line=4.0,
        eligible_diagnoses=[],
        eligible_insurance_statuses=[],
    ),
    FoundationRule(
        foundation_id="high_bar_foundation_001",
        name="Example Strict-Income Foundation",
        max_income_multiplier_of_poverty_line=0.9,
        eligible_diagnoses=[],
        eligible_insurance_statuses=[],
    ),
]


def main():
    print("=" * 70)
    print("ONCOLOGY FINANCIAL NAVIGATOR -- LOCAL DEMO")
    print("=" * 70)
    print()
    print("Step 1: Patient Intake Conversation (simulated)")
    print("-" * 70)

    extractor = LLMFieldExtractor(llm_call_fn=fake_llm)
    agent = IntakeAgent(llm_extractor=extractor)

    answer_index = 0
    while not agent.is_complete():
        question = agent.next_question()
        print("\n  Navigator asks: " + question)
        answer = SAMPLE_ANSWERS[answer_index] if answer_index < len(SAMPLE_ANSWERS) else "not sure"
        print("  Patient answers: \"" + answer + "\"")
        agent.submit_answer(answer)
        answer_index += 1

    profile = agent.get_completed_profile()
    contact_channel = agent.get_preferred_contact_channel()

    print()
    print("Step 2: Structured data handed to the rules engine")
    print("-" * 70)
    print("  Diagnosis: " + str(profile.diagnosis_code))
    print("  Household size: " + str(profile.household_size))
    print("  Annual household income: $" + format(profile.annual_household_income, ",.0f"))
    print("  Insurance status: " + str(profile.insurance_status))
    print("  State: " + str(profile.state))
    print("  Preferred contact channel: " + str(contact_channel))

    print()
    print("Step 3: Deterministic eligibility matching (no AI, auditable rules)")
    print("-" * 70)
    results = match_all_foundations(profile, SAMPLE_FOUNDATIONS)
    label_map = {"match": "YES", "no_match": "no", "ambiguous": "AMBIGUOUS -> escalate to human"}
    for foundation in SAMPLE_FOUNDATIONS:
        result = results[foundation.foundation_id]
        symbol = label_map[result.value]
        print("  " + foundation.name + ": " + symbol)

    print()
    print("=" * 70)
    print("Done. In the real system, any MATCH would now be handed to the")
    print("Form Preparation Agent to auto-fill the real application, which a")
    print("human always reviews before anything is submitted.")
    print("=" * 70)


if __name__ == "__main__":
    main()
