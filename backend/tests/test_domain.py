# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-data-design-v1.md (v1)
# Ticket: none
from decimal import Decimal

import pytest

from app.domain import amortization, emi_amount, money, prepayment_savings


def test_emi_zero_interest_uses_simple_division():
    assert emi_amount(Decimal("120000"), Decimal("0"), 12) == Decimal("10000.00")


def test_prepaid_principal_saves_interest_and_shortens_term():
    result = prepayment_savings(Decimal("382450.75"), Decimal("10.75"), Decimal("11250"), Decimal("50000"))
    assert result["interest_saved"] == result["interest_before"] - result["interest_after"]
    assert result["interest_saved"] > 0
    assert result["months_saved"] > 0
    assert result["months_after"] < result["months_before"]


def test_amortization_rejects_payment_that_never_reduces_balance():
    with pytest.raises(ValueError, match="does not amortize"):
        amortization(Decimal("100000"), Decimal("12"), Decimal("500"))


def test_prepayment_must_be_less_than_principal():
    with pytest.raises(ValueError, match="less than"):
        prepayment_savings(Decimal("10000"), Decimal("10"), Decimal("1000"), Decimal("10000"))
