---
artifact-type: component-design
subject: Tool Platform (ToolGateway), the reusable capability from ADR-003
version: 1
supersedes: none
generated-by: h-bmad-generate-component-design
source-design:
  - enterprise-voice-agent-system-design-v1.md
  - tool-platform-enterprise-systems-integration-design-v1.md
  - ADR-003-declarative-tool-platform-as-reusable-capability.md
ticket: none
---

## Component Design: Tool Platform

**SRP check:** the platform's responsibilities (registry, validation, authorisation, confirmation, resilience, caching, audit) are related but too many for one class. They are split into collaborating components behind one facade, **`ToolGateway`**. The facade is designed in full below. The others are specified at interface level in section 3.

**Parent system:** Enterprise AI Loan Servicing Assistant, Conversation Service
**Tech stack:** Python 3.12, async, Pydantic v2, httpx, Redis, Postgres (no stack was set in project context, so this follows the system design)

### 1. Responsibilities

**Is responsible for:**

- Exposing the tools a workflow may use, with argument schemas the model can see.
- Validating arguments and rejecting any model-supplied identity field (`customer_id`).
- Injecting `customer_id` from the trusted turn context.
- Enforcing scope, read versus write, and the confirmation step for writes.
- Executing calls in parallel with per-system timeouts, bounded retries and circuit breakers (per the integration design).
- Read-through caching for allowed tools, with stale flags.
- Mapping provider responses into canonical, typed tool outputs and rejecting schema violations.
- Producing an evidence record for every call.
- Writing an audit record for every call and action.

**Is NOT responsible for (boundary):**

- Deciding which tool to call or interpreting results (Orchestrator).
- Financial arithmetic (Calculator) or evaluating policy rules (Rules Engine).
- Verifying the customer's identity or issuing session tokens (Session and Auth).
- Business logic inside the enterprise systems.
- Composing answers or any customer-facing wording except the neutral action summary.

### 2. Interface Definition

**Shared types**

```python
JsonObject = dict[str, "JsonValue"]            # raw model arguments, validated before use
class TurnContext(BaseModel):
    session_id: UUID; turn_id: UUID            # turn_id is the correlation ID
    customer_id: str                           # trusted, from the session, never from the model
    workflow_id: str
    scopes: frozenset[str]
    deadline: datetime                         # tz-aware; calls must finish before it
class ToolCall(BaseModel):
    call_id: str; tool_name: str; arguments: JsonObject
class EvidenceRecord(BaseModel):
    system: Literal["CRM","LOAN","PAYMENTS","POLICY","SERVICE_OPS"]
    operation: str; request_id: UUID; correlation_id: UUID
    fetched_at: datetime; latency_ms: int; stale: bool; source_ids: list[str]
class ToolError(BaseModel):
    code: ToolErrorCode; retryable: bool; message: str   # message safe to show the model
class ToolResult(BaseModel):
    call_id: str
    status: Literal["OK","STALE","ERROR"]
    data: ToolOutput | None                    # per-tool Pydantic model, never a dict
    evidence: EvidenceRecord | None
    error: ToolError | None
```

#### Inbound: `list_tools(workflow_id: str) -> list[ToolSpecView]`

- **Input:** `workflow_id` (str, required, must exist in the registry).
- **Returns:** name, description and JSON Schema of arguments for each allowed tool. `customer_id` is never included.
- **Errors:** `WorkflowNotFound`, non-retryable, unknown workflow.
- **Side effects:** none.

#### Inbound: `execute_many(calls: list[ToolCall], ctx: TurnContext) -> list[ToolResult]`

- **Input:** `calls` (1 to 8 items, required; each `tool_name` must be a read tool in the workflow allowlist), `ctx` (required).
- **Returns:** one `ToolResult` per call, in the same order. Per-call failures are returned as `ERROR` results, not raised, so one failed system doesn't lose the others.
- **Errors (raised, for the whole batch):** `TooManyCalls` (non-retryable, more than 8), `DeadlineExceeded` (retryable, `ctx.deadline` passed before dispatch).
- **Side effects:** parallel outbound calls, cache reads and writes, audit records, telemetry events.

#### Inbound: `prepare_action(call: ToolCall, ctx: TurnContext) -> ConfirmationRequest`

- **Input:** `call.tool_name` must be a write tool; `call.arguments` validated against its schema.
- **Returns:** `ConfirmationRequest(token_id: UUID, action_summary: str, params_digest: str, expires_at: datetime)`. Token TTL is 5 minutes.
- **Errors:** `ToolNotAllowed`, `ArgumentValidationError`, `ScopeDenied`, `OwnershipDenied` (all non-retryable).
- **Side effects:** stores the token in Redis bound to session, customer and `params_digest`; audit record `ACTION_PREPARED`. Nothing is sent to any enterprise system.

#### Inbound: `confirm_action(token_id: UUID, ctx: TurnContext) -> ToolResult`

- **Input:** `token_id` issued by this session and by the same customer.
- **Returns:** `ToolResult` whose `data` is the created record (for example `ServiceRequestCreated(reference, status, created_at)`).
- **Errors:** `ConfirmationExpired`, `ConfirmationReused`, `ConfirmationMismatch` (non-retryable); `OutcomeUnknown` (retryable, via a status check); `UpstreamUnavailable` (retryable); `AuditWriteFailure` (fatal for this write, nothing sent if the audit could not be recorded).
- **Side effects:** single-use token consumed, write sent with the derived idempotency key, audit `ACTION_EXECUTED`.
- **Only the UI's explicit confirm action may call this.** The model cannot.

#### Errors common to execute and prepare

| Error | Classification | When raised |
|---|---|---|
| `ToolNotAllowed` | non-retryable | Tool not in the workflow allowlist |
| `ArgumentValidationError` | non-retryable | Arguments fail schema, or the model supplied `customer_id` |
| `ScopeDenied` | non-retryable | Context scopes lack the tool's required scope |
| `OwnershipDenied` | non-retryable | Backend 404 or 403 on a resource that is not the customer's |
| `UpstreamTimeout` | retryable | Timeout after the allowed retry |
| `UpstreamUnavailable` | retryable | 5xx after retry, or circuit open |
| `UpstreamRateLimited` | retryable | 429 after the allowed retry |
| `BusinessRuleRejected` | non-retryable | 422 from a backend |
| `SchemaViolation` | non-retryable | Response fails the expected schema |
| `RegistryConfigInvalid` | fatal | Tool or workflow config fails validation at startup |

#### Events emitted

- `ToolCallCompleted(tool: str, system: str, status: str, latency_ms: int, correlation_id: UUID)` after every call.
- `CircuitStateChanged(system: str, from_state: str, to_state: str, at: datetime)` when a breaker changes state.
- `ActionPrepared(tool: str, token_id: UUID, correlation_id: UUID)` and `ActionExecuted(tool: str, reference: str, correlation_id: UUID)`.
- Published to the telemetry and audit sinks, not to other business components.

#### Outbound: enterprise systems

- **Sends:** the integration design's contract: path parameters from validated arguments plus `customerId` from the context; headers `Authorization`, `X-Correlation-Id`, `X-Request-Id`, `traceparent`, and `Idempotency-Key` on writes.
- **On success:** validate the response against the tool's output model, build evidence, cache if allowed.
- **On failure:** classify per the integration design, retry once if retryable, return a typed error.

### 3. Internal Structure

```
ToolGateway (facade: the four operations above)
 ├─ ToolRegistry            loads and validates tool and workflow YAML, serves allowlists
 ├─ ArgumentValidator       Pydantic validation, rejects identity fields, injects customer_id
 ├─ AuthzGuard              scope check and read/write policy per tool
 ├─ ConfirmationGate        issues and consumes single-use tokens, derives idempotency key
 ├─ ResilientClient         per-system timeout, one jittered retry, circuit breaker (wraps httpx)
 ├─ ReadThroughCache        TTL cache keyed by tool, args and customer; marks stale hits
 ├─ ResponseMapper          provider response → canonical ToolOutput, raises SchemaViolation
 ├─ EvidenceBuilder         builds EvidenceRecord from call metadata
 └─ AuditSink               append-only records (Postgres), masked PII
```

**Tool definition example (declarative, one file per tool)**

```yaml
name: get_failed_payments
system: PAYMENTS
mode: read
operation: GET /v1/loans/{loanId}/payments
scope: payments:read
timeout_ms: 3500
cache_ttl_s: 0
arguments: {loanId: str, from: datetime, to: datetime}
output_model: PaymentList
```

- **A new workflow** is a workflow file listing allowed tools and prompt references, plus any new tool files. No gateway code changes. That is the reuse the second workflow must demonstrate.

### 4. Dependency List

| Dependency | Purpose | Required / Optional | Failure impact |
|---|---|---|---|
| httpx (async) | Outbound HTTP with timeouts | Required | No backend access; every tool fails |
| Pydantic v2 | Argument and output validation | Required | Unsafe to run without it; fail closed |
| Redis | Confirmation tokens, cache | Required for writes; optional for cache | No writes possible; reads continue uncached |
| Postgres | Audit records | Required for writes; reads buffer and warn | Writes refused (fatal); reads degrade |
| OpenTelemetry SDK | Traces and metrics | Optional | Loss of observability only |
| Small in-house circuit breaker | Per-system breaker | Required | Without it, slow systems stall turns |
| PyYAML | Load tool definitions | Required | Platform cannot start (`RegistryConfigInvalid`) |

### 5. Testability

- **Unit-test seams (≥3):**
  1. `HttpTransport` (inject an httpx mock transport to simulate any status, latency or malformed body).
  2. `Clock` (control timeouts, token TTL and breaker windows).
  3. `TokenStore` (in-memory fake for confirmation tokens).
  4. `Cache` (in-memory fake, to test stale handling).
  5. `AuditSink` (capture records, simulate write failure).
  6. `ToolRegistry` source (feed definitions from test fixtures).
  7. `JitterSource` (deterministic retry delays).
- **Integration boundaries:** the mock enterprise service (run for real in tests), Redis and Postgres test instances.
- **Key scenarios:**
  - **Happy path:** J1 batch (loan, payments and policy in parallel) returns three OK results with evidence, latency near the slowest call.
  - **Error 1:** Payments times out, retried once, still fails: that result is `ERROR/UpstreamTimeout`, the others still return.
  - **Error 2:** the model supplies a `customer_id` or a loan owned by another customer: rejected or `OwnershipDenied`, nothing leaked.
  - **Error 3:** double confirm and retry on a write: one record created, replay returns the same reference; a timeout on the write triggers a status check before reporting.
  - **Also:** circuit opens after repeated failures and fails fast; schema-violating response never reaches the model; audit failure blocks a write.

### 6. Open questions

- **Breaker state:** per worker or shared in Redis? Per worker is simpler and good enough for the POC, but gives uneven behaviour at scale. Assumed per worker.
- **Cache keys and TTLs:** assumed policy and terms 10 minutes, balances and payments none. Confirm.
- **Batch limit:** 8 parallel calls per turn assumed. Confirm against the heaviest journey.
- **Action summary text:** generated by the gateway from the tool definition, not by the model, so the customer confirms what will really execute. Confirm this wording is acceptable to product.
- **Token TTL:** 5 minutes assumed.
- **Hot reload of tool config:** needed for the interview-time change request? Not designed; restart-on-change is assumed.

*No code was written and no tests were run. Library choices have not been checked against the final Python version.*
