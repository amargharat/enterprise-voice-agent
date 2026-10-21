## ADR-001: Answer from typed tools, a rules engine and a deterministic calculator, not from RAG or text-to-SQL

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Amar Gharat (project lead), Design Architect (Amol)

### Context
- PRD problem A: the customer's current chatbot gives generic, outdated or non-customer-specific answers.
- The sample questions need account data, policy rules, calculations and prior turns together. Example: "My EMI increased. Why? And if I prepay ₹50,000, how much interest would I save?" needs the EMI history, the rate-reset rule, and an exact interest calculation.
- The business requirement says a successful solution is "not simply an LLM connected to a vector database", and answers must be verifiable.
- Money figures must be exact (project standard: no float for money).

### Decision
The assistant answers by having the model plan calls to typed, authorised tools, with every figure computed by a deterministic calculator and every policy outcome decided by a rules engine that cites its clause.

### Options considered

#### Option A: Typed tools + rules engine + Decimal calculator (chosen)
- **Pros:** every number traces to a tool output and calculator inputs, so the evidence view and number verifier can check it; `customer_id` is injected by the platform, so cross-customer access is impossible by construction; failures are per-tool and visible; rules can be changed as data during the interview change request.
- **Cons:** each capability needs a tool definition and each policy a rule, which costs build time within the 3-day budget; questions with no matching tool need a clear fallback.
- **Risks:** rule authoring errors produce confidently wrong outcomes; mitigated by tests against hand-calculated cases.

#### Option B: RAG over policy documents and account data placed in context
- **Pros:** fastest to build; flexible for novel questions.
- **Cons:** the model would do EMI and interest arithmetic itself; the retrieved text cannot guarantee a rule was applied; this is the generic-answer behaviour the customer is leaving.
- **Risks:** plausible but wrong financial figures; cannot be verified.

#### Option C: Model-generated SQL or code over the data (text-to-SQL)
- **Pros:** highly flexible queries over structured data; little tool authoring.
- **Cons:** the rules and calculations still live in prompts; hard to verify; access control depends on the generated query.
- **Risks:** injection, cross-customer data exposure, and silent wrong joins.

### Rationale
Criteria in order: correctness and verifiability, authorisation by construction, ability to change rules quickly, then build speed. Only Option A satisfies the first two. Option B is acceptable only for explanatory text, so the policy store keeps clause text for citation, but rules decide.

### Consequences

**Positive:**
- Answers are explainable: the evidence view shows systems, data, rule and inputs.
- Calculator and rules are unit-testable against independent calculations.
- New tools and rules are added as configuration plus small code.

**Negative:**
- Upfront authoring of tool schemas, rules and calculator cases.
- Out-of-scope questions must be refused or escalated rather than improvised.

**Monitoring:**
- Golden-set accuracy (target in PRD: at least 90%, calculations 100%).
- Number-verifier rejection rate per week; a rising rate means the composer is drifting from the evidence.
- Share of turns ending in "I can't answer that", to catch missing tools.

### Linked ADRs
- ADR-003 (the tool platform that hosts these tools).
