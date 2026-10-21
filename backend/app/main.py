# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-prd-v1.md (v1), tool-platform-component-design-v1.md (v1), enterprise-voice-agent-data-design-v1.md (v1)
# Ticket: none
"""Local POC API: verified synthetic accounts, reusable tool gateway, evidence and confirmed actions."""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import httpx
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response
from starlette.websockets import WebSocketDisconnected

from .domain import money, prepayment_savings
from .human_handoff import human_handoff
from .orchestrator import TurnPlan, orchestrator
from .rules_engine import rules_engine
from .verifier import verify_rewrite
from .platform.database import database
from .platform.session_store import state
from .platform.telemetry import ACTION_CALLS, TOOL_CALLS, TOOL_LATENCY, TURN_CALLS, TURN_LATENCY, TURN_STAGE_LATENCY, configure_tracing, prometheus_app
from .platform.tool_gateway import ToolCall, ToolGatewayError, TurnContext, gateway
from .platform.voice_providers import voice_provider

ROOT = Path(__file__).resolve().parents[1]
DEMO_OTP = "246810"

CUSTOMERS: dict[str, dict[str, Any]] = {
    "CU-2291": {
        "customerId": "CU-2291", "name": "Aarav Sharma", "mobile": "+91 •••••• 4721", "kycStatus": "VERIFIED",
        "loan": {
            "loanId": "LN-10045", "product": "Personal loan", "status": "Active", "currency": "INR",
            "sanctionedAmount": "500000.00", "outstandingPrincipal": "382450.75", "annualRatePercent": "10.75",
            "previousRatePercent": "10.25", "rateType": "FLOATING", "emi": "11250.00", "previousEmi": "10950.00",
            "nextDueDate": "2026-11-05", "tenureRemainingMonths": 38, "rateEffectiveDate": "2026-09-01",
        },
        "payments": [
            {"paymentId": "PM-88213", "dueDate": "2026-09-05", "attemptedAt": "2026-09-05T06:01:12+05:30", "amount": "11250.00", "status": "FAILED", "failureCode": "INSUFFICIENT_FUNDS", "failureReason": "Not enough balance in the linked account", "channel": "AUTO_DEBIT"},
            {"paymentId": "PM-87820", "dueDate": "2026-06-05", "attemptedAt": "2026-06-05T06:00:31+05:30", "amount": "10950.00", "status": "FAILED", "failureCode": "BANK_TIMEOUT", "failureReason": "The bank did not respond before the payment timed out", "channel": "AUTO_DEBIT"},
            {"paymentId": "PM-86109", "dueDate": "2026-03-05", "attemptedAt": "2026-03-05T06:00:43+05:30", "amount": "10950.00", "status": "FAILED", "failureCode": "MANDATE_INACTIVE", "failureReason": "The auto-debit mandate was inactive", "channel": "AUTO_DEBIT"},
            {"paymentId": "PM-88914", "dueDate": "2026-10-05", "attemptedAt": "2026-10-05T06:00:10+05:30", "amount": "11250.00", "status": "SUCCESS", "failureCode": None, "failureReason": None, "channel": "AUTO_DEBIT"},
        ],
        "lastPayment": {"paymentId": "PM-88914", "date": "2026-10-05", "amount": "11250.00", "status": "SUCCESS", "channel": "AUTO_DEBIT"},
        "card": {"cardId": "CC-7042", "product": "Horizon Rewards Credit Card", "lastFour": "7042", "outstanding": "18420.50", "availableLimit": "81579.50", "statementBalance": "22340.00", "dueDate": "2026-10-28", "minimumDue": "1120.00", "rewardPoints": 3240, "transactions": [{"transactionId": "TX-50081", "date": "2026-10-12", "merchant": "Green Basket Market", "amount": "1842.00", "status": "POSTED"}, {"transactionId": "TX-49823", "date": "2026-10-08", "merchant": "Metroline Travel", "amount": "4360.00", "status": "POSTED"}, {"transactionId": "TX-49277", "date": "2026-10-02", "merchant": "CloudNine Media", "amount": "499.00", "status": "POSTED"}]},
    },
    "CU-3140": {
        "customerId": "CU-3140", "name": "Mira Iyer", "mobile": "+91 •••••• 9816", "kycStatus": "VERIFIED",
        "loan": {
            "loanId": "LN-20418", "product": "Personal loan", "status": "Active", "currency": "INR",
            "sanctionedAmount": "350000.00", "outstandingPrincipal": "241180.00", "annualRatePercent": "11.20",
            "previousRatePercent": "11.20", "rateType": "FIXED", "emi": "10230.00", "previousEmi": "10230.00",
            "nextDueDate": "2026-11-10", "tenureRemainingMonths": 29, "rateEffectiveDate": "2025-04-01",
        },
        "payments": [
            {"paymentId": "PM-91301", "dueDate": "2026-08-10", "attemptedAt": "2026-08-10T05:58:02+05:30", "amount": "10230.00", "status": "FAILED", "failureCode": "INSUFFICIENT_FUNDS", "failureReason": "Not enough balance in the linked account", "channel": "AUTO_DEBIT"},
            {"paymentId": "PM-91752", "dueDate": "2026-10-10", "attemptedAt": "2026-10-10T05:59:11+05:30", "amount": "10230.00", "status": "SUCCESS", "failureCode": None, "failureReason": None, "channel": "AUTO_DEBIT"},
        ],
        "lastPayment": {"paymentId": "PM-91752", "date": "2026-10-10", "amount": "10230.00", "status": "SUCCESS", "channel": "AUTO_DEBIT"},
        "card": {"cardId": "CC-3308", "product": "Horizon Platinum Credit Card", "lastFour": "3308", "outstanding": "9360.00", "availableLimit": "40640.00", "statementBalance": "12840.00", "dueDate": "2026-11-02", "minimumDue": "650.00", "rewardPoints": 1810, "transactions": [{"transactionId": "TX-61003", "date": "2026-10-14", "merchant": "Northwind Books", "amount": "1290.00", "status": "POSTED"}, {"transactionId": "TX-60710", "date": "2026-10-09", "merchant": "Urban Outfitters", "amount": "3280.00", "status": "POSTED"}]},
    },
}

POLICIES = {
    "PREPAYMENT": {"ruleId": "PL-PP-004", "clauseId": "PL-TERMS-5.4", "clauseText": "Part-prepayments are applied to principal. For floating-rate personal loans, no part-prepayment fee applies.", "condition": {"all": [{"field": "rateType", "op": "eq", "value": "FLOATING"}]}, "outcome": {"feePercent": "0.00"}},
    "FORECLOSURE": {"ruleId": "PL-FC-001", "clauseId": "PL-TERMS-7.2", "clauseText": "No foreclosure charges apply to floating-rate personal loans.", "condition": {"all": [{"field": "rateType", "op": "eq", "value": "FLOATING"}]}, "outcome": {"penaltyPercent": "0.00"}},
    "PAYMENT_FAILURE": {"ruleId": "PAY-OPS-002", "clauseId": "PAYMENTS-HELP-2.1", "clauseText": "Failed debit attempts may be disputed for investigation; the payment remains unpaid until a successful retry is recorded.", "condition": {"all": []}, "outcome": {"disputeAllowed": True}},
    "CARD_DISPUTE": {"ruleId": "CC-DISPUTE-001", "clauseId": "CARD-TERMS-9.1", "clauseText": "Card transactions may be disputed for investigation. A submitted dispute does not guarantee reversal.", "condition": {"all": []}, "outcome": {"disputeAllowed": True}},
}

# The same validated registry defines workflow allowlists and the executing ToolGateway.
WORKFLOWS: dict[str, dict[str, Any]] = gateway.registry.workflows

PENDING_ACTIONS: dict[str, dict[str, Any]] = {}
FAILURES = {"payments": False}
gateway.failure_override = FAILURES
LATENCIES: list[dict[str, Any]] = []
AUDIT: list[dict[str, Any]] = []


async def audit(event_type: str, customer_id: str | None, details: dict[str, Any]) -> None:
    record = {"event": event_type, "customerId": customer_id, "at": datetime.now(timezone.utc).isoformat(), **details}
    AUDIT.append(record)
    await database.record_audit(event_type, customer_id, details)


def mask_log_text(value: str) -> str:
    value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[EMAIL]", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<!\d)(?:\+?\d[\d ()-]{8,}\d)(?!\d)", "[PHONE]", value)
    value = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[CARD_NUMBER]", value)
    return value[:2000]


def record_turn_stage_metrics(channel: str, *, total_ms: int, llm_ms: int, tools_ms: int) -> None:
    for stage, latency in (("model", llm_ms), ("tools", tools_ms), ("first_response", total_ms), ("total", total_ms)):
        TURN_STAGE_LATENCY.labels(channel=channel, stage=stage).observe(max(0, latency) / 1000)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.initialize()
    await state.connect()
    try:
        yield
    finally:
        await state.close()
        await database.close()


configure_tracing()
HTTPXClientInstrumentor().instrument()
app = FastAPI(title="Horizon Voice Agent POC", version="1.0.0", description="Synthetic-data servicing assistant API", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", prometheus_app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartSessionRequest(BaseModel):
    workflowId: str = "loan-servicing"


class VerifyRequest(BaseModel):
    sessionId: str
    customerId: str
    otp: str


class ChatRequest(BaseModel):
    sessionId: str
    message: str = Field(min_length=1, max_length=2000)
    workflowId: str = "loan-servicing"
    channel: Literal["TEXT", "VOICE"] = "TEXT"


class TurnResponse(BaseModel):
    turnId: str
    answer: str
    evidence: list[dict[str, Any]]
    action: dict[str, Any] | None
    suggestions: list[str]
    latencyMs: int
    channel: Literal["TEXT", "VOICE"]


class PrepareActionRequest(BaseModel):
    sessionId: str
    workflowId: str
    actionType: str
    subjectRef: str | None = None
    amount: str | None = None


class ConfirmActionRequest(BaseModel):
    sessionId: str
    token: str


class FailureRequest(BaseModel):
    system: str = "payments"
    enabled: bool


async def save_session(session_id: str, session: dict[str, Any]) -> None:
    await state.save_session(session_id, session)


async def session_for(session_id: str, verified: bool = True) -> dict[str, Any]:
    session = await state.get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired. Start a new demo session.")
    if verified and not session.get("customerId"):
        raise HTTPException(status_code=403, detail="Verify your demo identity before viewing account information.")
    return session


async def tool_call(name: str, system: str, operation: str, customer_id: str, correlation_id: str, payload: Any, session_id: str, workflow_id: str) -> tuple[Any, dict[str, Any]]:
    customer = CUSTOMERS[customer_id]
    loan_id = customer["loan"]["loanId"]
    card_id = customer["card"]["cardId"]
    if name == "customer.profile":
        arguments = {}
    elif name in {"loan.summary", "loan.detail"}:
        arguments = {} if name == "loan.summary" else {"loanId": loan_id}
    elif name == "loan.rate-history":
        arguments = {"loanId": loan_id}
    elif name == "payments.history":
        arguments = {"loanId": loan_id}
        if "status=FAILED" in operation:
            arguments["status"] = "FAILED"
        limit = re.search(r"limit=(\d+)", operation)
        if limit:
            arguments["limit"] = int(limit.group(1))
        if "from=" in operation:
            match = re.search(r"from=([^&]+)", operation)
            if match:
                arguments["from"] = match.group(1)
    elif name == "policy.lookup":
        topic = re.search(r"topic=([A-Z_]+)", operation)
        arguments = {"productCode": "CREDIT_CARD" if "CARD_" in operation else "PERSONAL_LOAN", "topic": topic.group(1) if topic else "FORECLOSURE"}
    elif name == "card.summary":
        arguments = {"cardId": card_id}
    elif name == "card.statement":
        arguments = {"cardId": card_id}
    else:
        arguments = {}
    call = ToolCall(tool_name=name, arguments=arguments)
    context = TurnContext(
        session_id=session_id, turn_id=correlation_id, customer_id=customer_id,
        workflow_id=workflow_id,
        scopes=gateway.registry.scopes_for(workflow_id),
        deadline=datetime.now(timezone.utc) + timedelta(seconds=6),
    )
    results = await gateway.execute_many([call], context, fallback={call.call_id: payload})
    result = results[0]
    evidence = result.evidence.model_dump(mode="json", by_alias=True) if result.evidence else {
        "system": system, "operation": operation, "requestId": str(uuid.uuid4()),
        "correlationId": correlation_id, "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "latencyMs": 0, "sourceIds": [], "stale": False,
    }
    evidence["tool"] = name
    evidence["status"] = result.status
    if result.error:
        evidence["error"] = result.error.code
    LATENCIES.append({"system": system, "operation": operation, "latencyMs": evidence["latencyMs"], "status": result.status, "at": evidence["fetchedAt"]})
    TOOL_CALLS.labels(system=system, tool=name, status=result.status).inc()
    TOOL_LATENCY.labels(system=system, tool=name).observe(evidence["latencyMs"] / 1000)
    await audit("TOOL_CALL", customer_id, {"tool": name, "system": system, "requestId": evidence["requestId"], "correlationId": correlation_id, "status": result.status, "latencyMs": evidence["latencyMs"]})
    await database.record_tool_call(call_id=call.call_id, turn_id=correlation_id, tool_name=name, system=system, status=result.status, latency_ms=evidence["latencyMs"], request_id=evidence["requestId"], evidence=evidence, error_code=result.error.code if result.error else None)
    return result.data, evidence


def _source_ids(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [str(payload[k]) for k in ("loanId", "cardId", "paymentId", "ruleId") if payload.get(k)]
    if isinstance(payload, list):
        return [str(row.get("paymentId")) for row in payload if isinstance(row, dict) and row.get("paymentId")]
    return []


def account_for(customer_id: str) -> dict[str, Any]:
    return CUSTOMERS[customer_id]


def unwrap_loan(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("loans"), list) and value["loans"]:
        return value["loans"][0]
    return value if isinstance(value, dict) else fallback


def unwrap_payments(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("payments"), list):
        return value["payments"]
    if isinstance(value, list):
        return value
    return [value] if isinstance(value, dict) and value.get("paymentId") else fallback


def unwrap_rule(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("rules"), list) and value["rules"]:
        return value["rules"][0]
    return value if isinstance(value, dict) and value.get("clauseId") else fallback


def policy_evidence(rule: dict[str, Any], decision: Any) -> dict[str, Any]:
    return {
        "type": "policy", "system": "POLICY", "tool": "policy.lookup", "operation": "Deterministic rule evaluation",
        "status": "OK", "ruleId": decision.rule_id, "clauseId": decision.clause_id,
        "clauseText": decision.clause_text, "applies": decision.applies,
        "outcome": decision.outcome, "sourceIds": [decision.rule_id, decision.clause_id],
        "latencyMs": 0, "stale": False,
    }


async def gather_tools(specs: list[tuple[str, str, str, Any]], customer_id: str, correlation_id: str, session_id: str, workflow_id: str, planned_tools: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    planned = set(planned_tools)
    calls = [tool_call(name, system, operation, customer_id, correlation_id, payload, session_id, workflow_id) for name, system, operation, payload in specs if name in planned]
    if len(calls) != len(specs):
        raise HTTPException(status_code=502, detail="The assistant plan omitted evidence required for this answer.")
    results = await asyncio.gather(*calls)
    return {spec[0]: result[0] for spec, result in zip(specs, results)}, [result[1] for result in results]


def fail_answer(system: str) -> str:
    return f"I can’t reach the {system} service right now, so I can’t safely confirm that information. Please try again in a moment. I haven’t made any changes."


def currency(amount: Any) -> str:
    return f"₹{Decimal(str(amount)):,.2f}"


def extract_amount(text: str) -> Decimal | None:
    match = re.search(r"(?:₹|rs\.?\s*)?([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    return Decimal(match.group(1).replace(",", "")) if match else None


async def prepare_action(customer_id: str, workflow_id: str, action_type: str, subject_ref: str | None, amount: str | None, session_id: str) -> dict[str, Any]:
    if workflow_id not in WORKFLOWS:
        raise HTTPException(status_code=404, detail="Unknown workflow.")
    valid_types = {"PAYMENT_DISPUTE", "PREPAYMENT_REQUEST", "CARD_DISPUTE", "TICKET"}
    if action_type not in valid_types:
        raise HTTPException(status_code=422, detail="This action is not available in the demo.")
    if action_type in {"PAYMENT_DISPUTE", "PREPAYMENT_REQUEST"} and workflow_id != "loan-servicing":
        raise HTTPException(status_code=422, detail="That action is not available in this workflow.")
    if action_type == "CARD_DISPUTE" and workflow_id != "credit-card":
        raise HTTPException(status_code=422, detail="That action is not available in this workflow.")
    if action_type == "PAYMENT_DISPUTE":
        owns = any(p["paymentId"] == subject_ref and p["status"] == "FAILED" for p in CUSTOMERS[customer_id]["payments"])
        if not owns:
            raise HTTPException(status_code=404, detail="That failed payment was not found for this account.")
        summary = f"Open a payment investigation for {subject_ref}"
    elif action_type == "CARD_DISPUTE":
        owned_transactions = {item["transactionId"] for item in CUSTOMERS[customer_id]["card"]["transactions"]}
        if subject_ref not in owned_transactions:
            raise HTTPException(status_code=404, detail="Select a posted transaction from your statement before preparing a dispute.")
        transaction = next(item for item in CUSTOMERS[customer_id]["card"]["transactions"] if item["transactionId"] == subject_ref)
        summary = f"Open a card transaction investigation for {transaction['merchant']} ({subject_ref}, {currency(transaction['amount'])})"
    elif action_type == "TICKET":
        reason = (subject_ref or "").strip()[:400]
        if not reason:
            raise HTTPException(status_code=422, detail="Describe what you need help with before preparing a service request.")
        offer = human_handoff.prepare(reason, workflow_id)
        summary = offer.summary
    else:
        value = Decimal(amount or "0")
        principal = Decimal(CUSTOMERS[customer_id]["loan"]["outstandingPrincipal"])
        if value <= 0 or value >= principal:
            raise HTTPException(status_code=422, detail="Enter a prepayment greater than ₹0 and less than your outstanding principal.")
        amount = str(money(value))
        summary = f"Submit a part-prepayment request for {currency(amount)} on {CUSTOMERS[customer_id]['loan']['loanId']}"
    token = str(uuid.uuid4())
    pending = {
        "token": token, "sessionId": session_id, "customerId": customer_id, "workflowId": workflow_id,
        "actionType": action_type, "subjectRef": subject_ref, "amount": amount, "summary": summary,
        "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    canonical_params = {"type": action_type, "subjectRef": subject_ref, "amount": amount}
    digest = hashlib.sha256(json.dumps(canonical_params, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    pending["paramsDigest"] = digest
    pending["idempotencyKey"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:service-request.create:{digest}:{token}"))
    # PENDING_ACTIONS remains a local test index; Redis is authoritative in the composed app.
    PENDING_ACTIONS[token] = pending
    await audit("ACTION_PREPARED", customer_id, {"actionType": action_type, "subjectRef": subject_ref, "expiresAt": pending["expiresAt"]})
    await state.save_confirmation(token, pending)
    await database.record_prepared_action(
        action_id=str(uuid.uuid4()), token_id=token, session_id=session_id, customer_id=customer_id,
        tool_name="service-request.create", digest=digest, params=canonical_params,
        idempotency_key=pending["idempotencyKey"],
    )
    return {"token": token, "summary": summary, "expiresAt": pending["expiresAt"], "actionType": action_type}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "horizon-voice-agent"}


@app.get("/api/voice/status")
def voice_status() -> dict[str, bool]:
    return {"serverSttConfigured": voice_provider.status.stt_configured, "serverTtsConfigured": voice_provider.status.tts_configured}


@app.get("/api/workflows")
def workflows() -> dict[str, Any]:
    return {"workflows": [{"id": key, **value} for key, value in WORKFLOWS.items()]}


@app.post("/api/session/start")
async def start_session(request: StartSessionRequest) -> dict[str, Any]:
    if request.workflowId not in WORKFLOWS:
        raise HTTPException(status_code=404, detail="Unknown workflow.")
    session_id = str(uuid.uuid4())
    await save_session(session_id, {"customerId": None, "workflowId": request.workflowId, "history": []})
    await database.record_session(session_id, request.workflowId)
    await audit("SESSION_STARTED", None, {"sessionId": session_id, "workflowId": request.workflowId})
    return {"sessionId": session_id, "otpHint": "Use demo code 246810", "expiresInMinutes": 30}


@app.post("/api/session/verify")
async def verify_session(request: VerifyRequest) -> dict[str, Any]:
    session = await session_for(request.sessionId, verified=False)
    customer_id = request.customerId.strip().upper()
    if request.otp != DEMO_OTP or customer_id not in CUSTOMERS:
        await audit("VERIFICATION_FAILED", None, {"sessionId": request.sessionId})
        raise HTTPException(status_code=401, detail="That demo code or customer ID isn’t recognized. Try CU-2291 or CU-3140 with code 246810.")
    session["customerId"] = customer_id
    await save_session(request.sessionId, session)
    await database.verify_session(request.sessionId, customer_id)
    await audit("CUSTOMER_VERIFIED", customer_id, {"sessionId": request.sessionId})
    customer = CUSTOMERS[customer_id]
    return {"customerId": customer_id, "name": customer["name"], "workflowId": session["workflowId"]}


@app.get("/api/account")
async def account(sessionId: str, workflowId: str = "loan-servicing") -> dict[str, Any]:
    session = await session_for(sessionId)
    if workflowId not in WORKFLOWS:
        raise HTTPException(status_code=404, detail="Unknown workflow.")
    if session["workflowId"] != workflowId:
        session["workflowId"] = workflowId
        await save_session(sessionId, session)
        await database.update_session_workflow(sessionId, workflowId)
    customer = account_for(session["customerId"])
    correlation_id = str(uuid.uuid4())
    specs = [("customer.profile", "CRM", "GET /v1/customers/{customerId}", customer)]
    if workflowId == "credit-card":
        specs.extend([
            ("card.summary", "CRM", "GET /v1/cards/{cardId}", customer["card"]),
            ("card.statement", "PAYMENTS", "GET /v1/cards/{cardId}/statement", customer["card"]),
        ])
    else:
        specs.extend([
            ("loan.summary", "LOAN", "GET /v1/customers/{customerId}/loans", customer["loan"]),
            ("payments.history", "PAYMENTS", "GET /v1/loans/{loanId}/payments?limit=3", customer["payments"]),
        ])
    data, evidence = await gather_tools(specs, session["customerId"], correlation_id, sessionId, workflowId, [spec[0] for spec in specs])
    failures = {item["tool"] for item in evidence if item["status"] == "ERROR"}
    warnings = [f"{item['system']} account data is temporarily unavailable." for item in evidence if item["status"] == "ERROR"]
    profile = data.get("customer.profile") or {}
    common = {"customer": {"customerId": profile.get("customerId", session["customerId"]), "name": profile.get("name", ""), "mobile": profile.get("mobile", "")}}
    requests = await _requests_for(session["customerId"])
    if workflowId == "credit-card":
        card = data.get("card.summary") if "card.summary" not in failures else None
        statement = data.get("card.statement") if "card.statement" not in failures else {}
        transactions = statement.get("transactions", [])
        recent = [{"paymentId": item["transactionId"], "dueDate": item["date"], "amount": item["amount"], "status": "SUCCESS"} for item in transactions[:3]]
        return {**common, "workflowId": workflowId, "card": card, "recentPayments": recent, "requests": requests, "warnings": warnings}
    loan = unwrap_loan(data["loan.summary"], customer["loan"]) if "loan.summary" not in failures else None
    recent_payments = unwrap_payments(data["payments.history"], []) if "payments.history" not in failures else []
    return {**common, "workflowId": workflowId, "loan": loan, "recentPayments": recent_payments[:3], "requests": requests, "warnings": warnings}


async def _requests_for(customer_id: str) -> list[dict[str, Any]]:
    rows = await database.fetch_all("SELECT request_id,request_type,subject_ref,summary,status,created_at FROM service_requests WHERE customer_id=:customer_id ORDER BY created_at DESC LIMIT 5", {"customer_id": customer_id})
    return [{"reference": row["request_id"], "type": row["request_type"], "subjectRef": row["subject_ref"], "summary": row["summary"], "status": row["status"], "createdAt": row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else row["created_at"]} for row in rows]


@app.post("/api/chat", response_model=TurnResponse)
async def chat(request: ChatRequest) -> dict[str, Any]:
    session = await session_for(request.sessionId)
    if request.workflowId not in WORKFLOWS:
        raise HTTPException(status_code=404, detail="Unknown workflow.")
    if request.workflowId != session["workflowId"]:
        session.pop("pending_service_request", None)
        session["workflowId"] = request.workflowId
    workflow = request.workflowId
    customer_id = session["customerId"]
    customer = CUSTOMERS[customer_id]
    message = request.message.strip()
    lowered = message.lower()
    pending_service_request = bool(session.get("pending_service_request"))
    planner_started = time.perf_counter()
    cancelling_request = pending_service_request and bool(re.search(r"\b(cancel|never mind|nevermind|stop)\b", lowered))
    if pending_service_request:
        plan = TurnPlan(intent="general" if cancelling_request else "service-request", tool_names=[] if cancelling_request else ["service-request.create"])
    else:
        plan = await orchestrator.plan(message, workflow)
    planner_ms = round((time.perf_counter() - planner_started) * 1000)
    intent = plan.intent
    correlation_id = str(uuid.uuid4())
    started = time.perf_counter()
    evidence: list[dict[str, Any]] = []
    action = None
    suggestions: list[str] = []

    if intent == "service-request":
        if pending_service_request:
            session.pop("pending_service_request", None)
        reason = re.sub(r"\b(?:please|i|we|want|need|would|like|to|raise|open|create|submit|make|a|an|the|service|support|request|ticket|for|about|regarding|help|with|my|me|can|you)\b", " ", message, flags=re.IGNORECASE)
        reason = re.sub(r"\s+", " ", reason).strip(" .,!?;:")
        if not reason or reason.lower() in {"loan", "card", "credit card", "payment", "account", "issue", "support", "loan account", "credit card account"}:
            session["pending_service_request"] = True
            answer = "Sure. What would you like the servicing team to help with? Please describe the request in one sentence. I’ll show it to you for confirmation before submitting."
            suggestions = ["Update my contact details", "Call me about my account", "I need help with a failed payment debit"]
        else:
            action = await prepare_action(customer_id, workflow, "TICKET", reason, None, request.sessionId)
            answer = f"I’ve prepared a service request for review: {action['summary']}. Please confirm to submit it; nothing has been sent yet."
    elif cancelling_request:
        session.pop("pending_service_request", None)
        answer = "No problem. I cancelled the service request. Nothing was submitted."
    elif workflow == "credit-card":
        card = customer["card"]
        if intent == "card-dispute":
            specs = [("card.statement", "PAYMENTS", "GET /v1/cards/{cardId}/statement", {"cardId": card["cardId"], "statementBalance": card["statementBalance"], "dueDate": card["dueDate"], "minimumDue": card["minimumDue"], "transactions": card["transactions"]}), ("policy.lookup", "POLICY", "GET /v1/policies/rules?topic=CARD_DISPUTE", POLICIES["CARD_DISPUTE"])]
            data, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
            if any(item["status"] == "ERROR" for item in evidence):
                answer = fail_answer("card payments")
            else:
                statement = data["card.statement"]
                transactions = statement.get("transactions", card["transactions"])
                rule = unwrap_rule(data["policy.lookup"], POLICIES["CARD_DISPUTE"])
                decision = rules_engine.evaluate(rule, {})
                evidence.append(policy_evidence(rule, decision))
                match = re.search(r"TX-\d+", message, re.IGNORECASE)
                transaction = next((item for item in transactions if item["transactionId"] == (match.group(0).upper() if match else "")), None)
                if transaction:
                    action = await prepare_action(customer_id, workflow, "CARD_DISPUTE", transaction["transactionId"], None, request.sessionId)
                    answer = f"I’ve prepared a dispute review for {transaction['merchant']} ({transaction['transactionId']}, {currency(transaction['amount'])}). {decision.clause_text} Please review and confirm; no dispute has been submitted yet."
                else:
                    answer = "Which posted transaction would you like to dispute? Your recent statement activity is:\n" + "\n".join(f"• {item['date']} · {item['merchant']} · {currency(item['amount'])} · {item['transactionId']}" for item in transactions) + f"\n\n{decision.clause_text}"
            suggestions = [f"Dispute transaction {item['transactionId']}" for item in card["transactions"][:2]] + ["Show my statement"]
        else:
            specs = [("card.summary", "CRM", "GET /v1/cards/{cardId}", card), ("card.statement", "PAYMENTS", "GET /v1/cards/{cardId}/statement", {"cardId": card["cardId"], "statementBalance": card["statementBalance"], "dueDate": card["dueDate"], "minimumDue": card["minimumDue"], "transactions": card["transactions"]})]
            data, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
            if any(item["status"] == "ERROR" for item in evidence):
                answer = fail_answer("card")
            else:
                card = data["card.summary"]
                statement = data["card.statement"]
                transactions = statement.get("transactions", [])
                answer = f"Your {card['product']} ending {card['lastFour']} has an outstanding balance of {currency(card['outstanding'])}. Your latest statement balance is {currency(statement['statementBalance'])}, with a minimum due of {currency(statement['minimumDue'])} by {statement['dueDate']}. You have {card['rewardPoints']:,} reward points.\n\nRecent posted transactions:\n" + "\n".join(f"• {item['date']} · {item['merchant']} · {currency(item['amount'])} · {item['transactionId']}" for item in transactions)
                suggestions = [f"Dispute transaction {transactions[0]['transactionId']}", "Show my card statement"]
    elif intent in {"failed-payments", "payment-dispute", "last-payment", "next-emi"}:
        if intent in {"failed-payments", "payment-dispute"}:
            six_months_ago = datetime.now(timezone.utc).date() - timedelta(days=183)
            specs = [("payments.history", "PAYMENTS", f"GET /v1/loans/{{loanId}}/payments?status=FAILED&from={six_months_ago.isoformat()}", customer["payments"]), ("policy.lookup", "POLICY", "GET /v1/policies/rules?topic=PAYMENT_FAILURE", POLICIES["PAYMENT_FAILURE"])]
            data, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
            if any(item["status"] == "ERROR" for item in evidence):
                answer = fail_answer("payments")
                suggestions = ["Try again", "Open a support ticket"]
            else:
                payment_rows = unwrap_payments(data["payments.history"], customer["payments"])
                failed = [payment for payment in payment_rows if payment["status"] == "FAILED" and datetime.fromisoformat(payment["dueDate"]).date() >= six_months_ago]
                rule = unwrap_rule(data["policy.lookup"], POLICIES["PAYMENT_FAILURE"])
                decision = rules_engine.evaluate(rule, {})
                evidence.append(policy_evidence(rule, decision))
                session["last_failed_payments"] = [payment["paymentId"] for payment in failed]
                answer = "Here are the failed payment attempts I found, with the recorded reasons:\n" + "\n".join(f"• {p['dueDate']} · {currency(p['amount'])} · {p['failureReason']} (reference {p['paymentId']})" for p in failed) + f"\n\n{decision.clause_text}"
                suggestions = ["Raise a dispute on the first one", "Why did my EMI change?"]
                if "dispute" in lowered:
                    match = re.search(r"PM-\d+", message, re.IGNORECASE)
                    ordinal = re.search(r"\b(first|1st|second|2nd|third|3rd)\b", lowered)
                    position = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}
                    selected = position.get(ordinal.group(1)) if ordinal else None
                    subject = match.group(0).upper() if match else (failed[selected]["paymentId"] if selected is not None and selected < len(failed) else None)
                    if subject:
                        action = await prepare_action(customer_id, workflow, "PAYMENT_DISPUTE", subject, None, request.sessionId)
                        answer += "\n\nI’ve prepared a dispute for your review. It will only be sent if you confirm it."
                    else:
                        answer += "\n\nPlease tell me which payment reference to dispute, or ask me to list the failed payments first. I won’t guess which one you mean."
        elif intent == "last-payment":
            specs = [("payments.history", "PAYMENTS", "GET /v1/loans/{loanId}/payments?limit=1", customer["payments"])]
            data, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
            if any(item["status"] == "ERROR" for item in evidence):
                answer = fail_answer("payments")
            else:
                p = max(unwrap_payments(data["payments.history"], [customer["lastPayment"]]), key=lambda payment: payment.get("dueDate", payment.get("date", "")))
                answer = f"Your latest payment of {currency(p['amount'])} was recorded as {p['status'].lower()} on {p['date']} via {p['channel'].replace('_', ' ').lower()} (reference {p['paymentId']})."
                suggestions = ["What is my next EMI?", "Show failed payments"]
        else:
            loan = customer["loan"]
            specs = [("loan.summary", "LOAN", "GET /v1/customers/{customerId}/loans", loan)]
            data, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
            loan = unwrap_loan(data.get("loan.summary"), loan)
            answer = fail_answer("loan") if any(item["status"] == "ERROR" for item in evidence) else f"Your next EMI is {currency(loan['emi'])}, due on {loan['nextDueDate']}. The loan has {loan['tenureRemainingMonths']} months remaining."
            suggestions = ["Why did my EMI change?", "Show failed payments"]
    elif intent == "foreclosure":
        loan = customer["loan"]
        rule = POLICIES["FORECLOSURE"]
        specs = [("loan.detail", "LOAN", "GET /v1/loans/{loanId}", loan), ("policy.lookup", "POLICY", "GET /v1/policies/rules?topic=FORECLOSURE", rule)]
        data, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
        if any(item["status"] == "ERROR" for item in evidence):
            answer = fail_answer("loan or policy")
        else:
            loan = data["loan.detail"]
            rule = unwrap_rule(data["policy.lookup"], rule)
            decision = rules_engine.evaluate(rule, {"rateType": loan["rateType"]})
            evidence.append(policy_evidence(rule, decision))
            answer = ("Based on the applicable rule for your floating-rate personal loan, no foreclosure charge applies." if decision.applies else "I couldn’t find a foreclosure rule that applies to this loan’s rate type. I can’t confirm the charge, so I won’t guess.") + f" Source: {decision.clause_id} — {decision.clause_text}"
            if not decision.applies:
                reason = "confirm the foreclosure charge for this fixed-rate loan"
                offer = human_handoff.prepare(reason, workflow)
                action = await prepare_action(customer_id, workflow, offer.action_type, reason, None, request.sessionId)
                answer += " I can prepare a specialist review for your confirmation."
        suggestions = ["What would a part-prepayment save?", "What is my next EMI?"]
    elif intent == "prepayment":
        loan = customer["loan"]
        rule = POLICIES["PREPAYMENT"]
        specs = [("loan.detail", "LOAN", "GET /v1/loans/{loanId}", loan), ("loan.rate-history", "LOAN", "GET /v1/loans/{loanId}/rate-history", {"loanId": loan["loanId"], "history": [{"annualRatePercent": loan["annualRatePercent"], "effectiveFrom": loan["rateEffectiveDate"]}], "previousRatePercent": loan["previousRatePercent"]}), ("policy.lookup", "POLICY", "GET /v1/policies/rules?topic=PREPAYMENT", rule), ("payments.history", "PAYMENTS", "GET /v1/loans/{loanId}/payments?limit=1", customer["payments"])]
        data, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
        if any(item["status"] == "ERROR" for item in evidence):
            answer = fail_answer("loan or policy")
        else:
            loan = data["loan.detail"]
            rule = unwrap_rule(data["policy.lookup"], rule)
            rate_data = data["loan.rate-history"]
            old_rate = rate_data.get("previousRatePercent", loan["previousRatePercent"])
            latest_rate = rate_data.get("history", [{}])[-1].get("annualRatePercent", loan["annualRatePercent"])
            if str(latest_rate) != str(loan["annualRatePercent"]):
                answer = fail_answer("loan rate history")
            else:
                answer = ""
            decision = rules_engine.evaluate(rule, {"rateType": loan["rateType"]})
            evidence.append(policy_evidence(rule, decision))
            old_emi, current_emi = Decimal(loan["previousEmi"]), Decimal(loan["emi"])
            if Decimal(old_rate) != Decimal(loan["annualRatePercent"]):
                answer += f"Your EMI changed from {currency(old_emi)} to {currency(current_emi)} after the floating rate moved from {old_rate}% to {loan['annualRatePercent']}% on {loan['rateEffectiveDate']}. The rate reset is reflected in your loan record."
            else:
                answer += f"Your current EMI is {currency(current_emi)} at {loan['annualRatePercent']}%. No rate change is recorded since {loan['rateEffectiveDate']}."
            amount = extract_amount(message)
            if amount is None:
                answer += "\n\nWhat amount would you like me to simulate? I won’t assume an amount for a financial calculation."
                suggestions = ["Simulate ₹20,000 prepayment", "Simulate ₹50,000 prepayment"]
                elapsed = round((time.perf_counter() - started) * 1000)
                turn = {"turnId": correlation_id, "message": message, "answer": answer, "workflowId": workflow, "channel": request.channel, "latencyMs": elapsed, "createdAt": datetime.now(timezone.utc).isoformat()}
                session["history"].append(turn)
                session["history"] = session["history"][-30:]
                await save_session(request.sessionId, session)
                await database.record_turn(turn_id=correlation_id, session_id=request.sessionId, seq=len(session["history"]), channel=request.channel, user_text=mask_log_text(message), answer_text=mask_log_text(answer), total_ms=elapsed, llm_ms=planner_ms, tools_ms=max((item["latencyMs"] for item in evidence if item.get("requestId")), default=0), verifier_outcome=next((item.get("outcome") for item in evidence if item.get("type") == "verification"), None), started_at=datetime.now(timezone.utc) - timedelta(milliseconds=elapsed))
                await audit("TURN_COMPLETED", customer_id, {"turnId": correlation_id, "workflowId": workflow, "channel": request.channel, "latencyMs": elapsed})
                TURN_CALLS.labels(channel=request.channel, outcome="ok").inc()
                TURN_LATENCY.labels(channel=request.channel).observe(elapsed / 1000)
                record_turn_stage_metrics(request.channel, total_ms=elapsed, llm_ms=planner_ms, tools_ms=max((item["latencyMs"] for item in evidence if item.get("requestId")), default=0))
                return {"turnId": correlation_id, "answer": answer, "evidence": evidence, "action": None, "suggestions": suggestions, "latencyMs": elapsed, "channel": request.channel}
            try:
                calc = prepayment_savings(Decimal(loan["outstandingPrincipal"]), Decimal(loan["annualRatePercent"]), Decimal(loan["emi"]), amount)
            except ValueError:
                answer += f"\n\nI can’t calculate that amount: a one-time prepayment must be greater than ₹0 and less than the outstanding principal of {currency(loan['outstandingPrincipal'])}."
            else:
                answer += f"\n\nIf {currency(amount)} is applied to principal today and you keep the EMI unchanged, the estimate is {currency(calc['interest_saved'])} less interest and about {calc['months_saved']} fewer monthly instalments. This is a simulation, not a submitted payment."
                if decision.applies:
                    answer += f"\n\nApplied rule {decision.clause_id}: {decision.clause_text}"
                else:
                    answer += f"\n\nThe available prepayment clause {decision.clause_id} is limited to floating-rate loans and does not establish fees for your fixed-rate loan. Please confirm current fees with a servicing specialist."
                answer += f"\nCalculation inputs: outstanding principal {currency(loan['outstandingPrincipal'])}, annual rate {loan['annualRatePercent']}%, EMI {currency(loan['emi'])}, one-time prepayment {currency(amount)}."
                verified_amounts = {
                    currency(old_emi)[1:], currency(current_emi)[1:], currency(loan["outstandingPrincipal"])[1:],
                    currency(loan["emi"])[1:], currency(amount)[1:], currency(calc["interest_saved"])[1:],
                }
                mentioned_amounts = re.findall(r"₹([\d,]+\.\d{2})", answer)
                numbers_verified = all(value in verified_amounts for value in mentioned_amounts)
                clause_verified = bool(decision.clause_id and decision.clause_id in answer)
                if not numbers_verified or not clause_verified:
                    answer = f"Your EMI changed from {currency(old_emi)} to {currency(current_emi)} as the rate moved from {old_rate}% to {loan['annualRatePercent']}%. Verified simulation: applying {currency(amount)} to principal while keeping your EMI at {currency(loan['emi'])} saves an estimated {currency(calc['interest_saved'])} in interest. The policy source is {decision.clause_id}."
                evidence.append({"type": "verification", "system": "VERIFIER", "tool": "evidence_verifier", "operation": "Money figures and policy citation", "status": "OK", "outcome": "PASSED" if numbers_verified and clause_verified else "TEMPLATE", "numbersVerified": numbers_verified, "clauseVerified": clause_verified, "latencyMs": 0, "stale": False})
                evidence.append({"type": "calculation", "system": "CALCULATOR", "tool": "prepayment_savings", "operation": "Fixed EMI; one-time principal reduction", "status": "OK", "inputs": {"outstandingPrincipal": str(loan["outstandingPrincipal"]), "annualRatePercent": str(loan["annualRatePercent"]), "emi": str(loan["emi"]), "prepayment": str(amount)}, "result": {key: str(value) for key, value in calc.items()}, "latencyMs": 0, "stale": False})
                if any(word in lowered for word in ("request", "submit", "make the prepayment", "go ahead")):
                    action = await prepare_action(customer_id, workflow, "PREPAYMENT_REQUEST", loan["loanId"], str(amount), request.sessionId)
                    answer += "\n\nI’ve prepared a prepayment request for review. It will only be submitted if you confirm."
            suggestions = ["Raise a prepayment request", "Show failed payments"]
    else:
        loan = customer["loan"]
        specs = [("loan.summary", "LOAN", "GET /v1/customers/{customerId}/loans", loan)]
        _, evidence = await gather_tools(specs, customer_id, correlation_id, request.sessionId, workflow, plan.tool_names)
        answer = fail_answer("loan") if any(item["status"] == "ERROR" for item in evidence) else f"I can help with your loan account. Your next EMI is {currency(loan['emi'])}, due {loan['nextDueDate']}. Ask me to explain your EMI change, estimate a prepayment, check a payment, or review a policy."
        suggestions = ["Why did my EMI change?", "Show failed payments", "Am I eligible for foreclosure without a penalty?"]

    verifier = next((item for item in evidence if item.get("type") == "verification"), None)
    composition_started = time.perf_counter()
    model_candidate = None if intent == "service-request" or cancelling_request else await orchestrator.compose(message, answer, evidence)
    planner_ms += round((time.perf_counter() - composition_started) * 1000)
    if model_candidate:
        accepted, reasons = verify_rewrite(answer, model_candidate)
        if accepted:
            answer = model_candidate
            verifier_outcome = "MODEL_PASSED"
        else:
            verifier_outcome = "REGENERATED"
        if verifier is None:
            verifier = {"type": "verification", "system": "VERIFIER", "tool": "answer_verifier", "operation": "Model composition validation", "status": "OK", "latencyMs": 0, "stale": False}
            evidence.append(verifier)
        verifier.update({"outcome": verifier_outcome, "reasons": reasons if not accepted else [], "numbersVerified": accepted, "clauseVerified": accepted})
    elif verifier is None:
        evidence.append({"type": "verification", "system": "VERIFIER", "tool": "answer_verifier", "operation": "Deterministic evidence template", "status": "OK", "outcome": "PASSED", "numbersVerified": True, "clauseVerified": True, "latencyMs": 0, "stale": False})

    elapsed = round((time.perf_counter() - started) * 1000)
    turn = {"turnId": correlation_id, "message": message, "answer": answer, "workflowId": workflow, "channel": request.channel, "latencyMs": elapsed, "createdAt": datetime.now(timezone.utc).isoformat()}
    session["history"].append(turn)
    session["history"] = session["history"][-30:]
    await save_session(request.sessionId, session)
    await database.record_turn(turn_id=correlation_id, session_id=request.sessionId, seq=len(session["history"]), channel=request.channel, user_text=mask_log_text(message), answer_text=mask_log_text(answer), total_ms=elapsed, llm_ms=planner_ms, tools_ms=max((item["latencyMs"] for item in evidence if item.get("requestId")), default=0), verifier_outcome=next((item.get("outcome") for item in evidence if item.get("type") == "verification"), None), started_at=datetime.now(timezone.utc) - timedelta(milliseconds=elapsed))
    await audit("TURN_COMPLETED", customer_id, {"turnId": correlation_id, "workflowId": workflow, "channel": request.channel, "latencyMs": elapsed})
    TURN_CALLS.labels(channel=request.channel, outcome="ok").inc()
    TURN_LATENCY.labels(channel=request.channel).observe(elapsed / 1000)
    record_turn_stage_metrics(request.channel, total_ms=elapsed, llm_ms=planner_ms, tools_ms=max((item["latencyMs"] for item in evidence if item.get("requestId")), default=0))
    return {"turnId": correlation_id, "answer": answer, "evidence": evidence, "action": action, "suggestions": suggestions, "latencyMs": elapsed, "channel": request.channel}


async def _emit_turn(websocket: WebSocket, request: ChatRequest, stt_ms: int | None = None) -> None:
    turn_started = time.perf_counter()
    first_response_ms: int | None = None
    await websocket.send_json({"type": "turn.started", "channel": request.channel})
    chat_task = asyncio.create_task(chat(request))
    tts_ms = 0
    try:
        done, _ = await asyncio.wait({chat_task}, timeout=0.7)
        if not done:
            await websocket.send_json({"type": "turn.progress", "message": "I’m checking your account securely."})
            first_response_ms = round((time.perf_counter() - turn_started) * 1000)
        result = await chat_task
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", result["answer"]):
            if not sentence:
                continue
            if first_response_ms is None:
                first_response_ms = round((time.perf_counter() - turn_started) * 1000)
            await websocket.send_json({"type": "assistant.delta", "text": sentence + " "})
            if request.channel == "VOICE" and voice_provider.status.tts_configured:
                tts_started = time.perf_counter()
                audio = await voice_provider.synthesize(sentence)
                tts_ms += round((time.perf_counter() - tts_started) * 1000)
                await websocket.send_json({"type": "voice.audio.chunk", "mimeType": "audio/mpeg"})
                await websocket.send_bytes(audio)
        if stt_ms is not None:
            await database.update_turn_stages(result["turnId"], stt_ms=stt_ms, tts_ms=tts_ms, first_response_ms=first_response_ms)
            TURN_STAGE_LATENCY.labels(channel="VOICE", stage="stt").observe(stt_ms / 1000)
            if voice_provider.status.tts_configured:
                TURN_STAGE_LATENCY.labels(channel="VOICE", stage="tts").observe(tts_ms / 1000)
        else:
            await database.update_turn_stages(result["turnId"], first_response_ms=first_response_ms)
        if first_response_ms is not None:
            TURN_STAGE_LATENCY.labels(channel=request.channel, stage="first_response").observe(first_response_ms / 1000)
        await websocket.send_json({"type": "turn.completed", **{key: value for key, value in result.items() if key != "answer"}})
    except asyncio.CancelledError:
        chat_task.cancel()
        raise
    except WebSocketDisconnected:
        chat_task.cancel()
        raise
    except HTTPException as error:
        await websocket.send_json({"type": "error", "code": "TURN_FAILED", "message": str(error.detail)})
    except ToolGatewayError as error:
        await websocket.send_json({"type": "error", "code": error.code, "message": str(error)})
    except (httpx.HTTPError, RuntimeError, ValueError) as error:
        await websocket.send_json({"type": "voice.error", "message": f"Voice processing failed ({type(error).__name__})."})


async def _process_audio_turn(websocket: WebSocket, session_id: str, audio: bytes, mime_type: str, workflow_id: str) -> None:
    try:
        stt_started = time.perf_counter()
        transcript = await voice_provider.transcribe(audio, mime_type)
        stt_ms = round((time.perf_counter() - stt_started) * 1000)
        await websocket.send_json({"type": "voice.transcript", "text": transcript})
        session = await session_for(session_id)
        session["workflowId"] = workflow_id
        await save_session(session_id, session)
        await _emit_turn(websocket, ChatRequest(sessionId=session_id, message=transcript, workflowId=workflow_id, channel="VOICE"), stt_ms)
    except asyncio.CancelledError:
        raise
    except WebSocketDisconnected:
        raise
    except (HTTPException, httpx.HTTPError, RuntimeError, ValueError) as error:
        await websocket.send_json({"type": "voice.error", "message": f"Voice processing failed ({type(error).__name__})."})


@app.websocket("/ws/conversations/{session_id}")
async def conversation_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        await session_for(session_id)
    except HTTPException:
        await websocket.send_json({"type": "error", "code": "SESSION_REQUIRED", "message": "Verify your identity before starting a conversation."})
        await websocket.close(code=4401)
        return

    active_response: asyncio.Task[None] | None = None
    audio_parts: list[bytes] | None = None
    audio_bytes = 0
    audio_mime = "audio/webm"
    audio_workflow = "loan-servicing"
    audio_rejected = False

    async def cancel_active() -> None:
        nonlocal active_response
        if active_response and not active_response.done():
            active_response.cancel()
            await asyncio.gather(active_response, return_exceptions=True)
            await websocket.send_json({"type": "turn.cancelled"})
        active_response = None

    try:
        while True:
            packet = await websocket.receive()
            if packet.get("bytes") is not None:
                if audio_parts is None or audio_rejected:
                    continue
                audio_bytes += len(packet["bytes"])
                if audio_bytes > 15 * 1024 * 1024:
                    audio_rejected = True
                    audio_parts.clear()
                    await websocket.send_json({"type": "voice.error", "message": "The audio turn is larger than the 15 MB demo limit."})
                else:
                    audio_parts.append(packet["bytes"])
                continue
            if packet.get("text") is None:
                continue
            event = json.loads(packet["text"])
            event_type = event.get("type")
            if event_type == "voice.audio.start":
                if not voice_provider.status.stt_configured:
                    await websocket.send_json({"type": "voice.unavailable", "message": "Server speech recognition is not configured. Use the browser speech fallback or type your message."})
                    continue
                requested_workflow = event.get("workflowId", "loan-servicing")
                if requested_workflow not in WORKFLOWS:
                    await websocket.send_json({"type": "error", "code": "UNKNOWN_WORKFLOW", "message": "Unknown servicing workflow."})
                    continue
                await cancel_active()
                audio_parts = []
                audio_bytes = 0
                audio_rejected = False
                audio_mime = event.get("mimeType", "audio/webm")
                audio_workflow = requested_workflow
            elif event_type == "voice.audio.end":
                if audio_parts is not None and not audio_rejected:
                    active_response = asyncio.create_task(_process_audio_turn(websocket, session_id, b"".join(audio_parts), audio_mime, audio_workflow))
                audio_parts = None
            elif event_type == "cancel":
                await cancel_active()
            elif event_type == "turn":
                workflow_id = event.get("workflowId", "loan-servicing")
                channel = event.get("channel", "TEXT")
                if workflow_id not in WORKFLOWS or channel not in {"TEXT", "VOICE"} or not isinstance(event.get("message"), str):
                    await websocket.send_json({"type": "error", "code": "INVALID_EVENT", "message": "Turn requires valid text, workflow, and TEXT/VOICE channel."})
                    continue
                await cancel_active()
                active_response = asyncio.create_task(_emit_turn(websocket, ChatRequest(sessionId=session_id, message=event["message"], workflowId=workflow_id, channel=channel)))
            else:
                await websocket.send_json({"type": "error", "code": "INVALID_EVENT", "message": "Unsupported conversation event."})
    except (WebSocketDisconnect, WebSocketDisconnected):
        if active_response and not active_response.done():
            active_response.cancel()
            await asyncio.gather(active_response, return_exceptions=True)


@app.post("/api/actions/prepare")
async def action_prepare(request: PrepareActionRequest) -> dict[str, Any]:
    session = await session_for(request.sessionId)
    return await prepare_action(session["customerId"], request.workflowId, request.actionType, request.subjectRef, request.amount, request.sessionId)


@app.post("/api/actions/confirm")
async def action_confirm(request: ConfirmActionRequest) -> dict[str, Any]:
    session = await session_for(request.sessionId)
    prior_result = await state.get_action_result(request.token)
    if prior_result:
        return {**prior_result, "replayed": True}
    # GETDEL semantics make confirmation single-use across conversation workers.
    pending = await state.consume_confirmation(request.token)
    if not pending or pending["sessionId"] != request.sessionId or pending["customerId"] != session["customerId"]:
        raise HTTPException(status_code=410, detail="This confirmation has expired or has already been used.")
    if datetime.fromisoformat(pending["expiresAt"]) < datetime.now(timezone.utc):
        PENDING_ACTIONS.pop(request.token, None)
        raise HTTPException(status_code=410, detail="This confirmation has expired. Please prepare the request again.")
    PENDING_ACTIONS.pop(request.token, None)
    idempotency_key = pending["idempotencyKey"]
    # Persist the authorization attempt before sending the state-changing request.
    await audit("ACTION_ATTEMPTED", session["customerId"], {"actionType": pending["actionType"], "subjectRef": pending["subjectRef"], "idempotencyKey": idempotency_key})
    try:
        result = await gateway.execute_write(
            "service-request.create",
            {
                "loanId": CUSTOMERS[session["customerId"]]["loan"]["loanId"] if pending["workflowId"] == "loan-servicing" else None,
                "cardId": CUSTOMERS[session["customerId"]]["card"]["cardId"] if pending["workflowId"] == "credit-card" else None,
                "type": pending["actionType"], "subjectRef": pending["subjectRef"],
                "summary": pending["summary"], "amount": pending["amount"],
            },
            TurnContext(
                session_id=request.sessionId, turn_id=str(uuid.uuid4()), customer_id=session["customerId"],
                workflow_id=pending["workflowId"], scopes=gateway.registry.scopes_for(pending["workflowId"]),
                deadline=datetime.now(timezone.utc) + timedelta(seconds=6),
            ),
            idempotency_key,
        )
    except ToolGatewayError as error:
        await database.complete_action(request.token, "UNKNOWN")
        if error.code == "OutcomeUnknown":
            await state.save_confirmation(request.token, pending)
        raise HTTPException(status_code=503, detail=f"Action outcome is {error.code.lower().replace('_', ' ')}. Retry this confirmation to check the same idempotent request.") from error

    request_id = result["requestId"]
    now = result.get("createdAt", datetime.now(timezone.utc).isoformat())
    confirmation_result = {"reference": request_id, "status": result.get("status", "OPEN"), "createdAt": now, "replayed": False, "summary": pending["summary"]}
    try:
        existing = await database.fetch_one("SELECT request_id,status,created_at FROM service_requests WHERE idempotency_key=:key", {"key": idempotency_key})
        if existing:
            created_at = existing["created_at"].isoformat() if isinstance(existing["created_at"], datetime) else existing["created_at"]
            confirmation_result = {"reference": existing["request_id"], "status": existing["status"], "createdAt": created_at, "replayed": True, "summary": pending["summary"]}
        else:
            await database.execute(
                "INSERT INTO service_requests(request_id,customer_id,workflow_id,request_type,subject_ref,summary,status,idempotency_key,created_at) VALUES(:request_id,:customer_id,:workflow_id,:request_type,:subject_ref,:summary,:status,:key,:created_at)",
                {"request_id": request_id, "customer_id": session["customerId"], "workflow_id": pending["workflowId"], "request_type": pending["actionType"], "subject_ref": pending["subjectRef"], "summary": pending["summary"], "status": result.get("status", "OPEN"), "key": idempotency_key, "created_at": datetime.fromisoformat(now) if database.is_postgres else now},
            )
        await database.complete_action(request.token, "EXECUTED", request_id)
        await audit("ACTION_EXECUTED", session["customerId"], {"reference": request_id, "actionType": pending["actionType"], "subjectRef": pending["subjectRef"], "idempotencyKey": idempotency_key})
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail=f"Service Operations accepted request {request_id}, but the audit store is unavailable. Do not submit a second request; refresh status shortly.") from error
    await state.save_action_result(request.token, confirmation_result)
    ACTION_CALLS.labels(type=pending["actionType"], outcome="executed").inc()
    return confirmation_result


@app.get("/api/metrics")
async def metrics() -> dict[str, Any]:
    def percentile(values: list[int], p: float) -> int:
        if not values:
            return 0
        values = sorted(values)
        index = min(len(values) - 1, max(0, round((len(values) - 1) * p)))
        return values[index]
    tool_rows = await database.fetch_all("SELECT system_name,tool_name,status,latency_ms FROM tool_calls")
    values = [row["latency_ms"] for row in tool_rows]
    by_system = {}
    for system in sorted({row["system_name"] for row in tool_rows}):
        group = [row["latency_ms"] for row in tool_rows if row["system_name"] == system]
        by_system[system] = {"calls": len(group), "p50Ms": percentile(group, .50), "p95Ms": percentile(group, .95), "p99Ms": percentile(group, .99)}
    turn_rows = await database.fetch_all("SELECT stt_ms,llm_ms,tools_ms,tts_ms,first_response_ms,total_ms FROM turns")
    stages = {}
    for stage, column in (("stt", "stt_ms"), ("model", "llm_ms"), ("tools", "tools_ms"), ("tts", "tts_ms"), ("firstResponse", "first_response_ms"), ("total", "total_ms")):
        values_for_stage = [row[column] for row in turn_rows if row[column] is not None]
        stages[stage] = {"count": len(values_for_stage), "p50Ms": percentile(values_for_stage, .50), "p95Ms": percentile(values_for_stage, .95), "p99Ms": percentile(values_for_stage, .99)}
    actions = (await database.fetch_one("SELECT COUNT(*) AS count FROM service_requests")) or {"count": 0}
    return {"toolCalls": len(tool_rows), "toolLatencyMs": {"p50": percentile(values, .50), "p95": percentile(values, .95), "p99": percentile(values, .99)}, "bySystem": by_system, "stageLatencyMs": stages, "actionsCreated": actions["count"], "turnsRecorded": len(turn_rows), "failureInjection": FAILURES}


@app.get("/api/metrics/prometheus", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/audit")
async def recent_audit(sessionId: str) -> dict[str, Any]:
    session = await session_for(sessionId)
    customer_id = session["customerId"]
    rows = await database.fetch_all("SELECT occurred_at,event_type,details FROM audit_events WHERE customer_ref=:customer_id ORDER BY audit_id DESC LIMIT 30", {"customer_id": customer_id})
    return {"events": [{"at": row["occurred_at"].isoformat() if isinstance(row["occurred_at"], datetime) else row["occurred_at"], "event": row["event_type"], "details": json.loads(row["details"]) if isinstance(row["details"], str) else row["details"]} for row in rows]}


@app.post("/api/demo/failures")
def set_failure(request: FailureRequest) -> dict[str, Any]:
    if request.system not in FAILURES:
        raise HTTPException(status_code=404, detail="Failure injection is available for payments only.")
    FAILURES[request.system] = request.enabled
    return {"system": request.system, "enabled": request.enabled}
