## ADR-003: Make a declarative tool platform the reusable capability

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Amar Gharat (project lead), Design Architect (Amol)

### Context
- PRD problem D and challenge 5: every new workflow takes weeks because integrations, business logic, UI and monitoring are rebuilt each time. The customer plans credit cards, insurance and collections next.
- The requirement asks for at least one reusable capability and a second workflow built without rebuilding it.
- Backends have different latencies and fail intermittently (problem C); every action needs authorisation and audit.

### Decision
Build one tool platform where each tool is a declarative definition (schema, system, scope, read or write, timeout, retry, cache, confirmation) and a shared layer applies resilience, authorisation, confirmation, idempotency and audit; workflows only choose which tools they may use.

### Options considered

#### Option A: Declarative tool registry plus shared execution layer (chosen)
- **Pros:** a second workflow (credit cards) needs new tool definitions and prompt and rules config, not new plumbing; resilience, authz and audit are written once; adding a tool during the interview change request is a config change.
- **Cons:** the abstraction must be designed carefully in a short build; unusual integrations may not fit the schema.
- **Risks:** over-engineering the registry; mitigated by building only the fields the three journeys and the second workflow use.

#### Option B: Hand-coded integrations per workflow
- **Pros:** fastest for the first workflow; no abstraction to design.
- **Cons:** this is the customer's current problem D; resilience and audit are duplicated; the second workflow would cost almost as much as the first.
- **Risks:** inconsistent security and error handling across workflows.

#### Option C: Adopt a third-party agent framework or MCP servers wholesale
- **Pros:** existing tooling and community.
- **Cons:** weaker control over customer_id injection, confirmation tokens and the verifier; added dependency and learning curve in 3 days.
- **Risks:** framework behaviour that is hard to explain in the architecture review.

### Rationale
Criteria: demonstrable reuse (second workflow, measured effort), consistent security, and control. Option A is the smallest design that shows reuse. A standard such as MCP can be added later as an adapter at the edge of the registry.

### Consequences

**Positive:**
- Second-workflow effort can be measured and presented as the evidence for reuse.
- One place to enforce authorisation, confirmation and audit.

**Negative:**
- The registry's schema becomes a contract; changes need versioning.
- Additional up-front work on day 1.

**Monitoring:**
- Effort to add the second workflow (hours, new lines of code versus reused) in the build log.
- Share of tools needing custom code outside the registry; a high share means the schema is too narrow.
- Per-tool error rate, latency and circuit state.

### Linked ADRs
- ADR-001 (the tools hosted here).
- ADR-004 (service structure that hosts the platform).
