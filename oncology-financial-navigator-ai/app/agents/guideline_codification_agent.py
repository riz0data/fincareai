"""
Guideline Codification Agent (Agent 5)

Per agent_architecture.md, Agent 5: reads the raw guideline text fetched by the Daily
Automated Change Ticker (foundation_reference_store.py) when it detects a change, and
drafts a proposed structured rule update in the same shape the rules engine already
uses (see eligibility_rules.FoundationRule).

This agent NEVER applies its own draft. It only ever produces a CodificationDraft for
a human to review, edit, and explicitly approve via the existing human-reviewed update
path (foundation_reference_store.apply_human_reviewed_update). This mirrors every other
agent in this system: agents draft and recommend, a human signs off before anything
becomes live.

Why no vector database here: this agent is handed exactly one already-identified
document at a time (the specific page the ticker just fetched for one specific
foundation). There is no search-across-many-documents step, so nothing to retrieve --
this is a structured extraction task over a single known input, not a retrieval task.

Extraction approach: like the Risk and Escalation Agent, this uses explicit, inspectable
keyword/pattern-based extraction rather than an opaque LLM call, so a human reviewer can
see exactly why the agent proposed what it proposed. A real deployment could swap in an
LLM-based extractor for messier source text, but it should still produce this same
draft shape, still flag low-confidence fields, and still never bypass human review.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict


@dataclass
class FieldExtraction:
    """One extracted candidate field, with the evidence and confidence behind it,
    so a human reviewer can quickly judge whether to trust it."""
    field_name: str
    proposed_value: object
    confidence: str  # "high", "medium", "low"
    evidence_snippet: Optional[str] = None
    note: Optional[str] = None


@dataclass
class CodificationDraft:
    """The full proposed update for one foundation, awaiting human review.
    Shape mirrors eligibility_rules.FoundationRule's fields so a human reviewer
    (or apply_human_reviewed_update) can adopt it with minimal translation."""
    foundation_id: str
    foundation_name: str
    generated_at: datetime
    proposed_rules_version: str

    proposed_max_income_multiplier_of_poverty_line: Optional[float]
    proposed_eligible_diagnoses: List[str]
    proposed_eligible_insurance_statuses: List[str]
    proposed_required_application_fields: List[str]

    field_extractions: List[FieldExtraction] = field(default_factory=list)
    change_summary: str = ""
    overall_confidence: str = "low"
    requires_careful_human_review: bool = True


INSURANCE_KEYWORDS = {
    "uninsured": ["uninsured", "no insurance", "without insurance"],
    "underinsured": ["underinsured", "under-insured", "high deductible"],
    "medicare": ["medicare"],
    "medicaid": ["medicaid"],
    "private": ["private insurance", "commercial insurance", "private plan"],
}


def _extract_income_multiplier(text: str) -> FieldExtraction:
    """Looks for patterns like '500% of the federal poverty line' or
    '500 percent of poverty level' and converts to a multiplier (5.0)."""
    pattern = re.search(
        r"(\d{2,4})\s*(?:%|percent)\s*of\s*(?:the\s+)?(?:federal\s+)?poverty\s*(?:line|level)",
        text, re.IGNORECASE,
    )
    if pattern:
        percent = float(pattern.group(1))
        return FieldExtraction(
            field_name="max_income_multiplier_of_poverty_line",
            proposed_value=percent / 100.0,
            confidence="high",
            evidence_snippet=pattern.group(0),
        )
    return FieldExtraction(
        field_name="max_income_multiplier_of_poverty_line",
        proposed_value=None,
        confidence="low",
        note="No explicit poverty-line percentage found in source text. Human must "
             "locate the income threshold manually.",
    )


def _extract_insurance_statuses(text: str) -> FieldExtraction:
    lower_text = text.lower()
    found = []
    snippets = []
    for status, keywords in INSURANCE_KEYWORDS.items():
        for kw in keywords:
            if kw in lower_text:
                found.append(status)
                snippets.append(kw)
                break
    confidence = "high" if found else "low"
    return FieldExtraction(
        field_name="eligible_insurance_statuses",
        proposed_value=sorted(set(found)),
        confidence=confidence,
        evidence_snippet=", ".join(snippets) if snippets else None,
        note=None if found else "No recognized insurance-status keywords found; human "
                                 "should confirm insurance eligibility manually.",
    )


def _extract_diagnoses(text: str, known_diagnosis_keywords: Optional[List[str]] = None) -> FieldExtraction:
    """Diagnosis extraction is intentionally conservative: it only flags matches against
    a supplied known-diagnosis keyword list (e.g. current diagnosis taxonomy), rather than
    trying to freely parse arbitrary disease names, which is exactly the kind of open-ended
    judgment call this system reserves for a human rather than pattern matching."""
    if not known_diagnosis_keywords:
        return FieldExtraction(
            field_name="eligible_diagnoses",
            proposed_value=[],
            confidence="low",
            note="No known-diagnosis keyword list supplied; human must read the source "
                 "text directly to determine diagnosis coverage.",
        )
    lower_text = text.lower()
    found = [d for d in known_diagnosis_keywords if d.lower() in lower_text]
    return FieldExtraction(
        field_name="eligible_diagnoses",
        proposed_value=found,
        confidence="medium" if found else "low",
        evidence_snippet=", ".join(found) if found else None,
    )


def _extract_required_fields(text: str) -> FieldExtraction:
    """Looks for a handful of common application-field phrases. Deliberately narrow
    and conservative -- this is the field most likely to need human correction, since
    application form requirements are rarely stated in fully consistent language."""
    candidates = {
        "patient_full_name": ["patient name", "full name"],
        "diagnosis_code": ["diagnosis code", "icd-10", "icd 10"],
        "household_income": ["household income", "annual income"],
        "household_size": ["household size", "family size"],
        "insurance_status": ["insurance status", "insurance type"],
        "physician_verification": ["physician verification", "treating physician must verify",
                                    "verified by the treating physician"],
    }
    lower_text = text.lower()
    found = [field_name for field_name, phrases in candidates.items()
             if any(p in lower_text for p in phrases)]
    return FieldExtraction(
        field_name="required_application_fields",
        proposed_value=found,
        confidence="medium" if found else "low",
        note=None if found else "No recognized application-field phrases found.",
    )


class GuidelineCodificationAgent:
    """Agent 5. Call codify() once per foundation, only after the daily ticker has
    reported "change_detected" for that foundation. Produces a CodificationDraft for
    a human to review -- never applies anything itself."""

    def codify(
        self,
        foundation_id: str,
        foundation_name: str,
        fetched_guideline_text: str,
        previous_rules_version: str,
        known_diagnosis_keywords: Optional[List[str]] = None,
        previous_guideline_text: Optional[str] = None,
    ) -> CodificationDraft:
        income_extraction = _extract_income_multiplier(fetched_guideline_text)
        insurance_extraction = _extract_insurance_statuses(fetched_guideline_text)
        diagnosis_extraction = _extract_diagnoses(fetched_guideline_text, known_diagnosis_keywords)
        fields_extraction = _extract_required_fields(fetched_guideline_text)

        extractions = [income_extraction, insurance_extraction, diagnosis_extraction, fields_extraction]

        confidences = [e.confidence for e in extractions]
        if "low" in confidences:
            overall_confidence = "low"
        elif all(c == "high" for c in confidences):
            overall_confidence = "high"
        else:
            overall_confidence = "medium"

        try:
            version_num = int(previous_rules_version.lstrip("v")) + 1
            proposed_version = f"v{version_num}"
        except ValueError:
            proposed_version = f"{previous_rules_version}-draft"

        change_summary = self._build_change_summary(
            previous_guideline_text, fetched_guideline_text, extractions
        )

        return CodificationDraft(
            foundation_id=foundation_id,
            foundation_name=foundation_name,
            generated_at=datetime.utcnow(),
            proposed_rules_version=proposed_version,
            proposed_max_income_multiplier_of_poverty_line=income_extraction.proposed_value,
            proposed_eligible_diagnoses=diagnosis_extraction.proposed_value,
            proposed_eligible_insurance_statuses=insurance_extraction.proposed_value,
            proposed_required_application_fields=fields_extraction.proposed_value,
            field_extractions=extractions,
            change_summary=change_summary,
            overall_confidence=overall_confidence,
            requires_careful_human_review=(overall_confidence != "high"),
        )

    def _build_change_summary(
        self,
        previous_text: Optional[str],
        new_text: Optional[str],
        extractions: List[FieldExtraction],
    ) -> str:
        low_conf_fields = [e.field_name for e in extractions if e.confidence == "low"]
        parts = []
        if previous_text is None:
            parts.append("No previous version on file to diff against; this is a first-time "
                         "codification, review in full.")
        else:
            parts.append("Source content changed since the last check.")
        if low_conf_fields:
            parts.append(
                "Low-confidence fields requiring direct human reading of the source page: "
                + ", ".join(low_conf_fields) + "."
            )
        else:
            parts.append("All fields extracted with medium or high confidence, but still "
                          "require sign-off before going live.")
        return " ".join(parts)
