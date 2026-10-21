---
artifact-type: integration-design
subject: Tool Platform to Enterprise Systems (CRM, Loan Management, Payments, Policy Knowledge, Service Operations)
version: 1
supersedes: none
generated-by: h-bmad-generate-integration-design
source-design:
  - enterprise-voice-agent-system-design-v1.md
  - enterprise-voice-agent-prd-v1.md
ticket: none
---

## Integration Design: Tool Platform → Enterprise Systems

All five systems share one contract convention, with per-system operations. Voice-provider and LLM-provider integrations are designed separately.

**Bottom line:** synchronous REST/JSON everywhere, with the platform enforcing timeouts, bounded retries, circuit breakers and idempotent writes. The API style in project context was TBD, so REST with OpenAPI 3.1 is assumed (see section 7).

### 1. Pattern Recommendation

**Sync REST over HTTPS, JSON, OpenAPI 3.1 per system.**

- **Latency:** every read feeds a live turn, so the caller needs the answer now. Parallel REST calls give latency equal to the slowest call.
- **Writes:** the customer needs a reference ID in the same turn, so writes are synchronous with idempotency keys.
- **Coupling:** the Tool Platform is the only caller. The systems know nothing about the AI layer.
- **Rejected: gRPC.** No browser or polyglot need, and REST is simpler to mock and to explain in the review.
- **Rejected: async events/queues for writes.** The reference ID is needed immediately. Request status is polled for now. If push updates are added later, that is an event design, not this one.

### 2. Contract

**Common headers on every call**

| Header | Purpose |
|---|---|
| `Authorization: Bearer <service token>` | Service-to-service identity (platform, not customer) |
| `X-Correlation-Id` | Turn ID, propagated end to end |
| `X-Request-Id` | One per outbound call (retries get new ones) |
| `traceparent` | W3C trace context for OpenTelemetry |
| `Idempotency-Key` | Required on writes only |

**Operations**

| System | Operation | Timeout |
|---|---|---|
| CRM | `GET /v1/customers/{customerId}` | 1.5 s |
| Loan Mgmt | `GET /v1/customers/{customerId}/loans` | 2.5 s |
| Loan Mgmt | `GET /v1/loans/{loanId}` | 2.5 s |
| Loan Mgmt | `GET /v1/loans/{loanId}/schedule?from=&to=` | 2.5 s |
| Loan Mgmt | `GET /v1/loans/{loanId}/rate-history` | 2.5 s |
| Payments | `GET /v1/loans/{loanId}/payments?status=&from=&to=` | 3.5 s |
| Policy | `GET /v1/policies/rules?productCode=&topic=` | 2.0 s |
| Service Ops | `POST /v1/service-requests` (write) | 5.0 s |
| Service Ops | `GET /v1/service-requests/{requestId}` | 2.5 s |

- **Ownership check:** the platform injects `customerId` from the session, never from the model. Backends must also verify the loan belongs to the customer (defence in depth) and return 404 otherwise.
- **Compatibility:** versioned in the path, additive-only changes within a version.
- **Money:** amounts are strings in decimal form with an ISO currency code. No floats.
- **Time:** ISO-8601 with offset (maps to TIMESTAMPTZ).

**Loan response (`GET /v1/loans/{loanId}`)**

```json
{
  "loanId": "LN-10045",
  "customerId": "CU-2291",
  "productCode": "PERSONAL_LOAN",
  "status": "ACTIVE",
  "sanctionedAmount": {"amount": "500000.00", "currency": "INR"},
  "outstandingPrincipal": {"amount": "382450.75", "currency": "INR"},
  "annualRatePercent": "10.75",
  "rateType": "FLOATING",
  "emi": {"amount": "11250.00", "currency": "INR"},
  "nextDueDate": "2026-11-05T00:00:00+05:30",
  "tenureRemainingMonths": 38,
  "disbursedAt": "2024-03-05T10:12:00+05:30"
}
```

**Payments response (`status=FAILED`)**

```json
{
  "loanId": "LN-10045",
  "payments": [
    {
      "paymentId": "PM-88213",
      "dueDate": "2026-05-05T00:00:00+05:30",
      "attemptedAt": "2026-05-05T06:01:12+05:30",
      "amount": {"amount": "11250.00", "currency": "INR"},
      "status": "FAILED",
      "failureCode": "INSUFFICIENT_FUNDS",
      "channel": "AUTO_DEBIT"
    }
  ],
  "page": {"next": null}
}
```

**Policy rules response**

```json
{
  "productCode": "PERSONAL_LOAN",
  "topic": "FORECLOSURE",
  "rules": [
    {
      "ruleId": "PL-FC-001",
      "version": 3,
      "effectiveFrom": "2025-04-01T00:00:00+05:30",
      "condition": {"all": [{"field": "rateType", "op": "eq", "value": "FLOATING"}]},
      "outcome": {"penaltyPercent": "0.00"},
      "clauseId": "PL-TERMS-7.2",
      "clauseText": "No foreclosure charges apply to floating-rate personal loans."
    }
  ]
}
```

**Create service request (`POST /v1/service-requests`)**

```json
{
  "customerId": "CU-2291",
  "loanId": "LN-10045",
  "type": "PAYMENT_DISPUTE",
  "subjectRef": "PM-88213",
  "summary": "Customer disputes failed auto-debit on 2026-05-05",
  "confirmedAt": "2026-10-21T11:02:44+05:30",
  "sourceCorrelationId": "7b1f6c52-4d1c-4a8e-9c5e-0d2f1a7c3b11"
}
```

Response `201 Created` (or `200 OK` on idempotent replay):

```json
{
  "requestId": "SR-550214",
  "status": "OPEN",
  "type": "PAYMENT_DISPUTE",
  "createdAt": "2026-10-21T11:02:45+05:30",
  "expectedResolutionBy": "2026-10-28T00:00:00+05:30"
}
```

**Error envelope (all systems)**

```json
{"error": {"code": "UPSTREAM_TIMEOUT", "message": "...", "retryable": true, "correlationId": "7b1f6c52-..."}}
```

### 3. Error Handling & Retry Strategy

| Error | Classification | Handling |
|---|---|---|
| 400 validation | Non-retryable | Fail fast; log as a platform bug (schema should have caught it) |
| 401 / 403 | Non-retryable | Fail fast; refresh service token once; alert if repeated |
| 404 (incl. ownership mismatch) | Non-retryable | Tell the model "not found"; never reveal whether another customer's record exists |
| 409 idempotency key reuse with a different payload | Non-retryable | Fail the action; alert (indicates a bug) |
| 422 business rule rejection | Non-retryable | Surface the reason to the customer; offer a ticket |
| 429 | Retryable | Honour `Retry-After`, then one retry; else degrade |
| 500 on read | Retryable | One retry with backoff |
| 500 on write | Retryable only with the same idempotency key | One retry, same key |
| 502 / 503 / 504 | Retryable | One retry, then circuit breaker accounting |
| Timeout on read | Retryable | One retry within the total budget, else say the data is unavailable |
| Timeout on write | Retryable with the same key; **outcome unknown** until confirmed | Retry once with the same key; if still unknown, `GET` request status before telling the customer anything |
| Connection reset / DNS | Retryable | One retry |
| Response violates schema | Non-retryable | Fail the tool call, alert, never pass to the model |

- **Retry policy:** max 2 attempts (one retry). Exponential backoff with full jitter, base 100 ms, cap 400 ms. Total time for a call must not exceed 1.5 × its timeout.
- **Circuit breaker (per system):** opens at ≥ 50% failures over a 30 s window with at least 10 calls. Half-open after 15 s with 3 probes. While open, calls fail fast and the answer says that system is unavailable.
- **Stale cache:** reads may serve cached data only if it is marked stale in the evidence and was fetched within the allowed age (policy and terms yes, balances and payments no).
- **Async DLQ / schema evolution:** not applicable, since this is a synchronous design.

### 4. Data Mapping (source → canonical tool output)

| Source field | Target field | Transformation | Notes |
|---|---|---|---|
| `loan.annualRatePercent` | `rate_percent` | string → Decimal | Never float |
| `loan.outstandingPrincipal.amount` | `outstanding_principal` | string → Decimal | Currency carried alongside |
| `loan.emi.amount` | `emi_amount` | string → Decimal | |
| `loan.nextDueDate` | `next_due_at` | ISO-8601 → tz-aware datetime | |
| `payment.status` | `payment_status` | enum pass-through | Unknown values rejected |
| `payment.failureCode` | `failure_reason` | code → customer text via policy mapping | Code kept in evidence |
| `rule.ruleId`, `clauseId` | `evidence.rule_id`, `evidence.clause_id` | as is | Required for policy statements (closes a gap in the system design) |
| `request.requestId` | `service_request.reference` | as is | Shown to the customer |
| `response.correlationId` | `evidence.correlation_id` | as is | Links evidence to the audit log |

### 5. Idempotency & Correlation

- **Idempotency key:** a UUIDv5 derived from session ID, tool name, a hash of the canonical arguments and the confirmation-token ID. A double click, a retry or a repeated confirmation therefore produces the same key.
- **Deduplication window:** 24 hours at Service Ops. A replay returns the original response with `200 OK`.
- **Correlation:** `X-Correlation-Id` is the turn ID, set by the orchestrator and propagated on every call. Each outbound call also gets its own `X-Request-Id`. `traceparent` carries the OpenTelemetry trace. The backend stores `sourceCorrelationId` on every service request and echoes the ID in errors.

### 6. Monitoring & Alerting

- **Metrics (per system and operation):** request count, error rate by class, latency p50, p95 and p99, retry count, timeout count, circuit state, idempotent-replay count, cache hit ratio and schema-violation count.
- **Alerts:**
  - Error rate above 5% for 5 minutes (excluding runs with the failure-injection switch on).
  - p95 above 80% of the timeout.
  - A circuit open for more than 2 minutes.
  - Any write with outcome-unknown not resolved by status check.
  - Any schema violation.
- **Dashboards:** per-system latency and error panels, because the demo and the latency evidence deliverable both need them.

### 7. Open Items

- **API style:** REST with OpenAPI 3.1 assumed because `api_style` is TBD in project context. Confirm or change.
- **Mock latency and failure profile:** assumed a range of about 100 ms to 3 s and 5 to 10% failures per system. Agree the exact profile so timeouts and alerts match it.
- **Service-to-service auth:** a bearer token is assumed for the POC. Production auth is not specified.
- **Which write actions are in scope:** dispute plus prepayment request are assumed. The prepayment request would reuse `POST /v1/service-requests` with a different `type` and an amount field.

*Timeout and retry numbers are starting values, not validated against measured latency. The OpenAPI conversion script was not used because no spec exists yet.*
