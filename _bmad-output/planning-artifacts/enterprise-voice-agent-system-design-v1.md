---
artifact-type: system-design
subject: Enterprise AI Loan Servicing Assistant (POC)
version: 1
supersedes: none
generated-by: haptiq-bmad-generate-system-design
source-design:
  - enterprise-voice-agent-prd-v1.md
ticket: none
---

## System Design: Enterprise AI Loan Servicing Assistant (POC)

Designed against PRD v1.0 (`enterprise-voice-agent-prd-v1.md`) and validated against these NFR targets:

- Text first token ≤ 2 s.
- Voice first audio ≤ 1.5 s, barge-in ≤ 300 ms.
- 1,000 concurrent conversations as the design direction.
- Availability 99.5% for the POC, 99.9% as the production direction.

**Trade-off up front:** correctness and explainability win over model freedom. The model plans and explains, while typed tools, a deterministic calculator and a rules engine produce every number.

### 1. Architecture Overview

- **Style:** a modular monolith for the conversation tier plus a separate mock-enterprise service. This is a small team on a 3-day clock, so the design avoids a microservice zoo but keeps clean seams to split later.
- **Core idea:** a **tool platform** sits between the model and every enterprise system. It is the reusable capability (PRD FR-20).
- **Same brain for text and voice:** both channels feed one orchestrator, so capabilities and context are shared by construction.

```
 Browser (React)
   ├─ chat UI + account view + evidence panel
   └─ mic/speaker ── WebSocket (audio frames + events)
           │
 ┌─────────▼───────────────────────────────────────────────┐
 │ Conversation Service (FastAPI, stateless, async)        │
 │  Session/Auth ─ Voice Gateway (VAD, STT, TTS, barge-in) │
 │  Orchestrator: plan → parallel tools → verify → compose │
 │  Tool Platform: registry, resilience, authz, audit      │
 │  Calculator (Decimal) · Rules Engine · Evidence builder │
 └───┬───────────┬───────────────┬──────────────┬──────────┘
     │           │               │              │
   Redis     Postgres        LLM provider    STT / TTS providers
 (session,   (audit, mock    (adapter)       (streaming)
  cache)      data)
     │
 ┌───▼──────────────── Mock Enterprise Services ──────────────┐
 │ CRM · Loan Mgmt · Payments · Policy Knowledge · Service Ops│
 │ (configurable latency, injected failures)                  │
 └────────────────────────────────────────────────────────────┘
```

- **Alternatives rejected:**
  - Pure retrieval chatbot: cannot compute or act (Problem A).
  - Free-form text-to-SQL: unsafe and unverifiable.
  - Per-use-case microservices: slower to build and goes against Problem D.

### 2. Component Responsibilities

- **Web UI**: customer-facing text, voice, account view and evidence panel.
  - Does: render streaming answers, capture the mic, play audio, show progress and the confirmation card for actions.
  - Does NOT: hold business logic, compute figures, or decide what is authorised.
- **Session and Auth**: verifies the customer and binds the session.
  - Does: mock OTP, issue a short-lived token carrying `customer_id`, enforce timeouts.
  - Does NOT: store credentials or trust identity from model output.
- **Voice Gateway**: audio in, audio out, turn-taking.
  - Does: voice activity detection, streaming STT, sentence-level streaming TTS, barge-in cancellation, filler cues.
  - Does NOT: understand intent or call enterprise systems.
- **Orchestrator**: runs one conversational turn.
  - Does: classify the turn, call the model to plan tool calls, run tools in parallel, assemble evidence, verify numbers, compose the answer, keep context.
  - Does NOT: do arithmetic, talk to backends directly, or execute writes without a confirmation.
- **Tool Platform (reusable)**: the single door to all systems.
  - Does: load declarative tool definitions, validate args, inject `customer_id` from the session, apply timeout, retry, circuit breaker and cache, enforce confirmation for writes, write audit.
  - Does NOT: contain workflow-specific logic.
- **Calculator**: deterministic finance maths on Decimal (EMI, prepayment, interest saved, tenure change).
  - Does NOT: fetch data or interpret policy.
- **Rules Engine**: evaluates policy rules as data (foreclosure penalty, prepayment limits).
  - Does: return an outcome plus the clause that produced it.
  - Does NOT: invent rules absent from the policy store.
- **Mock Enterprise Services**: CRM, Loan Management, Payments, Policy, Service Operations.
  - Does: realistic data and behaviour with configurable latency and failures.
  - Does NOT: know anything about the AI layer.
- **Audit and Telemetry**: append-only turn, tool and action records plus traces.
  - Does NOT: store raw audio or unmasked PII.

### 3. Data Flow

- **Synchronous text path:** UI → WebSocket → Orchestrator → model plans tools → Tool Platform calls systems in parallel → Calculator and Rules Engine on the results → Evidence object → answer composed from the evidence only → numbers verified against evidence → streamed to UI with an evidence record.
- **Voice path:** mic → streaming STT → turn manager → same Orchestrator → text streamed sentence by sentence into TTS → audio out.
  - **Barge-in:** speech detected while TTS plays → cancel TTS and the generation within 300 ms. In-flight reads finish and populate the cache.
  - **Slow tools:** if tools exceed about 700 ms, play a short progress phrase.
- **Journey data flows:**
  - J1: Loan (schedule, rate history), Payments (recent EMI), Policy (rate-reset and prepayment rules), then Calculator.
  - J2: the same, plus session context carrying the loan and the last intent.
  - J3: Payments (failed list), Policy (failure reasons), then Service Ops (dispute) with a confirmation.
- **Asynchronous paths:** audit and metrics are written off the request path. Service-request status updates are polled, with push to the UI as a later step.
- **External:** LLM, STT and TTS providers. Providers are behind adapters.

### 4. Technology Choices

- **Choice:** Python 3.12 + FastAPI (async) — **Rationale:** best ecosystem for LLM, audio and numerics, fast to build, solid async WebSockets.
  - **Rejected alternatives:** Node/TypeScript (weaker numeric libraries), Java/Spring (slower to iterate for 3 days).
  - **Trade-offs:** Python concurrency needs care at scale (async I/O, multiple workers).
- **Choice:** React + Vite UI — **Rationale:** quick build of a polished interface, easy audio handling.
  - **Rejected alternatives:** server-rendered pages, which are awkward for live audio.
  - **Trade-offs:** a client-side bundle to maintain.
- **Choice:** WebSocket for audio and events — **Rationale:** simple, bidirectional, enough for a POC.
  - **Rejected alternatives:** WebRTC (better network resilience, but much more setup). Listed as the production upgrade.
  - **Trade-offs:** less resilient on poor networks.
- **Choice:** Cascaded STT → LLM → TTS — **Rationale:** the same tool-using model serves text and voice, and gives full control over barge-in, filler cues and tools.
  - **Rejected alternatives:** speech-to-speech realtime model (lower latency but weaker control over tools and verification).
  - **Trade-offs:** more latency stages to tune.
- **Choice:** Typed tool calling over free-form SQL or pure RAG — **Rationale:** verifiable inputs and outputs, authorisation in code.
  - **Rejected alternatives:** text-to-SQL (injection and accuracy risk), embeddings-only retrieval (the problem the customer is leaving).
  - **Trade-offs:** each capability needs a tool definition.
- **Choice:** Hybrid policy store (structured rules plus clause text) — **Rationale:** rules decide, clause text explains and cites.
  - **Rejected alternatives:** vector search alone (cannot guarantee a rule was applied).
  - **Trade-offs:** rules must be authored and kept in step with policy documents.
- **Choice:** Python `Decimal` for money — **Rationale:** exact arithmetic.
  - **Rejected alternatives:** float and model arithmetic.
  - **Trade-offs:** slightly more verbose code.
- **Choice:** Postgres 16 (NUMERIC for money, TIMESTAMPTZ for times) for mock data and audit — **Rationale:** boring and reliable.
  - **Rejected alternatives:** a document DB, because the data is relational.
  - **Trade-offs:** schema migrations to manage.
- **Choice:** Redis for session state and read-through cache — **Rationale:** stateless workers, shared context.
  - **Rejected alternatives:** in-process memory, which breaks scaling and failover.
  - **Trade-offs:** one more component to run.
- **Choice:** LLM, STT and TTS via provider adapters — **Rationale:** swap providers without touching the orchestrator; provider choice stays open (see section 9).
  - **Rejected alternatives:** hard-wiring one vendor SDK.
  - **Trade-offs:** adapter lowest-common-denominator features.
- **Choice:** OpenTelemetry + Prometheus/Grafana — **Rationale:** vendor-neutral latency evidence (PRD deliverable 4).
  - **Rejected alternatives:** a single vendor APM.
  - **Trade-offs:** more setup than a hosted APM.
- **Choice:** Docker Compose for the POC, Kubernetes as the scale path — **Rationale:** reproducible local run.
  - **Rejected alternatives:** Kubernetes from day one (overhead for a 3-day build).
  - **Trade-offs:** scale path is documented, not demonstrated.

### 5. Scalability & Performance

- **Voice latency budget (design budget, not a measurement):**

  | Stage | Budget |
  |---|---|
  | End-of-speech detection | ~300 ms |
  | Final STT | ~150 ms |
  | Model first token (fast path) | ~500 ms |
  | First sentence to TTS audio | ~250 ms |
  | **Total to first audio** | **~1.2 s** (meets ≤ 1.5 s) |

- **Tool-heavy queries:** tools run in parallel, so latency is the slowest call, not the sum. Mocks run at 100 ms to 3 s. A progress phrase covers the wait, so first audio is still fast and the answer follows.
- **Text:** token streaming gives first token under 2 s. Full answers for multi-system queries target under 6 s.
- **Fast and deep paths:** simple lookups use a small model with a single tool. Multi-step questions use a stronger model.
- **Caching:** short-TTL cache for stable reads (loan terms, policy), none for balances and payments beyond a few seconds.
- **1,000 concurrent conversations (design direction):**
  - Conversation workers are stateless. Sessions live in Redis, and WebSocket connections are spread by a load balancer.
  - Audio bandwidth is small (about 4 MB/s for 1,000 streams).
  - **Bottleneck 1:** model throughput. If every conversation were active, that could mean on the order of hundreds of model calls per second. This needs provider quota and prompt caching, and is a stated assumption to confirm.
  - **Bottleneck 2:** STT and TTS stream concurrency limits.
  - **Bottleneck 3:** backend connection pools, mitigated by per-system bulkheads.
  - **Load shedding:** queue or politely defer new sessions beyond capacity rather than degrade everyone.
- **Evidence plan:** per-stage timing in every turn, and a small load test to find the knee of the curve.

### 6. Failure Modes & Mitigations

| Failure Scenario | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Payments or Loan service times out or errors (dependency) | High (injected 5 to 10%) | Missing evidence for an answer | Timeout, one retry with backoff, circuit breaker, serve cached data only when marked stale, otherwise say so and offer a ticket. Never invent data. |
| LLM provider slow or down (dependency) | Medium | Turn fails | Timeout, fall back to a second model or provider adapter, show a graceful message, keep the account view working. |
| STT or TTS stream drops (infra) | Medium | Voice breaks | Detect and fall back to text with the transcript preserved; auto-reconnect. |
| Model states a figure not in evidence (data) | Medium | Wrong financial answer | Verifier checks every number in the draft against evidence, regenerates or falls back to the evidence template. Calculator is the only source of money figures. |
| Duplicate write after a retry or double confirm (data) | Medium | Duplicate dispute or prepayment | Idempotency key per action, confirmation token single-use, server-side dedupe. |
| Traffic spike beyond provider quotas (traffic) | Medium | Latency climbs, errors | Admission control, queueing with an honest wait message, per-tenant rate limits, autoscale workers. |
| Wrong tool or policy config deployed (config) | Medium | Wrong answers or blocked actions | Config validated against schema at startup, versioned and feature-flagged, one-step rollback. |
| Prompt injection via user input or tool output (security) | Medium | Data leak or rogue action | Tool outputs treated as data, `customer_id` injected by platform, writes need a server-issued confirmation, output filter. |
| Session state loss (Redis restart) | Low | Context lost | Persist the minimal context, ask a brief re-confirmation, no silent re-assumption. |

### 7. Security Considerations

- **Authentication:** mock OTP at session start for the POC. Production would use the company's identity provider. The session token carries `customer_id`.
- **Authorisation (key control):**
  - The model never supplies `customer_id`. The Tool Platform injects it from the session, so cross-customer access is impossible by construction.
  - Each tool declares required scope and whether it is read or write.
- **Write actions:** the UI shows a confirmation card with the exact action and amount. The server issues a single-use confirmation token. The model cannot self-confirm.
- **Data classification:**
  - PII: name, phone, address, identifiers.
  - Financial: balances, schedules, payment history.
  - Sensitive: session tokens, OTPs.
  - Voice audio: not stored by default; transcripts masked in logs.
- **Encryption:** TLS in transit. Encryption at rest for Postgres and Redis in any hosted environment. Secrets in a secret store.
- **Prompt-injection defences:** delimit and label tool output as data, restrict tools by workflow, validate arguments with schemas, verify numbers.
- **Audit:** every turn, tool call and action, with customer, time (TIMESTAMPTZ) and outcome.
- **Compliance:** unconfirmed. The ₹ context implies India (RBI, DPDP): consent for voice, data minimisation, retention, localisation. The POC uses synthetic data only, which limits exposure, but hosted model and voice providers must be vetted before real data.

### 8. Operational Concerns

- **Metrics and alerts:**
  - Turn latency p50, p95 and p99, by stage (STT, model, tools, TTS) for text and voice.
  - Tool error rate and circuit state per system.
  - Verifier rejection rate (a proxy for hallucination).
  - Escalation and fallback rate.
  - Barge-in count and cancel latency.
  - Provider error and quota usage.
  - Alert on p95 over target, a tool circuit open for more than 2 minutes, and a rising verifier rejection rate.
- **Deployment:** Docker Compose for the POC and demo. Production direction: Kubernetes with a canary release (5% then 50% then 100%).
- **Rollback:** previous image tag, plus a feature flag per workflow and tool. Tool and policy config are versioned, so a bad config is reverted without a redeploy.
- **Demo resilience:** a failure-injection switch to show graceful degradation live, and a recorded fallback path if the network fails.
- **Runbook pointers:** provider outage (switch adapter), backend circuit open (explain to customer, ticket), latency regression (check stage breakdown).

### 9. Open Questions

| # | Question | Proposed owner |
|---|---|---|
| 1 | Which LLM, STT and TTS providers, and do accounts and quota exist? Needed for the 1,000-concurrency claim. | Project lead |
| 2 | Compliance regime (RBI/DPDP assumed) and whether hosted models are acceptable even with synthetic data. | Compliance / sponsor |
| 3 | Second workflow: credit cards assumed (statement query and dispute). | Product |
| 4 | Which two write actions: dispute and prepayment request assumed. | Product |
| 5 | Load test or capacity-plan argument for 1,000 concurrent? | Sponsor |
| 6 | Languages for voice (English assumed). | Product |
| 7 | Availability target for production (99.9% is an assumption). | Sponsor |
| 8 | The interview change request is unknown, so keep tools and rules config-driven. | Design/Eng |

### Alignment notes (added after the PRD check)

Open gaps against PRD v1.0, to close in a refinement pass (OSD):

1. **Verifier scope:** it checks numbers only. Require every policy statement to carry a clause ID from the rules engine, and check that.
2. **FR-9 human escalation:** add a named human-handoff component (stub acceptable for the POC).
3. **FR-22 effort measurement:** plan a measured build log for adding the second workflow.
4. **FR-17 / FR-21:** second workflow and write actions are still assumptions.
5. **1,000 concurrency:** argued by design only; add a small load test.
6. **Interview-time change:** specify how a rule or tool change is made quickly and safely.

*Latency and quota figures are design budgets, not measurements. Model, STT and TTS providers are intentionally left open.*
