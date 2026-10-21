# Generated from design: tool-platform-enterprise-systems-integration-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-system-design-v1.md (v1), enterprise-voice-agent-data-design-v1.md (v1)
# Ticket: none
"""Separate synthetic CRM, Loan, Payments, Policy, and Service Ops REST APIs."""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from prometheus_client import make_asgi_app
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from backend.app.main import CUSTOMERS, POLICIES
from backend.app.platform.database import database

@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.initialize()
    try:
        yield
    finally:
        await database.close()


app = FastAPI(title="Synthetic Enterprise Systems", version="1.0.0", description="Isolated mock CRM, Loan, Payments, Policy and Service Ops APIs", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())
_REQUESTS: dict[str, dict[str, Any]] = {}
_IDEMPOTENCY: dict[str, dict[str, Any]] = {}
_FAILURES: dict[str, bool] = {"CRM": False, "LOAN": False, "PAYMENTS": False, "POLICY": False, "SERVICE_OPS": False}
INDIA_TZ = ZoneInfo("Asia/Kolkata")


def local_date(value: datetime) -> str:
    return value.astimezone(INDIA_TZ).date().isoformat()


class ServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customerId: str
    loanId: str | None = None
    cardId: str | None = None
    type: str
    subjectRef: str | None = None
    summary: str = Field(min_length=1, max_length=500)
    confirmedAt: datetime
    sourceCorrelationId: str
    amount: str | None = None


@app.middleware("http")
async def simulated_system_behavior(request: Request, call_next):
    system = request.headers.get("x-mock-system", "")
    if system and _FAILURES.get(system, False):
        return JSONResponse(status_code=503, content={"error": {"code": "UPSTREAM_UNAVAILABLE", "message": "Injected system failure", "retryable": True}})
    failure_rate = float(os.getenv("MOCK_FAILURE_RATE", "0.05"))
    if system and random.random() < failure_rate:
        return JSONResponse(status_code=503, content={"error": {"code": "UPSTREAM_UNAVAILABLE", "message": "Injected intermittent system failure", "retryable": True}})
    minimum = int(os.getenv("MOCK_LATENCY_MIN_MS", "100"))
    maximum = int(os.getenv("MOCK_LATENCY_MAX_MS", "3000"))
    if system:
        await asyncio.sleep(random.uniform(minimum, maximum) / 1000)
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = request.headers.get("x-correlation-id", "")
    response.headers["X-Request-Id"] = request.headers.get("x-request-id", str(uuid.uuid4()))
    return response


@app.middleware("http")
async def service_auth(request: Request, call_next):
    expected = os.getenv("MOCK_SERVICE_TOKEN", "local-demo-service")
    public_paths = {"/health", "/metrics", "/metrics/", "/docs", "/openapi.json", "/redoc"}
    if expected and request.url.path not in public_paths and request.headers.get("authorization") != f"Bearer {expected}":
        return JSONResponse(status_code=401, content={"error": {"code": "UNAUTHORIZED", "message": "Invalid service identity", "retryable": False}})
    return await call_next(request)


async def customer_for(customer_id: str) -> dict[str, Any]:
    if database.is_postgres:
        customer_row = await database.fetch_one("SELECT customer_id,full_name,mobile_e164,kyc_status FROM core.customer WHERE customer_id=:customer_id AND deleted_at IS NULL", {"customer_id": customer_id})
        if not customer_row:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Customer not found", "retryable": False}})
        loan_row = await database.fetch_one("SELECT * FROM core.loan WHERE customer_id=:customer_id AND status='ACTIVE' AND deleted_at IS NULL ORDER BY disbursed_at DESC LIMIT 1", {"customer_id": customer_id})
        loan = None
        payments: list[dict[str, Any]] = []
        if loan_row:
            rate_rows = await database.fetch_all("SELECT effective_from,annual_rate_percent,reason FROM core.loan_rate_history WHERE loan_id=:loan_id ORDER BY effective_from", {"loan_id": loan_row["loan_id"]})
            loan = {
                "loanId": loan_row["loan_id"], "product": "Personal loan", "status": loan_row["status"].title(),
                "currency": loan_row["currency"], "sanctionedAmount": f"{loan_row['sanctioned_amount']:.2f}",
                "outstandingPrincipal": f"{loan_row['outstanding_principal']:.2f}", "annualRatePercent": f"{loan_row['annual_rate_percent']:.2f}",
                "previousRatePercent": f"{rate_rows[-2]['annual_rate_percent']:.2f}" if len(rate_rows) > 1 else f"{loan_row['annual_rate_percent']:.2f}",
                "rateType": loan_row["rate_type"], "emi": f"{loan_row['emi_amount']:.2f}", "previousEmi": f"{loan_row['previous_emi']:.2f}",
                "nextDueDate": local_date(loan_row["next_due_at"]) if loan_row["next_due_at"] else None,
                "tenureRemainingMonths": loan_row["tenure_remaining_months"], "rateEffectiveDate": local_date(rate_rows[-1]["effective_from"]) if rate_rows else None,
                "disbursedAt": loan_row["disbursed_at"].isoformat(),
                "rateHistory": [{"effectiveFrom": local_date(row["effective_from"]), "annualRatePercent": f"{row['annual_rate_percent']:.2f}", "reason": row["reason"]} for row in rate_rows],
            }
            payment_rows = await database.fetch_all(
                "SELECT p.payment_id,p.due_at,p.attempted_at,p.amount,p.status,p.failure_code,f.customer_text,p.channel FROM core.payment p LEFT JOIN core.failure_code_ref f ON f.code=p.failure_code WHERE p.loan_id=:loan_id ORDER BY p.due_at DESC",
                {"loan_id": loan_row["loan_id"]},
            )
            payments = [{
                "paymentId": row["payment_id"], "dueDate": local_date(row["due_at"]),
                "attemptedAt": row["attempted_at"].isoformat() if row["attempted_at"] else None,
                "amount": f"{row['amount']:.2f}", "status": row["status"], "failureCode": row["failure_code"],
                "failureReason": row["customer_text"], "channel": row["channel"],
            } for row in payment_rows]
        card_row = await database.fetch_one("SELECT * FROM core.card_account WHERE customer_id=:customer_id", {"customer_id": customer_id})
        card = None
        if card_row:
            transactions = await database.fetch_all("SELECT transaction_id,occurred_at,merchant,amount,status FROM core.card_transaction WHERE card_id=:card_id ORDER BY occurred_at DESC", {"card_id": card_row["card_id"]})
            card = {
                "cardId": card_row["card_id"], "product": card_row["product_name"], "lastFour": card_row["last_four"],
                "outstanding": f"{card_row['outstanding']:.2f}", "availableLimit": f"{card_row['available_limit']:.2f}",
                "statementBalance": f"{card_row['statement_balance']:.2f}", "dueDate": local_date(card_row["due_at"]),
                "minimumDue": f"{card_row['minimum_due']:.2f}", "rewardPoints": card_row["reward_points"],
                "transactions": [{"transactionId": row["transaction_id"], "date": local_date(row["occurred_at"]), "merchant": row["merchant"], "amount": f"{row['amount']:.2f}", "status": row["status"]} for row in transactions],
            }
        return {"customerId": customer_row["customer_id"], "name": customer_row["full_name"], "mobile": customer_row["mobile_e164"], "kycStatus": customer_row["kyc_status"], "loan": loan, "payments": payments, "lastPayment": payments[0] if payments else None, "card": card}
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Customer not found", "retryable": False}})
    return customer


async def check_loan(customer_id: str, loan_id: str) -> dict[str, Any]:
    customer = await customer_for(customer_id)
    if not customer.get("loan") or customer["loan"]["loanId"] != loan_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Loan not found", "retryable": False}})
    return customer


async def check_card(customer_id: str, card_id: str) -> dict[str, Any]:
    customer = await customer_for(customer_id)
    if not customer.get("card") or customer["card"]["cardId"] != card_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Card not found", "retryable": False}})
    return customer


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "synthetic-enterprise-systems"}


@app.get("/v1/customers/{customer_id}")
async def crm_customer(customer_id: str) -> dict[str, Any]:
    customer = await customer_for(customer_id)
    return {key: customer[key] for key in ("customerId", "name", "mobile", "kycStatus")}


@app.get("/v1/customers/{customer_id}/loans")
async def customer_loans(customer_id: str) -> dict[str, Any]:
    customer = await customer_for(customer_id)
    return {"customerId": customer_id, "loans": [customer["loan"]] if customer.get("loan") else []}


@app.get("/v1/loans/{loan_id}")
async def loan_detail(loan_id: str, customerId: str = Query(...)) -> dict[str, Any]:
    return (await check_loan(customerId, loan_id))["loan"]


@app.get("/v1/loans/{loan_id}/rate-history")
async def rate_history(loan_id: str, customerId: str = Query(...)) -> dict[str, Any]:
    loan = (await check_loan(customerId, loan_id))["loan"]
    return {"loanId": loan_id, "history": loan.get("rateHistory", [{"effectiveFrom": loan["rateEffectiveDate"], "annualRatePercent": loan["annualRatePercent"], "reason": "Current contractual rate"}]), "previousRatePercent": loan["previousRatePercent"]}


@app.get("/v1/loans/{loan_id}/payments")
async def loan_payments(
    loan_id: str,
    customerId: str = Query(...),
    status: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = 100,
) -> dict[str, Any]:
    customer = await check_loan(customerId, loan_id)
    payments = sorted(customer["payments"], key=lambda payment: payment["dueDate"], reverse=True)
    if status:
        payments = [item for item in payments if item["status"] == status.upper()]
    if from_date:
        payments = [item for item in payments if item["dueDate"] >= from_date]
    if to_date:
        payments = [item for item in payments if item["dueDate"] <= to_date]
    return {"loanId": loan_id, "payments": payments[:limit], "page": {"next": None}}


@app.get("/v1/policies/rules")
async def policy_rules(productCode: str = "PERSONAL_LOAN", topic: str = "FORECLOSURE") -> dict[str, Any]:
    if database.is_postgres:
        rows = await database.fetch_all(
            "SELECT rule_id,version,condition,outcome,clause_id,clause_text,effective_from FROM core.policy_rule WHERE product_code=:product AND topic=:topic AND effective_to IS NULL ORDER BY effective_from DESC",
            {"product": productCode, "topic": topic.upper()},
        )
        return {"productCode": productCode, "topic": topic.upper(), "rules": [{
            "ruleId": row["rule_id"], "version": row["version"], "condition": row["condition"], "outcome": row["outcome"],
            "clauseId": row["clause_id"], "clauseText": row["clause_text"], "effectiveFrom": row["effective_from"].isoformat(),
        } for row in rows]}
    rule = POLICIES.get(topic.upper())
    if not rule:
        return {"productCode": productCode, "topic": topic, "rules": []}
    return {"productCode": productCode, "topic": topic, "rules": [{**rule, "version": 1, "effectiveFrom": "2025-04-01T00:00:00+05:30"}]}


@app.get("/v1/cards/{card_id}")
async def card_detail(card_id: str, customerId: str = Query(...)) -> dict[str, Any]:
    return (await check_card(customerId, card_id))["card"]


@app.get("/v1/cards/{card_id}/statement")
async def card_statement(card_id: str, customerId: str = Query(...)) -> dict[str, Any]:
    card = (await check_card(customerId, card_id))["card"]
    return {"cardId": card_id, "statementBalance": card["statementBalance"], "dueDate": card["dueDate"], "minimumDue": card["minimumDue"], "transactions": card["transactions"]}


@app.post("/v1/service-requests", status_code=201)
async def create_service_request(
    body: ServiceRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    customer = await customer_for(body.customerId)
    if body.loanId:
        await check_loan(body.customerId, body.loanId)
    if body.cardId:
        await check_card(body.customerId, body.cardId)
    if body.type == "PAYMENT_DISPUTE" and not any(item["paymentId"] == body.subjectRef and item["status"] == "FAILED" for item in customer["payments"]):
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Payment not found", "retryable": False}})
    if body.type == "CARD_DISPUTE" and body.subjectRef not in {item["transactionId"] for item in customer["card"]["transactions"]}:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Card transaction not found", "retryable": False}})
    now = datetime.now(timezone.utc)
    request_id = f"SR-{uuid.uuid4().hex[:6].upper()}"
    if database.is_postgres:
        existing = await database.fetch_one("SELECT request_id,status,created_at FROM service_requests WHERE idempotency_key=:key", {"key": idempotency_key})
        if existing:
            created_at = existing["created_at"].isoformat() if isinstance(existing["created_at"], datetime) else existing["created_at"]
            return {"requestId": existing["request_id"], "status": existing["status"], "type": body.type, "createdAt": created_at, "replayed": True}
        card_id = body.cardId
        if body.type == "CARD_DISPUTE":
            transaction = await database.fetch_one("SELECT card_id FROM core.card_transaction WHERE transaction_id=:transaction_id", {"transaction_id": body.subjectRef})
            card_id = transaction["card_id"] if transaction else card_id
            if body.cardId and card_id != body.cardId:
                raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Card transaction not found", "retryable": False}})
        request_hash = hashlib.sha256(body.model_dump_json().encode("utf-8")).hexdigest()
        try:
            await database.execute(
                "INSERT INTO core.service_request(request_id,customer_id,loan_id,card_id,type,subject_ref,summary,status,idempotency_key,request_hash,source_correlation_id,expected_resolution_by,created_at,updated_at) VALUES(:request_id,:customer_id,:loan_id,:card_id,:type,:subject_ref,:summary,'OPEN',:key,:request_hash,:correlation,:resolution,:created,:created)",
                {"request_id": request_id, "customer_id": body.customerId, "loan_id": body.loanId, "card_id": card_id,
                 "type": body.type, "subject_ref": body.subjectRef, "summary": body.summary,
                 "key": idempotency_key, "request_hash": request_hash,
                 "correlation": uuid.UUID(body.sourceCorrelationId), "resolution": now + timedelta(days=7), "created": now},
            )
        except IntegrityError:
            # A concurrent retry can win the unique-key race; return the committed original.
            existing = await database.fetch_one("SELECT request_id,status,created_at FROM core.service_request WHERE idempotency_key=:key", {"key": idempotency_key})
            if not existing:
                raise
            request_id = existing["request_id"]
            now = existing["created_at"] if isinstance(existing["created_at"], datetime) else datetime.fromisoformat(existing["created_at"])
            replayed = True
        else:
            await database.execute(
                "INSERT INTO service_requests(request_id,customer_id,workflow_id,request_type,subject_ref,summary,status,idempotency_key,created_at) VALUES(:request_id,:customer_id,:workflow,:type,:subject,:summary,'OPEN',:key,:created)",
                {"request_id": request_id, "customer_id": body.customerId, "workflow": "credit-card" if body.type == "CARD_DISPUTE" else "loan-servicing", "type": body.type, "subject": body.subjectRef, "summary": body.summary, "key": idempotency_key, "created": now},
            )
            replayed = False
    else:
        previous = _IDEMPOTENCY.get(idempotency_key)
        if previous:
            return {**previous, "replayed": True}
        _IDEMPOTENCY[idempotency_key] = {"requestId": request_id, "status": "OPEN", "type": body.type, "createdAt": now.isoformat(), "expectedResolutionBy": (now + timedelta(days=7)).date().isoformat(), "replayed": False}
        replayed = False
    result = {"requestId": request_id, "status": "OPEN", "type": body.type, "createdAt": now.isoformat(), "expectedResolutionBy": (now + timedelta(days=7)).date().isoformat(), "replayed": replayed}
    _REQUESTS[request_id] = {**result, "customerId": body.customerId, "summary": body.summary, "subjectRef": body.subjectRef, "sourceCorrelationId": body.sourceCorrelationId}
    return result


@app.get("/v1/service-requests/{request_id}")
async def get_service_request(request_id: str, customerId: str = Query(...)) -> dict[str, Any]:
    if database.is_postgres:
        result = await database.fetch_one("SELECT request_id,status,type,created_at,expected_resolution_by,summary,subject_ref,source_correlation_id FROM core.service_request WHERE request_id=:id AND customer_id=:customer", {"id": request_id, "customer": customerId})
        if not result:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Service request not found", "retryable": False}})
        created = result["created_at"].isoformat() if isinstance(result["created_at"], datetime) else result["created_at"]
        return {"requestId": result["request_id"], "status": result["status"], "type": result["type"], "createdAt": created, "summary": result["summary"], "subjectRef": result["subject_ref"]}
    result = _REQUESTS.get(request_id)
    if not result or result["customerId"] != customerId:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Service request not found", "retryable": False}})
    return result


@app.get("/admin/failures")
def get_failures() -> dict[str, bool]:
    return _FAILURES


@app.post("/admin/failures/{system}")
def set_failure(system: str, enabled: bool) -> dict[str, Any]:
    key = system.upper()
    if key not in _FAILURES:
        raise HTTPException(status_code=404, detail="Unknown mock system")
    _FAILURES[key] = enabled
    return {"system": key, "enabled": enabled}
