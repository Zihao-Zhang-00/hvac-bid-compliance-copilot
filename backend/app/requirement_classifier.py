"""Conservative post-extraction classification of HVAC tender clauses.

Rules are intentionally narrow. Unmatched clauses retain the LLM category;
conflicting signals become unknown and require human review.
"""

import re

from app.requirement_schema import RequirementCategory, RequirementExtractionResult


_ROLE = re.compile(
    r"\b(?:project manager|engineer|technician|installer|site supervisor|"
    r"project lead|staff|personnel|team members?)s?\b"
)
_PERSONNEL_EVIDENCE = re.compile(
    r"\b(?:licen[cs]e|certificat(?:e|ion)|credentials?|qualifications?|"
    r"resumes?|curriculum vitae|training|professional experience)\b"
)
_ORGANIZATION = re.compile(
    r"\b(?:bidders?|contractors?|companies|company|firms?|suppliers?|tenderers?)\b"
)
_COMPANY_CREDENTIAL = re.compile(
    r"\b(?:licen[cs]e|registration|accreditation)\b"
)
_PROJECT_REFERENCES = re.compile(
    r"\b(?:references?|track record|prior experience|past experience)\b"
    r".{0,100}\b(?:projects?|contracts?|installations?)\b"
)
_SCORING = re.compile(
    r"\b(?:evaluation|scoring)\s+(?:points?|marks?)\b|"
    r"\b(?:points?|marks?)\s+(?:will|shall|may|are)\s+be\s+awarded\b|"
    r"\bweighted\s+scores?\b"
)
_TECHNICAL = re.compile(
    r"\b(?:cop|coefficient of performance|refrigerant|cooling capacity|"
    r"energy efficiency ratio)\b|\br-\d{2,3}\b"
)
_DOCUMENTATION = re.compile(
    r"\b(?:signed|completed)\b.{0,60}\b(?:form|declaration)\b|"
    r"\b(?:attach|include|submit|provide)\b.{0,100}"
    r"\b(?:form|schedule|declaration)\b"
)
_GENERAL_MATERIAL = re.compile(
    r"\b(?:additional|supplementary|further|other)\b.{0,80}"
    r"\b(?:information|documents?|documentation|materials?)\b"
)
_DISCRETION = re.compile(
    r"\b(?:when|if)\s+(?:considered|deemed)\s+"
    r"(?:appropriate|necessary)\b|"
    r"\b(?:at|subject to)\s+(?:the\s+)?"
    r"(?:evaluation\s+)?committee(?:'s|’s)?\s+discretion\b|"
    r"\bif\s+(?:requested|required)\s+by\s+(?:the\s+)?"
    r"(?:evaluation\s+)?committee\b"
)


def classify_requirements(
    result: RequirementExtractionResult,
) -> RequirementExtractionResult:
    """Correct clear category signals; never change obligation or provenance.

    Scoring takes precedence when a scored criterion references a technical
    property. Other overlapping rules are left for human review.
    """

    classified = []

    for requirement in result.requirements:
        clause = " ".join(requirement.requirement_text.casefold().split())
        candidates: set[RequirementCategory] = set()

        if _GENERAL_MATERIAL.search(clause) and _DISCRETION.search(clause):
            category = RequirementCategory.UNKNOWN
        else:
            if _SCORING.search(clause):
                candidates.add(RequirementCategory.SCORING)
            else:
                if _TECHNICAL.search(clause):
                    candidates.add(RequirementCategory.TECHNICAL)

            if _ROLE.search(clause) and _PERSONNEL_EVIDENCE.search(clause):
                candidates.add(RequirementCategory.PERSONNEL)

            if _ORGANIZATION.search(clause) and (
                _COMPANY_CREDENTIAL.search(clause)
                or _PROJECT_REFERENCES.search(clause)
            ):
                candidates.add(RequirementCategory.QUALIFICATION)

            if _DOCUMENTATION.search(clause):
                candidates.add(RequirementCategory.DOCUMENTATION)

            if len(candidates) > 1:
                category = RequirementCategory.UNKNOWN
            elif len(candidates) == 1 and requirement.category != RequirementCategory.UNKNOWN:
                category = next(iter(candidates))
            else:
                category = requirement.category

        classified.append(
            requirement.model_copy(
                update={
                    "category": category,
                    "needs_review": (
                        requirement.needs_review
                        or category == RequirementCategory.UNKNOWN
                    ),
                }
            )
        )

    return RequirementExtractionResult(requirements=classified)
