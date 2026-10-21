---
artifact-type: data-design
subject: Enterprise AI Loan Servicing Assistant (POC): mock enterprise systems and conversation platform
version: 1
supersedes: none
generated-by: haptiq-bmad-generate-data-design
source-design:
  - enterprise-voice-agent-system-design-v1.md
  - tool-platform-enterprise-systems-integration-design-v1.md
  - enterprise-voice-agent-journeys-sequence-diagram-v1.md
ticket: none
---

## Data Design: Enterprise AI Loan Servicing Assistant (POC)

Covers two data sets: **A) the mock enterprise systems** (CRM, Loan, Payments, Policy, Service Ops) and **B) the conversation platform** (sessions, turns, tool calls, actions, audit). Access patterns come from the integration design and the sequence diagrams.

**Assumptions to confirm:** the compliance regime is TBD, so classifications are marked as assumptions. National ID numbers (PAN, Aadhaar and the like) are deliberately not stored, as data minimisation.

### 1. Entity Model

**A. Enterprise mock systems (schema `core`)**

| Entity | Purpose | Key attributes | Relationships |
|---|---|---|---|
| `customer` | CRM profile | customer_id, full_name, mobile, email, address, kyc_status | 1:many to loan, service_request (RESTRICT) |
| `loan` | Loan account | loan_id, product_code, status, sanctioned_amount, outstanding_principal, annual_rate_percent, rate_type, emi_amount, next_due_at, tenure_remaining_months | many:1 customer (RESTRICT); 1:many to rate history, schedule, payment (RESTRICT) |
| `loan_rate_history` | Rate changes that explain EMI changes | effective_from, annual_rate_percent, reason | many:1 loan (RESTRICT) |
| `repayment_schedule_item` | Instalment plan | installment_no, due_at, principal, interest, emi | many:1 loan (RESTRICT) |
| `payment` | Payment attempts | payment_id, due_at, attempted_at, amount, status, failure_code, channel | many:1 loan (RESTRICT) |
| `failure_code_ref` | Customer wording for failure codes | code, customer_text | referenced by payment.failure_code |
| `policy_rule` | Versioned business rule plus its clause | rule_id, version, product_code, topic, condition, outcome, clause_id, clause_text, effective_from/to | standalone |
| `service_request` | Dispute, prepayment request, statement | request_id, type, subject_ref, status, idempotency_key, source_correlation_id | many:1 customer, many:1 loan (RESTRICT) |

**B. Conversation platform (schema `platform`)**

| Entity | Purpose | Relationships |
|---|---|---|
| `conversation_session` | One customer conversation | 1:many turn (RESTRICT); customer referenced by ID only (separate system, no cross-DB FK) |
| `turn` | One exchange, with per-stage latency | many:1 session; 1:many tool_call |
| `tool_call` | Every tool call with evidence and latency | many:1 turn (RESTRICT) |
| `action_record` | Lifecycle of each write (prepared, executed, unknown) | many:1 turn (RESTRICT) |
| `audit_log` | Append-only record of events | references session and turn by ID, no FK (immutable, partitioned) |

Ephemeral state (not relational): sessions in flight, confirmation tokens (TTL 5 min), tool cache entries. See section 2.

### 2. Storage Technology Recommendation

| Data need | Technology | Rationale |
|---|---|---|
| Operational data, both schemas | PostgreSQL 16 (separate databases for mocks and platform) | Relational data, exact NUMERIC for money, TIMESTAMPTZ, transactional writes for service requests; boring and well understood. Rejected: document DB (data is relational). |
| Session context, confirmation tokens, tool cache | Redis | Short-lived, fast, TTL native, lets conversation workers stay stateless. Rejected: in-process memory (breaks scaling and failover). |
| Policy clause lookup | Postgres full-text search (GIN on `to_tsvector`) | Clauses are small and cited by ID; rules decide the outcome, so semantic search isn't needed. Rejected: a vector database (ADR-001). |
| Latency evidence and analytics | SQL views over `turn` and `tool_call` | The PRD's latency evidence is percentiles over these tables. Rejected: a separate analytics store (overkill for a POC). |
| Search over conversations | None for the POC | Reviewer lookups use indexed columns (session, customer, time). |

### 3. Schema (PostgreSQL 16)

```sql
-- ===== A. Enterprise mock systems =====
CREATE SCHEMA core;

CREATE TABLE core.customer (
  customer_id  TEXT PRIMARY KEY CHECK (customer_id ~ '^CU-[0-9]+$'),
  full_name    TEXT NOT NULL,
  mobile_e164  TEXT NOT NULL,
  email        TEXT,
  address_line TEXT,
  kyc_status   TEXT NOT NULL CHECK (kyc_status IN ('VERIFIED','PENDING','FAILED')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);

CREATE TABLE core.loan (
  loan_id                 TEXT PRIMARY KEY CHECK (loan_id ~ '^LN-[0-9]+$'),
  customer_id             TEXT NOT NULL REFERENCES core.customer(customer_id) ON DELETE RESTRICT,
  product_code            TEXT NOT NULL,
  status                  TEXT NOT NULL CHECK (status IN ('ACTIVE','CLOSED','FORECLOSED','DELINQUENT')),
  currency                CHAR(3) NOT NULL DEFAULT 'INR',
  sanctioned_amount       NUMERIC(14,2) NOT NULL CHECK (sanctioned_amount > 0),
  outstanding_principal   NUMERIC(14,2) NOT NULL CHECK (outstanding_principal >= 0),
  annual_rate_percent     NUMERIC(5,2)  NOT NULL CHECK (annual_rate_percent >= 0),
  rate_type               TEXT NOT NULL CHECK (rate_type IN ('FIXED','FLOATING')),
  emi_amount              NUMERIC(14,2) NOT NULL CHECK (emi_amount > 0),
  next_due_at             TIMESTAMPTZ,
  tenure_remaining_months INTEGER NOT NULL CHECK (tenure_remaining_months >= 0),
  disbursed_at            TIMESTAMPTZ NOT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at              TIMESTAMPTZ
);
CREATE INDEX loan_customer_idx ON core.loan (customer_id) WHERE deleted_at IS NULL;

CREATE TABLE core.loan_rate_history (
  loan_id             TEXT NOT NULL REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  effective_from      TIMESTAMPTZ NOT NULL,
  annual_rate_percent NUMERIC(5,2) NOT NULL,
  reason              TEXT NOT NULL,
  PRIMARY KEY (loan_id, effective_from)
);

CREATE TABLE core.repayment_schedule_item (
  loan_id             TEXT NOT NULL REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  installment_no      INTEGER NOT NULL CHECK (installment_no > 0),
  due_at              TIMESTAMPTZ NOT NULL,
  principal_component NUMERIC(14,2) NOT NULL,
  interest_component  NUMERIC(14,2) NOT NULL,
  emi_amount          NUMERIC(14,2) NOT NULL,
  status              TEXT NOT NULL CHECK (status IN ('UPCOMING','PAID','MISSED')),
  PRIMARY KEY (loan_id, installment_no)
);

CREATE TABLE core.failure_code_ref (
  code          TEXT PRIMARY KEY,
  customer_text TEXT NOT NULL
);

CREATE TABLE core.payment (
  payment_id   TEXT PRIMARY KEY CHECK (payment_id ~ '^PM-[0-9]+$'),
  loan_id      TEXT NOT NULL REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  due_at       TIMESTAMPTZ NOT NULL,
  attempted_at TIMESTAMPTZ,
  amount       NUMERIC(14,2) NOT NULL CHECK (amount > 0),
  status       TEXT NOT NULL CHECK (status IN ('SUCCESS','FAILED','PENDING')),
  failure_code TEXT REFERENCES core.failure_code_ref(code) ON DELETE RESTRICT,
  channel      TEXT NOT NULL CHECK (channel IN ('AUTO_DEBIT','UPI','CARD','BRANCH')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((status = 'FAILED') = (failure_code IS NOT NULL))
);
CREATE INDEX payment_loan_due_idx    ON core.payment (loan_id, due_at DESC);
CREATE INDEX payment_failed_idx      ON core.payment (loan_id, attempted_at DESC) WHERE status = 'FAILED';

CREATE TABLE core.policy_rule (
  rule_id        TEXT NOT NULL,
  version        INTEGER NOT NULL CHECK (version > 0),
  product_code   TEXT NOT NULL,
  topic          TEXT NOT NULL,
  condition      JSONB NOT NULL,
  outcome        JSONB NOT NULL,
  clause_id      TEXT NOT NULL,
  clause_text    TEXT NOT NULL,
  effective_from TIMESTAMPTZ NOT NULL,
  effective_to   TIMESTAMPTZ,
  PRIMARY KEY (rule_id, version)
);
CREATE INDEX policy_lookup_idx ON core.policy_rule (product_code, topic) WHERE effective_to IS NULL;
CREATE INDEX policy_fts_idx    ON core.policy_rule USING GIN (to_tsvector('english', clause_text));

CREATE TABLE core.service_request (
  request_id             TEXT PRIMARY KEY CHECK (request_id ~ '^SR-[0-9]+$'),
  customer_id            TEXT NOT NULL REFERENCES core.customer(customer_id) ON DELETE RESTRICT,
  loan_id                TEXT NOT NULL REFERENCES core.loan(loan_id) ON DELETE RESTRICT,
  type                   TEXT NOT NULL CHECK (type IN ('PAYMENT_DISPUTE','PREPAYMENT_REQUEST','STATEMENT','TICKET')),
  subject_ref            TEXT,
  summary                TEXT NOT NULL,
  status                 TEXT NOT NULL CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','REJECTED')),
  idempotency_key        TEXT NOT NULL,
  request_hash           TEXT NOT NULL,
  source_correlation_id  UUID NOT NULL,
  expected_resolution_by TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at             TIMESTAMPTZ,
  UNIQUE (customer_id, idempotency_key)
);
CREATE INDEX sr_customer_idx ON core.service_request (customer_id, created_at DESC);

-- ===== B. Conversation platform =====
CREATE SCHEMA platform;

CREATE TABLE platform.conversation_session (
  session_id   UUID PRIMARY KEY,
  customer_ref TEXT,                       -- NULL until verified
  workflow_id  TEXT NOT NULL,
  auth_level   TEXT NOT NULL CHECK (auth_level IN ('ANONYMOUS','VERIFIED')),
  started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at     TIMESTAMPTZ,
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX session_customer_idx ON platform.conversation_session (customer_ref, started_at DESC);

CREATE TABLE platform.turn (
  turn_id             UUID PRIMARY KEY,    -- also the correlation id
  session_id          UUID NOT NULL REFERENCES platform.conversation_session(session_id) ON DELETE RESTRICT,
  seq                 INTEGER NOT NULL,
  channel             TEXT NOT NULL CHECK (channel IN ('TEXT','VOICE')),
  user_text_masked    TEXT,
  answer_text_masked  TEXT,
  stt_ms              INTEGER, llm_ms INTEGER, tools_ms INTEGER, tts_ms INTEGER,
  first_response_ms   INTEGER,
  total_ms            INTEGER,
  verifier_outcome    TEXT CHECK (verifier_outcome IN ('PASSED','REGENERATED','TEMPLATE')),
  escalated           BOOLEAN NOT NULL DEFAULT FALSE,
  barge_in            BOOLEAN NOT NULL DEFAULT FALSE,
  started_at          TIMESTAMPTZ NOT NULL,
  completed_at        TIMESTAMPTZ,
  deleted_at          TIMESTAMPTZ,
  UNIQUE (session_id, seq)
);
CREATE INDEX turn_time_idx ON platform.turn (started_at);

CREATE TABLE platform.tool_call (
  call_id     TEXT NOT NULL,
  turn_id     UUID NOT NULL REFERENCES platform.turn(turn_id) ON DELETE RESTRICT,
  tool_name   TEXT NOT NULL,
  system_name TEXT NOT NULL CHECK (system_name IN ('CRM','LOAN','PAYMENTS','POLICY','SERVICE_OPS')),
  mode        TEXT NOT NULL CHECK (mode IN ('READ','WRITE')),
  status      TEXT NOT NULL CHECK (status IN ('OK','STALE','ERROR')),
  error_code  TEXT,
  retries     SMALLINT NOT NULL DEFAULT 0,
  latency_ms  INTEGER NOT NULL,
  request_id  UUID NOT NULL,
  evidence    JSONB NOT NULL,              -- ids and figures only, no raw PII
  started_at  TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (turn_id, call_id)
);
CREATE INDEX tool_call_system_idx ON platform.tool_call (system_name, started_at);

CREATE TABLE platform.action_record (
  action_id       UUID PRIMARY KEY,
  turn_id         UUID NOT NULL REFERENCES platform.turn(turn_id) ON DELETE RESTRICT,
  token_id        UUID NOT NULL UNIQUE,
  tool_name       TEXT NOT NULL,
  params_digest   TEXT NOT NULL,
  params_masked   JSONB NOT NULL,
  idempotency_key TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('PREPARED','EXECUTED','FAILED','UNKNOWN')),
  reference       TEXT,
  prepared_at     TIMESTAMPTZ NOT NULL,
  executed_at     TIMESTAMPTZ
);

CREATE TABLE platform.audit_log (
  audit_id     BIGINT GENERATED ALWAYS AS IDENTITY,
  occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type   TEXT NOT NULL,
  session_id   UUID,
  turn_id      UUID,
  customer_ref TEXT,
  details      JSONB NOT NULL,             -- masked
  PRIMARY KEY (audit_id, occurred_at)
) PARTITION BY RANGE (occurred_at);
-- append-only: REVOKE UPDATE, DELETE ON platform.audit_log FROM PUBLIC;
-- one partition per month, created ahead of time by a scheduled job.
```

- **Redis keys:** `session:{session_id}` (context, TTL 30 min idle), `confirm:{token_id}` (TTL 300 s, single use), `cache:{tool}:{args_hash}:{customer_ref}` (TTL per tool).

### 4. Access Pattern Coverage

| Access pattern | Query shape | Index used | Expected performance |
|---|---|---|---|
| Loan summary for a customer | `loan WHERE customer_id = ? AND deleted_at IS NULL` | `loan_customer_idx` | Single-digit ms at POC volume |
| Rate history for EMI explanation | `loan_rate_history WHERE loan_id = ? ORDER BY effective_from DESC` | PK | Single-digit ms |
| Repayment schedule window | `repayment_schedule_item WHERE loan_id = ? AND due_at BETWEEN ? AND ?` | PK plus filter | Single-digit ms |
| Failed payments in last 6 months | `payment WHERE loan_id = ? AND status = 'FAILED' AND attempted_at >= ?` | `payment_failed_idx` | Single-digit ms |
| Last payment | `payment WHERE loan_id = ? ORDER BY due_at DESC LIMIT 1` | `payment_loan_due_idx` | Single-digit ms |
| Active rules for a topic | `policy_rule WHERE product_code = ? AND topic = ? AND effective_to IS NULL` | `policy_lookup_idx` | Single-digit ms |
| Clause text search | `to_tsvector(clause_text) @@ plainto_tsquery(?)` | `policy_fts_idx` | Tens of ms at most |
| Idempotent create / replay | `INSERT ... ON CONFLICT (customer_id, idempotency_key)` | unique index | Single-digit ms |
| Service request status | `service_request WHERE request_id = ?` | PK | Single-digit ms |
| Latency percentiles for evidence | `percentile_cont` over `turn` and `tool_call` by window and system | `turn_time_idx`, `tool_call_system_idx` | Seconds over thousands of rows |
| Reviewer: conversations for a customer | `conversation_session WHERE customer_ref = ? ORDER BY started_at DESC` | `session_customer_idx` | Single-digit ms |

Performance figures are expectations at synthetic POC volumes (thousands of rows), not measurements.

**Volume (directional, from PRD statistics):** about 100K interactions per day at full scale means roughly 0.5M turns and about 1M tool calls per day, which is why `audit_log` is partitioned monthly and `turn` and `tool_call` would be partitioned by time in production.

### 5. Privacy & Compliance Classification

Regime TBD, so legal basis and retention are **assumptions for compliance to confirm**. The POC uses synthetic data only.

| Entity / Field | Classification | Legal basis (assumed) | Retention (assumed) |
|---|---|---|---|
| customer.full_name, mobile_e164, email, address_line | PII | Contract performance | Loan life + 7 years, then erase |
| customer.kyc_status | CONFIDENTIAL | Regulatory obligation | Loan life + 7 years |
| loan amounts, rates, EMI, balances, schedule | CONFIDENTIAL | Contract performance | Loan life + 7 years |
| payment amounts, status, failure_code, channel | CONFIDENTIAL | Contract performance | Loan life + 7 years |
| policy_rule | INTERNAL | n/a | Versions retained indefinitely |
| service_request.summary, subject_ref | PII (free text may hold personal data) | Contract performance | 7 years after resolution |
| conversation_session.customer_ref | PII (pseudonymous ID) | Contract performance, consent for voice | 1 year |
| turn.user_text_masked, answer_text_masked | PII (masked, but may still identify) | Consent / legitimate interest (to confirm) | 90 days |
| tool_call.evidence | CONFIDENTIAL (IDs and figures, no raw PII) | Legitimate interest (audit) | 1 year |
| action_record.params_masked | PII (masked) | Contract performance | 7 years (financial action) |
| audit_log.details | PII (masked) | Regulatory obligation / legitimate interest | 7 years |
| Voice audio | PII (biometric-adjacent) | **Not stored by default** | n/a |
| Redis session and token data | PII | Contract performance | TTL only, max 30 min |
| National ID numbers (PAN, Aadhaar) | PII / sensitive | n/a | **Excluded by design** |

### 6. Data Lifecycle

| Entity | Created when | Mutable / immutable | Archival | Deletion | Audit trail |
|---|---|---|---|---|---|
| customer | Onboarding | Contact fields mutable; ID immutable | After loan closure + retention | Soft delete (`deleted_at`), hard erase on lawful request | updated_at, audit events |
| loan | Disbursal | Balances, status, EMI mutable; ID, amounts at sanction immutable | On closure | Soft delete only | rate history and audit |
| loan_rate_history, repayment_schedule_item | Rate change / schedule generation | Immutable (a change creates a new row) | With loan | Retained with loan | Self-auditing |
| payment | Each attempt | Status may change from PENDING; otherwise immutable | With loan | Retained with loan | created_at |
| policy_rule | Policy change | Immutable; new version closes the old via `effective_to` | Never | Never | Version history |
| service_request | Confirmed action | Status and `updated_at` mutable; key and hash immutable | 1 year after resolution | Soft delete | action_record and audit |
| conversation_session, turn, tool_call | During conversation | Immutable after completion | Move to cold storage after 90 days | Soft delete, then purge per retention | Audit events |
| action_record | On prepare | Status moves PREPARED → EXECUTED / FAILED / UNKNOWN | With service_request | Retained | Self-auditing |
| audit_log | Every event | **Append-only, immutable** | Partition detached after retention | Partition drop only at retention end | Is the audit trail |

### Open items

- **Compliance regime and retention periods:** all legal bases and retention figures above are placeholders.
- **Free-text fields:** `summary` and `user_text_masked` may still contain personal data after masking; the masking approach isn't designed yet.
- **Hard-erase path:** soft delete is the default, but a verified erasure request would need a hard-delete procedure for PII that keeps financial audit integrity.
- **Seed data:** the synthetic dataset (customers, a clear EMI-rise case, failed payments, foreclosure cases) isn't designed yet. It determines what the journeys can show.

*Index choices are for POC-sized data and have not been tested at the production volume estimated above.*
