"""
LLM-Based Field Extraction for the Intake Agent

Replaces the earlier stub_extract_field() / stub_extract_contact_channel() keyword
matching with real LLM-based extraction, so the Intake Agent can robustly parse messy,
natural patient language (for example, "I've got about three people at home, my wife
and our daughter" -> household_size=3) instead of only simple keyword/digit matching.

Design principles this follows, per agent_architecture.md and this project's core
principle throughout:
  - The Intake Agent (and this extraction layer) NEVER decides eligibility. It only
    ever produces structured field values for the deterministic rules engine to later
    evaluate. No eligibility logic of any kind lives here.
  - Never guess silently. If the LLM cannot confidently extract a field from the
    patient's answer, this module returns None (per field) rather than fabricating a
    plausible-sounding value, exactly like the stub layer it replaces. A None value
    should prompt the Intake Agent to ask a gentle clarifying follow-up, never to fall
    through into the rules engine as if it were real data.
  - Provider-agnostic by design, same pattern as email_approval_loop.py's injected
    send_email_fn/search_replies_fn: this module takes an injected `llm_call_fn`
    rather than hardcoding a call to any specific provider's SDK, so it can be tested
    with a fake/deterministic function and wired to a real model later without
    changing any of the extraction logic itself.
  - Structured output, not free text. The LLM is asked to return JSON matching an
    explicit, narrow schema for exactly one field at a time, which keeps each call
    small, auditable, and easy to validate -- a human reviewer or a test can see
    exactly what was asked and what came back.
"""

import json
from dataclasses import dataclass
from typing import Optional, Callable, Any


# The strict, narrow set of values allowed per categorical field. Extraction results
# outside this set are treated as low-confidence/unrecognized rather than accepted --
# same "never guess" principle as the rules engine and the codification agent.
INSURANCE_STATUS_VALUES = ["uninsured", "underinsured", "insured"]
CONTACT_CHANNEL_VALUES = ["phone_call", "sms", "email", "portal_message"]


@dataclass
class ExtractionResult:
    """Result of one field extraction attempt. `value` is None whenever the model
    could not confidently extract the field -- callers must treat None as "ask a
    clarifying follow-up", never as a value to hand to the rules engine."""
    field_name: str
    value: Optional[Any]
    confidence: str  # "high", "medium", "low"
    raw_model_output: Optional[str] = None


# --- Per-field extraction prompts ----------------------------------------------------
# Each prompt is deliberately narrow (one field at a time) and asks for strict JSON,
# so the response is trivial to validate and so a human reviewing this file can see
# exactly what is being asked of the model for each field, with no hidden logic.

def _build_prompt(field_name: str, raw_answer: str) -> str:
    common_instructions = (
        "You are extracting ONE specific structured field from a patient's spoken "
        "answer during an intake conversation for a cancer financial-assistance "
        "matching tool. You must NEVER decide or comment on financial eligibility, "
        "only extract the literal field requested. Respond with ONLY a JSON object, "
        "no other text, in the exact shape: "
        '{"value": <extracted value, or null if not confidently determinable>, '
        '"confidence": "high" | "medium" | "low"}'
    )

    if field_name == "household_size":
        instructions = (
            "Extract the total number of people in the patient's household, "
            "including the patient themselves, as an integer. "
            'Example: "I\'ve got about three people at home, my wife and our '
            'daughter" -> {"value": 3, "confidence": "high"}. '
            "If no clear number of people can be determined, return null."
        )
    elif field_name == "annual_household_income":
        instructions = (
            "Extract the patient's approximate annual household income as a plain "
            "number (no currency symbols or commas), in US dollars. "
            'Example: "we make about 45 thousand a year" -> '
            '{"value": 45000, "confidence": "high"}. '
            "If given as monthly or weekly, convert to an annual estimate and note "
            "lower confidence. If no usable figure is given, return null."
        )
    elif field_name == "insurance_status":
        instructions = (
            "Classify the patient's insurance situation into exactly one of: "
            '"uninsured", "underinsured", or "insured". '
            "Return null if the answer does not clearly map to one of these three."
        )
    elif field_name == "preferred_contact_channel":
        instructions = (
            "Classify the patient's preferred contact method into exactly one of: "
            '"phone_call", "sms", "email", or "portal_message". '
            "Return null if the answer does not clearly map to one of these four."
        )
    elif field_name in ("diagnosis_code", "state"):
        instructions = (
            f"Extract the patient's answer as a clean, normalized short text value "
            f"for the field '{field_name}'. Correct obvious transcription errors in "
            f"place names or medical terms if confident, but do not invent details "
            f"not present in the answer. Return null only if the answer contains no "
            f"usable information at all."
        )
    else:
        instructions = f"Extract the value of the field '{field_name}' from the answer."

    return (
        f"{common_instructions}\n\n{instructions}\n\n"
        f'Patient\'s answer: "{raw_answer}"'
    )


def _validate_categorical(value, allowed_values):
    if isinstance(value, str) and value.strip().lower() in allowed_values:
        return value.strip().lower()
    return None


class LLMFieldExtractor:
    """Real LLM-backed replacement for the earlier stub_extract_field() /
    stub_extract_contact_channel() functions. Takes an injected llm_call_fn so this
    class has no hard dependency on any specific model provider and can be fully
    tested with a fake, deterministic function standing in for the model."""

    def __init__(self, llm_call_fn: Callable[[str], str]):
        """
        llm_call_fn: a callable taking a single prompt string and returning the raw
            model response text. In production this wraps a real model call (for
            example, an Anthropic or OpenAI chat completion with a low temperature
            for consistency); in tests it is a fake function returning canned JSON.
        """
        self._llm_call_fn = llm_call_fn

    def extract_field(self, field_name: str, raw_answer: str) -> ExtractionResult:
        raw_answer = (raw_answer or "").strip()
        if not raw_answer:
            return ExtractionResult(field_name=field_name, value=None, confidence="low")

        prompt = _build_prompt(field_name, raw_answer)
        raw_output = self._llm_call_fn(prompt)

        try:
            parsed = json.loads(raw_output)
            value = parsed.get("value")
            confidence = parsed.get("confidence", "low")
            if confidence not in ("high", "medium", "low"):
                confidence = "low"
        except (json.JSONDecodeError, AttributeError, TypeError):
            # Model returned something we cannot parse -- never guess, treat as no
            # extraction at all rather than trying to salvage partial text.
            return ExtractionResult(
                field_name=field_name, value=None, confidence="low",
                raw_model_output=raw_output,
            )

        # Extra validation layer for categorical fields: even if the model claims
        # high confidence, an out-of-vocabulary value is treated as no extraction.
        if field_name == "insurance_status":
            value = _validate_categorical(value, INSURANCE_STATUS_VALUES)
            if value is None:
                confidence = "low"
        elif field_name == "preferred_contact_channel":
            value = _validate_categorical(value, CONTACT_CHANNEL_VALUES)
            if value is None:
                confidence = "low"
        elif field_name == "household_size":
            if not isinstance(value, int) or value <= 0:
                value = None
                confidence = "low"
        elif field_name == "annual_household_income":
            if not isinstance(value, (int, float)) or value < 0:
                value = None
                confidence = "low"

        return ExtractionResult(
            field_name=field_name, value=value, confidence=confidence,
            raw_model_output=raw_output,
        )

    def extract_contact_channel(self, raw_answer: str) -> ExtractionResult:
        """Thin convenience wrapper so call sites reading like the old
        stub_extract_contact_channel() function still read naturally."""
        return self.extract_field("preferred_contact_channel", raw_answer)


# --- Real model-backed llm_call_fn adapter -------------------------------------------
#
# This is where a real provider call gets wired in. Kept separate from the class above
# so LLMFieldExtractor itself never imports any specific provider's SDK.
#
# Example wiring (uncomment and adapt once a real client is available in the actual
# runtime this executes in):
#
#   import anthropic
#   client = anthropic.Anthropic()
#
#   def anthropic_llm_call_fn(prompt: str) -> str:
#       response = client.messages.create(
#           model="claude-3-5-haiku-latest",   # small/fast model is enough for this
#           max_tokens=200,
#           temperature=0,                      # deterministic extraction, not creative
#           messages=[{"role": "user", "content": prompt}],
#       )
#       return response.content[0].text
#
#   extractor = LLMFieldExtractor(llm_call_fn=anthropic_llm_call_fn)
