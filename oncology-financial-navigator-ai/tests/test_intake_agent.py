"""
Tests for the Intake Agent (app/agents/intake_agent.py), now backed by real
LLM-based field extraction (llm_field_extraction.py) instead of the earlier
keyword-matching stub.

Uses a small fake LLM function simulating realistic patient answers, so these tests
exercise the full agent -> extractor -> validation pipeline without any real model
call. Focus areas: a full clean conversation completing correctly end to end, and the
low-confidence clarification retry / eventual give-up-with-None behavior, which is the
main new piece of logic this change introduced.
"""

import json
import pytest

from intake_agent import IntakeAgent, MAX_CLARIFICATION_ATTEMPTS
from llm_field_extraction import LLMFieldExtractor


def _clean_answers_llm(prompt: str) -> str:
    """Simulates a competent real model giving confident, correct answers for a
    full, clean intake conversation."""
    lower = prompt.lower()
    answer_section = prompt.rsplit("Patient's answer:", 1)[-1].strip().strip('"').lower()

    if "total number of people in the patient" in lower:
        return json.dumps({"value": 3, "confidence": "high"})
    if "annual household income" in lower:
        return json.dumps({"value": 45000, "confidence": "high"})
    if "uninsured" in lower and "underinsured" in lower and "classify" in lower:
        return json.dumps({"value": "uninsured", "confidence": "high"})
    if "preferred contact method" in lower:
        return json.dumps({"value": "sms", "confidence": "high"})
    # diagnosis / state free text
    return json.dumps({"value": answer_section.title(), "confidence": "high"})


def _always_unclear_llm(prompt: str) -> str:
    return json.dumps({"value": None, "confidence": "low"})


@pytest.fixture
def clean_agent():
    return IntakeAgent(llm_extractor=LLMFieldExtractor(llm_call_fn=_clean_answers_llm))


@pytest.fixture
def unclear_agent():
    return IntakeAgent(llm_extractor=LLMFieldExtractor(llm_call_fn=_always_unclear_llm))


def test_full_clean_conversation_completes_correctly(clean_agent):
    assert clean_agent.next_question() is not None
    clean_agent.submit_answer("breast cancer, stage two")
    clean_agent.submit_answer("three people including me")
    clean_agent.submit_answer("about 45 thousand a year")
    clean_agent.submit_answer("I don't have insurance")
    clean_agent.submit_answer("Ohio")
    assert not clean_agent.is_complete()  # contact preference still pending
    clean_agent.submit_answer("text message please")

    assert clean_agent.is_complete()
    profile = clean_agent.get_completed_profile()
    assert profile.household_size == 3
    assert profile.annual_household_income == 45000
    assert profile.insurance_status == "uninsured"
    assert profile.state == "Ohio"
    assert clean_agent.get_preferred_contact_channel() == "sms"


def test_questions_are_asked_in_order(clean_agent):
    q1 = clean_agent.next_question()
    assert "diagnosis" in q1.lower()
    clean_agent.submit_answer("lung cancer")
    q2 = clean_agent.next_question()
    assert "household" in q2.lower()


def test_low_confidence_answer_triggers_rephrased_clarifying_question(unclear_agent):
    unclear_agent.submit_answer("first answer, will be unclear")
    second_question = unclear_agent.next_question()
    assert second_question.startswith("Sorry, I want to make sure I get that right.")
    # Field index should not have advanced yet -- still on the first field.
    assert unclear_agent.state.current_field_index == 0


def test_gives_up_after_max_clarification_attempts_and_advances_with_none(unclear_agent):
    # Answer the same (first) field MAX_CLARIFICATION_ATTEMPTS + 1 times with unclear
    # answers; it should advance to the next field afterward, storing None.
    for _ in range(MAX_CLARIFICATION_ATTEMPTS + 1):
        unclear_agent.submit_answer("still unclear")

    assert unclear_agent.state.current_field_index == 1
    assert unclear_agent.get_completed_profile().diagnosis_code is None


def test_clarification_attempts_reset_between_fields(clean_agent, unclear_agent):
    # Exhaust clarification attempts on the first field, then confirm the *next*
    # field starts fresh (attempts counter reset to 0), rather than carrying over.
    for _ in range(MAX_CLARIFICATION_ATTEMPTS + 1):
        unclear_agent.submit_answer("still unclear")
    assert unclear_agent.state.clarification_attempts_on_current_field == 0


def test_submit_answer_after_completion_is_a_no_op(clean_agent):
    clean_agent.submit_answer("breast cancer")
    clean_agent.submit_answer("three people")
    clean_agent.submit_answer("45000")
    clean_agent.submit_answer("uninsured")
    clean_agent.submit_answer("Ohio")
    clean_agent.submit_answer("text")
    assert clean_agent.is_complete()

    profile_before = clean_agent.get_completed_profile()
    clean_agent.submit_answer("this should be ignored")
    profile_after = clean_agent.get_completed_profile()
    assert profile_before == profile_after


def test_hesitation_phrase_is_detected():
    agent = IntakeAgent(llm_extractor=LLMFieldExtractor(llm_call_fn=_clean_answers_llm))
    agent.submit_answer("I'd rather not say why you need that")
    assert agent.state.hesitation_detected is True


def test_next_question_returns_none_once_complete(clean_agent):
    clean_agent.submit_answer("breast cancer")
    clean_agent.submit_answer("three people")
    clean_agent.submit_answer("45000")
    clean_agent.submit_answer("uninsured")
    clean_agent.submit_answer("Ohio")
    clean_agent.submit_answer("text")
    assert clean_agent.next_question() is None
