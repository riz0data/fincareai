"""
Tests for LLM-based field extraction (app/agents/llm_field_extraction.py).

Uses an injected fake llm_call_fn throughout, exactly as the module was designed to be
tested -- no real model call is ever made by this suite. Focus areas: correct parsing
of well-formed model output, and -- most importantly for a safety-relevant system --
that malformed output, out-of-vocabulary categorical values, and blank input are all
treated as "no extraction" (None) rather than guessed.
"""

import json
import pytest

from llm_field_extraction import LLMFieldExtractor, ExtractionResult


def _json_llm(value, confidence="high"):
    """Builds a fake llm_call_fn that always returns the same canned JSON response,
    regardless of prompt -- fine for tests that only need one field extracted."""
    def _fn(prompt):
        return json.dumps({"value": value, "confidence": confidence})
    return _fn


def test_household_size_extraction_happy_path():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm(3, "high"))
    result = extractor.extract_field("household_size", "three of us at home")
    assert result.value == 3
    assert result.confidence == "high"


def test_income_extraction_happy_path():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm(45000, "high"))
    result = extractor.extract_field("annual_household_income", "about 45 thousand a year")
    assert result.value == 45000


def test_insurance_status_valid_value_accepted():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm("uninsured", "high"))
    result = extractor.extract_field("insurance_status", "I don't have insurance")
    assert result.value == "uninsured"
    assert result.confidence == "high"


def test_insurance_status_out_of_vocabulary_value_rejected_even_if_high_confidence():
    # The model claims high confidence but returns a value outside the allowed set --
    # this must be treated as no extraction, never passed through as-is.
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm("partially insured maybe", "high"))
    result = extractor.extract_field("insurance_status", "it's complicated")
    assert result.value is None
    assert result.confidence == "low"


def test_contact_channel_valid_value_accepted():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm("sms", "high"))
    result = extractor.extract_contact_channel("text me")
    assert result.value == "sms"


def test_contact_channel_out_of_vocabulary_rejected():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm("carrier pigeon", "high"))
    result = extractor.extract_contact_channel("send a pigeon")
    assert result.value is None
    assert result.confidence == "low"


def test_household_size_non_positive_or_wrong_type_rejected():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm(-1, "high"))
    result = extractor.extract_field("household_size", "negative one people, somehow")
    assert result.value is None
    assert result.confidence == "low"

    extractor2 = LLMFieldExtractor(llm_call_fn=_json_llm("three", "high"))  # wrong type (str not int)
    result2 = extractor2.extract_field("household_size", "three")
    assert result2.value is None
    assert result2.confidence == "low"


def test_income_negative_rejected():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm(-500, "high"))
    result = extractor.extract_field("annual_household_income", "negative income, somehow")
    assert result.value is None
    assert result.confidence == "low"


def test_malformed_model_output_treated_as_no_extraction():
    def broken_llm(prompt):
        return "I think the answer is 3 people"  # not valid JSON
    extractor = LLMFieldExtractor(llm_call_fn=broken_llm)
    result = extractor.extract_field("household_size", "three of us")
    assert result.value is None
    assert result.confidence == "low"
    assert result.raw_model_output == "I think the answer is 3 people"


def test_blank_answer_never_calls_the_model():
    called = {"count": 0}
    def counting_llm(prompt):
        called["count"] += 1
        return json.dumps({"value": "x", "confidence": "high"})
    extractor = LLMFieldExtractor(llm_call_fn=counting_llm)
    result = extractor.extract_field("state", "   ")
    assert result.value is None
    assert called["count"] == 0


def test_invalid_confidence_value_defaults_to_low():
    def weird_confidence_llm(prompt):
        return json.dumps({"value": "Ohio", "confidence": "extremely sure"})
    extractor = LLMFieldExtractor(llm_call_fn=weird_confidence_llm)
    result = extractor.extract_field("state", "ohio")
    assert result.confidence == "low"


def test_free_text_field_passes_through_model_value():
    extractor = LLMFieldExtractor(llm_call_fn=_json_llm("Breast Cancer", "high"))
    result = extractor.extract_field("diagnosis_code", "breast cancer, stage two")
    assert result.value == "Breast Cancer"
