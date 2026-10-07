"""
Intake and Conversation Agent (text-only prototype)

Per agent_architecture.md: this agent builds trust, gathers structured
data through natural conversation, and does NOT decide eligibility or
submit anything. It hands off a completed PatientProfile to the
deterministic rules engine.

This is a TEXT-ONLY prototype. No voice yet -- that is still a separate,
deferred piece of work (see orchestration.md's voice/conversation layer
note). Field extraction, however, is now real: this agent uses
LLMFieldExtractor (llm_field_extraction.py) instead of the earlier
keyword-matching stub, so it can robustly parse messy natural language
answers rather than only simple digit/keyword matching.
"""

from dataclasses import dataclass
from typing import Optional
import sys

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules_engine"))
from eligibility_rules import PatientProfile
from llm_field_extraction import LLMFieldExtractor, ExtractionResult


# Ordered list of fields we need before we can run eligibility matching.
# Mirrors the "progressive disclosure" principle from orchestration.md --
# we ask one thing at a time, not a big upfront form.
REQUIRED_FIELDS = [
    ("diagnosis_code", "Can you tell me a bit about your diagnosis or the type of cancer you're being treated for?"),
    ("household_size", "How many people are in your household, including yourself?"),
    ("annual_household_income", "What is your approximate annual household income?"),
    ("insurance_status", "Are you currently uninsured, underinsured, or fully insured?"),
    ("state", "Which state do you live in?"),
]

# Asked once, after the eligibility fields above, per an earlier session's addition:
# capturing how the patient prefers to be reached again later (e.g. if a human
# reviewer needs to follow up for missing or unclear information, per
# human_review.py's targeted recontact flow). Kept separate from
# REQUIRED_FIELDS/PatientProfile on purpose -- this is a contact preference, not
# eligibility data, and the rules engine should never need to know about it.
CONTACT_PREFERENCE_QUESTION = (
    "preferred_contact_channel",
    "If we ever need to reach you again, for example if we need one more piece of "
    "information, how would you prefer we contact you: phone call, text message, "
    "email, or a message through our patient portal?"
)

# Fields that are free-text pass-throughs even under LLM extraction (the model still
# cleans up transcription noise for these, per llm_field_extraction.py's prompt, but
# there is no closed vocabulary to validate against).
FREE_TEXT_FIELDS = {"diagnosis_code", "state"}

# How many times we will re-ask the same question after a low-confidence/unclear
# extraction before giving up and moving on with a None value (rather than looping
# forever on a patient who genuinely cannot give a clearer answer).
MAX_CLARIFICATION_ATTEMPTS = 2


@dataclass
class IntakeConversationState:
    profile: PatientProfile
    current_field_index: int = 0
    hesitation_detected: bool = False
    preferred_contact_channel: Optional[str] = None
    contact_preference_asked: bool = False
    clarification_attempts_on_current_field: int = 0
    last_extraction_was_low_confidence: bool = False


class IntakeAgent:
    """Drives a single patient through structured intake, one question
    at a time, per the Phase 0 trust-building and progressive disclosure
    design in orchestration.md."""

    def __init__(self, llm_extractor: LLMFieldExtractor):
        """llm_extractor is required (not defaulted) so a caller can never
        accidentally construct an IntakeAgent without deciding how field
        extraction actually happens -- see llm_field_extraction.py for how to
        build one, including the fake-function pattern used in tests."""
        self.state = IntakeConversationState(profile=PatientProfile())
        self._extractor = llm_extractor

    def is_complete(self) -> bool:
        """Complete once all eligibility fields AND the contact preference question
        have both been answered."""
        return (
            self.state.current_field_index >= len(REQUIRED_FIELDS)
            and self.state.contact_preference_asked
        )

    def next_question(self) -> Optional[str]:
        if self.state.current_field_index < len(REQUIRED_FIELDS):
            field_name, question = REQUIRED_FIELDS[self.state.current_field_index]
            if self.state.last_extraction_was_low_confidence:
                return self._clarifying_rephrase(field_name, question)
            return question
        if not self.state.contact_preference_asked:
            _, question = CONTACT_PREFERENCE_QUESTION
            if self.state.last_extraction_was_low_confidence:
                return self._clarifying_rephrase(CONTACT_PREFERENCE_QUESTION[0], question)
            return question
        return None

    def _clarifying_rephrase(self, field_name: str, original_question: str) -> str:
        """A gentle, non-repetitive-sounding follow-up when extraction confidence was
        low, per this project's 'never guess' principle: an unclear answer should
        prompt a real clarifying question, not a silent guess passed to the rules
        engine. Kept as simple template text (not another LLM call) since this is
        just a rephrase, not an extraction decision."""
        return (
            "Sorry, I want to make sure I get that right. " + original_question
        )

    def submit_answer(self, raw_answer: str):
        """Takes the patient's free-text answer, extracts the field via the LLM
        extractor, stores it on the profile (or the contact preference, once we've
        reached that step), and advances to the next question -- unless confidence
        was low and we have clarification attempts remaining, in which case we
        re-ask instead of advancing."""
        if self.is_complete():
            return

        # Simple hesitation signal check, per orchestration.md's continuous
        # hesitation monitoring principle -- still template-based here; a full
        # implementation could route this through the LLM too, but hesitation
        # detection is a separate concern from field extraction and is left as-is
        # in this change.
        lowered = raw_answer.lower()
        if any(phrase in lowered for phrase in ["not comfortable", "rather not", "skip", "why do you need"]):
            self.state.hesitation_detected = True

        if self.state.current_field_index < len(REQUIRED_FIELDS):
            field_name, _ = REQUIRED_FIELDS[self.state.current_field_index]
            result = self._extractor.extract_field(field_name, raw_answer)
            self._apply_extraction_result(field_name, result, is_contact_field=False)
            return

        # We're on the contact-preference step now.
        result = self._extractor.extract_contact_channel(raw_answer)
        self._apply_extraction_result(CONTACT_PREFERENCE_QUESTION[0], result, is_contact_field=True)

    def _apply_extraction_result(self, field_name: str, result: ExtractionResult, is_contact_field: bool):
        low_confidence_and_empty = result.value is None or result.confidence == "low"

        if low_confidence_and_empty and self.state.clarification_attempts_on_current_field < MAX_CLARIFICATION_ATTEMPTS:
            # Ask a clarifying follow-up instead of advancing -- never guess.
            self.state.clarification_attempts_on_current_field += 1
            self.state.last_extraction_was_low_confidence = True
            return

        # Either we got a usable value, or we've exhausted clarification attempts
        # and must move on (storing None rather than looping forever on a patient
        # who genuinely cannot give a clearer answer -- a human reviewer can follow
        # up later on any field left as None, per human_review.py's recontact flow).
        if is_contact_field:
            self.state.preferred_contact_channel = result.value
            self.state.contact_preference_asked = True
        else:
            setattr(self.state.profile, field_name, result.value)
            self.state.current_field_index += 1

        self.state.clarification_attempts_on_current_field = 0
        self.state.last_extraction_was_low_confidence = False

    def get_completed_profile(self) -> PatientProfile:
        return self.state.profile

    def get_preferred_contact_channel(self) -> Optional[str]:
        return self.state.preferred_contact_channel
