# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: tool-platform-component-design-v1.md (v1), enterprise-voice-agent-prd-v1.md (v1)
# Ticket: none
"""Shared, provider-neutral planner used by text and WebSocket voice turns."""

from __future__ import annotations

import json
import os
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .platform.tool_gateway import ToolGatewayError, ToolRegistry

Intent = Literal["card-dispute", "card-summary", "payment-dispute", "failed-payments", "last-payment", "next-emi", "foreclosure", "prepayment", "service-request", "general"]


class TurnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    tool_names: list[str] = Field(max_length=8)


class Orchestrator:
    """Select an allowlisted typed-tool plan; use a configured chat-completions provider when available."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")

    async def plan(self, message: str, workflow_id: str) -> TurnPlan:
        tools = self.registry.list_tools(workflow_id)
        available = {item["name"] for item in tools}
        if not self.base_url or not self.model:
            return self._deterministic_plan(message, workflow_id)
        safe_message = self._mask_user_text(message)
        prompt = {
            "role": "system",
            "content": "Classify the customer request. Return JSON only: {intent, tool_names}. Select only tools from the supplied allowlist. Never request customer identity. Supported intents: card-dispute, card-summary, payment-dispute, failed-payments, last-payment, next-emi, foreclosure, prepayment, service-request, general. Use service-request when the customer asks to raise, create, open, submit, or make a servicing request or support ticket. A money calculation always uses the prepayment tool plan; never calculate numbers.",
        }
        request_body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [prompt, {"role": "user", "content": json.dumps({"message": safe_message, "workflow": workflow_id, "tools": tools}, separators=(",", ":"))}],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=request_body, headers=headers)
                response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            plan = TurnPlan.model_validate_json(raw)
            if not set(plan.tool_names).issubset(available):
                raise ToolGatewayError("ToolNotAllowed", "The planner selected a tool outside the workflow")
            required = self._deterministic_plan(message, workflow_id)
            if plan.intent != required.intent or not set(required.tool_names).issubset(plan.tool_names):
                raise ToolGatewayError("InvalidPlan", "The provider plan omitted a required tool")
            return plan
        except (httpx.HTTPError, KeyError, ValueError, ToolGatewayError):
            return self._deterministic_plan(message, workflow_id)

    async def compose(self, message: str, verified_draft: str, evidence: list[dict[str, object]]) -> str | None:
        """Optionally make wording conversational without exposing session identity or inventing facts."""
        if not self.base_url or not self.model:
            return None
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Rewrite the supplied answer to sound concise and natural. This is wording-only: do not add, remove, or change numbers, dates, product facts, policy claims, or clause IDs. If any detail is unclear, keep the original sentence. Return answer text only."},
                {"role": "user", "content": json.dumps({"question": self._mask_user_text(message), "verified_answer": verified_draft, "evidence": evidence}, separators=(",", ":"))},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
            return text.strip()[:4000] if isinstance(text, str) and text.strip() else None
        except (httpx.HTTPError, KeyError, ValueError):
            return None

    @staticmethod
    def _mask_user_text(value: str) -> str:
        value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[EMAIL]", value, flags=re.IGNORECASE)
        value = re.sub(r"(?<!\d)(?:\+?\d[\d ()-]{8,}\d)(?!\d)", "[PHONE]", value)
        return value[:2000]

    @staticmethod
    def _deterministic_plan(message: str, workflow_id: str) -> TurnPlan:
        text = message.lower()
        if workflow_id == "credit-card":
            if any(word in text for word in ("dispute", "unauthorized", "unknown transaction")):
                intent, tools = "card-dispute", ["card.statement", "policy.lookup"]
            elif Orchestrator._asks_for_service_request(text):
                intent, tools = "service-request", ["service-request.create"]
            else:
                intent, tools = "card-summary", ["card.summary", "card.statement"]
        elif any(word in text for word in ("failed", "failure")) and "payment" in text:
            intent, tools = "failed-payments", ["payments.history", "policy.lookup"]
        elif "dispute" in text and any(word in text for word in ("payment", "pm-", "failed")):
            intent, tools = "payment-dispute", ["payments.history", "policy.lookup"]
        elif "last payment" in text:
            intent, tools = "last-payment", ["payments.history"]
        elif "dispute" in text and any(word in text for word in ("first", "second", "third", "one", "that")):
            intent, tools = "payment-dispute", ["payments.history", "policy.lookup"]
        elif any(phrase in text for phrase in ("next emi", "upcoming emi", "emi due")):
            intent, tools = "next-emi", ["loan.summary"]
        elif any(word in text for word in ("foreclos", "penalty", "charges")):
            intent, tools = "foreclosure", ["loan.detail", "policy.lookup"]
        elif any(word in text for word in ("emi", "prepay", "pre-payment", "interest saved", "tenure")):
            intent, tools = "prepayment", ["loan.detail", "loan.rate-history", "policy.lookup", "payments.history"]
        elif Orchestrator._asks_for_service_request(text):
            intent, tools = "service-request", ["service-request.create"]
        elif "payment" in text:
            intent, tools = "next-emi", ["loan.summary"]
        else:
            intent, tools = "general", ["loan.summary"] if workflow_id == "loan-servicing" else ["card.summary"]
        return TurnPlan(intent=intent, tool_names=tools)

    @staticmethod
    def _asks_for_service_request(text: str) -> bool:
        return any(phrase in text for phrase in (
            "raise a request", "raise request", "open a request", "open request",
            "create a request", "create request", "submit a request", "submit request",
            "make a request", "make request", "service request", "service ticket",
            "support ticket", "raise a ticket", "open a ticket", "create a ticket",
            "contact support", "need support", "need help", "speak to an agent",
            "talk to a person",
        )) or bool(re.search(r"\b(?:raise|open|create|submit)\b.{0,40}\b(?:request|ticket)\b", text))


orchestrator = Orchestrator(ToolRegistry())
