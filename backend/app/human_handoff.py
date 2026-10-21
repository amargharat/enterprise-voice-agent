# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-prd-v1.md (v1)
# Ticket: none
"""Human escalation boundary; confirmed requests are tracked by Service Operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HandoffOffer:
    action_type: str
    summary: str
    queue: str = "LOAN_SERVICING_SPECIALIST"


class HumanHandoff:
    """Creates a confirmation-ready handoff description without performing a write."""

    def prepare(self, reason: str, workflow_id: str) -> HandoffOffer:
        queue = "CARD_SERVICING_SPECIALIST" if workflow_id == "credit-card" else "LOAN_SERVICING_SPECIALIST"
        return HandoffOffer(action_type="TICKET", summary=f"Ask a {queue.replace('_', ' ').lower()} to review: {reason}", queue=queue)


human_handoff = HumanHandoff()
