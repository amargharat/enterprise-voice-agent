# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-data-design-v1.md (v1)
# Ticket: none
"""Deterministic finance calculations for the synthetic servicing demo."""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def emi_amount(principal: Decimal, annual_rate_percent: Decimal, months: int) -> Decimal:
    """Return a monthly EMI rounded to paise using the standard reducing-balance formula."""
    if months <= 0 or principal < 0:
        raise ValueError("principal must be non-negative and months must be positive")
    principal = Decimal(principal)
    monthly_rate = Decimal(annual_rate_percent) / Decimal("1200")
    if monthly_rate == 0:
        return money(principal / months)
    factor = (Decimal(1) + monthly_rate) ** months
    return money(principal * monthly_rate * factor / (factor - 1))


def amortization(principal: Decimal, annual_rate_percent: Decimal, payment: Decimal) -> tuple[int, Decimal]:
    """Simulate monthly reducing-balance payments; return months and total interest."""
    balance = money(principal)
    payment = money(payment)
    monthly_rate = Decimal(annual_rate_percent) / Decimal("1200")
    if balance <= 0:
        return 0, Decimal("0.00")
    if payment <= 0 or (monthly_rate > 0 and payment <= money(balance * monthly_rate)):
        raise ValueError("payment does not amortize the principal")

    total_interest = Decimal("0.00")
    months = 0
    while balance > 0 and months < 1200:
        interest = money(balance * monthly_rate)
        installment = min(payment, balance + interest)
        principal_paid = installment - interest
        if principal_paid <= 0:
            raise ValueError("payment does not reduce principal")
        balance = money(max(Decimal("0.00"), balance - principal_paid))
        total_interest += interest
        months += 1
    if balance > 0:
        raise ValueError("loan term exceeds supported calculator horizon")
    return months, money(total_interest)


def prepayment_savings(
    principal: Decimal, annual_rate_percent: Decimal, payment: Decimal, prepayment: Decimal
) -> dict[str, Decimal | int]:
    """Estimate interest saved when a one-off prepayment reduces principal, keeping EMI fixed."""
    principal = money(principal)
    prepayment = money(prepayment)
    if prepayment <= 0 or prepayment >= principal:
        raise ValueError("prepayment must be positive and less than outstanding principal")
    months_before, interest_before = amortization(principal, annual_rate_percent, payment)
    months_after, interest_after = amortization(principal - prepayment, annual_rate_percent, payment)
    return {
        "interest_before": interest_before,
        "interest_after": interest_after,
        "interest_saved": money(interest_before - interest_after),
        "months_before": months_before,
        "months_after": months_after,
        "months_saved": months_before - months_after,
    }
