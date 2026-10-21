# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-prd-v1.md (v1)
# Ticket: none
"""Fail-closed verifier for optional model wording over deterministic evidence."""

from __future__ import annotations

import re
from collections import Counter

MONEY_PATTERN = re.compile(r"₹\s*([\d,]+\.\d{2})")
CLAUSE_PATTERN = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\.\d+(?:\.\d+)?\b")
REFERENCE_PATTERN = re.compile(r"\b(?:CU|LN|PM|CC|TX|SR)-[A-Z0-9]+\b")
NUMBER_PATTERN = re.compile(r"(?<![A-Z])\d+(?:\.\d+)?%?(?![A-Z])")


def numeric_facts(value: str) -> Counter[str]:
    value = MONEY_PATTERN.sub("[MONEY]", value)
    value = CLAUSE_PATTERN.sub("[CLAUSE]", value)
    value = REFERENCE_PATTERN.sub("[REFERENCE]", value)
    return Counter(NUMBER_PATTERN.findall(value))


def verify_rewrite(draft: str, candidate: str) -> tuple[bool, list[str]]:
    """Require model wording to preserve all grounded money values and rule citations verbatim."""
    reasons: list[str] = []
    draft_amounts = set(MONEY_PATTERN.findall(draft))
    candidate_amounts = set(MONEY_PATTERN.findall(candidate))
    if not candidate.strip():
        reasons.append("empty_response")
    if not candidate_amounts.issubset(draft_amounts):
        reasons.append("unsupported_money_value")
    if numeric_facts(candidate) != numeric_facts(draft):
        reasons.append("numeric_fact_changed")
    draft_clauses = set(CLAUSE_PATTERN.findall(draft))
    candidate_clauses = set(CLAUSE_PATTERN.findall(candidate))
    if not candidate_clauses.issubset(draft_clauses) or not draft_clauses.issubset(candidate_clauses):
        reasons.append("policy_citation_changed_or_omitted")
    return not reasons, reasons
