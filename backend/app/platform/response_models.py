# Generated from design: tool-platform-component-design-v1.md (v1)
# Supporting design: tool-platform-enterprise-systems-integration-design-v1.md (v1)
# Ticket: none
"""Canonical response shapes accepted at the enterprise-service trust boundary."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


class LoanOutput(StrictOutput):
    loanId: str
    status: str
    outstandingPrincipal: str | Decimal
    annualRatePercent: str | Decimal
    rateType: Literal["FIXED", "FLOATING"]
    emi: str | Decimal
    tenureRemainingMonths: int


class LoanListOutput(StrictOutput):
    customerId: str
    loans: list[LoanOutput]


class PaymentOutput(StrictOutput):
    paymentId: str
    dueDate: str
    amount: str | Decimal
    status: Literal["SUCCESS", "FAILED", "PENDING"]
    failureCode: str | None = None


class PaymentListOutput(StrictOutput):
    payments: list[PaymentOutput]


class PolicyRuleOutput(StrictOutput):
    ruleId: str
    clauseId: str
    clauseText: str


class PolicyListOutput(StrictOutput):
    productCode: str
    topic: str
    rules: list[PolicyRuleOutput]


class CardOutput(StrictOutput):
    cardId: str
    product: str
    lastFour: str
    outstanding: str | Decimal
    statementBalance: str | Decimal


class CardStatementOutput(StrictOutput):
    cardId: str
    statementBalance: str | Decimal
    dueDate: str
    minimumDue: str | Decimal
    transactions: list[dict[str, Any]]


class RateHistoryOutput(StrictOutput):
    loanId: str
    history: list[dict[str, Any]]
    previousRatePercent: str | Decimal


ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "loan.summary": TypeAdapter(LoanListOutput | LoanOutput),
    "loan.detail": TypeAdapter(LoanOutput),
    "loan.rate-history": TypeAdapter(RateHistoryOutput),
    "payments.history": TypeAdapter(PaymentListOutput | list[PaymentOutput] | PaymentOutput),
    "policy.lookup": TypeAdapter(PolicyListOutput | PolicyRuleOutput),
    "card.summary": TypeAdapter(CardOutput),
    "card.statement": TypeAdapter(CardStatementOutput),
}


def validate_tool_output(tool_name: str, payload: Any) -> Any:
    adapter = ADAPTERS.get(tool_name)
    if adapter is None:
        return payload
    validated = adapter.validate_python(payload)
    if isinstance(validated, list):
        return [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in validated]
    return validated.model_dump(mode="json") if isinstance(validated, BaseModel) else validated
