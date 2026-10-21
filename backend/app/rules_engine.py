# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-data-design-v1.md (v1), ADR-001-typed-tools-rules-calculator-over-rag.md (v1)
# Ticket: none
"""Small fail-closed evaluator for versioned declarative policy rules."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PolicyDecision(BaseModel):
    applies: bool
    rule_id: str
    clause_id: str
    clause_text: str
    outcome: dict[str, Any]
    reason: str


class RulesEngine:
    def evaluate(self, rule: dict[str, Any], facts: dict[str, Any]) -> PolicyDecision:
        condition = rule.get("condition", {"all": []})
        applies = self._matches(condition, facts)
        return PolicyDecision(
            applies=applies,
            rule_id=str(rule.get("ruleId", "")),
            clause_id=str(rule.get("clauseId", "")),
            clause_text=str(rule.get("clauseText", "")),
            outcome=rule.get("outcome", {}) if applies else {},
            reason="condition_matched" if applies else "no_applicable_rule",
        )

    def _matches(self, condition: Any, facts: dict[str, Any]) -> bool:
        if not isinstance(condition, dict):
            return False
        all_terms = condition.get("all", [])
        any_terms = condition.get("any", [])
        if not isinstance(all_terms, list) or not isinstance(any_terms, list):
            return False
        return all(self._term(term, facts) for term in all_terms) and (not any_terms or any(self._term(term, facts) for term in any_terms))

    @staticmethod
    def _term(term: Any, facts: dict[str, Any]) -> bool:
        if not isinstance(term, dict) or term.get("field") not in facts:
            return False
        actual = facts[term["field"]]
        expected = term.get("value")
        operation = term.get("op", "eq")
        if operation == "eq":
            return actual == expected
        if operation == "neq":
            return actual != expected
        if operation == "in":
            return isinstance(expected, list) and actual in expected
        if operation == "gte":
            return actual >= expected
        if operation == "lte":
            return actual <= expected
        return False


rules_engine = RulesEngine()
