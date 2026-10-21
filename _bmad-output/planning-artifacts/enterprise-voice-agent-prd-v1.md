---
artifact-type: prd
subject: Enterprise AI Loan Servicing Assistant (POC)
version: 1
supersedes: none
generated-by: h-bmad-create-prd-spec-doc
ticket: none
---

# PRD: Enterprise AI Loan Servicing Assistant (POC)

**Status:** Draft v1.0, built from the Blue Machines business requirement.
**Traceability:** A to D are the customer problems; C1 to C5 are the engineering challenges.

**Bottom line:** scope is clear and buildable in the 3-day window. Open items that need early closure: compliance regime, second workflow, latency targets, and preparing for the interview-time change request (section 12).

## 1. Overview

- **Product:** a web app where a customer of a large financial-services firm (2M+ customers, about 100K support interactions a day) uses a text and live-voice AI assistant for loan servicing.
- **Type:** a working POC to demonstrate to the Blue Machines engineering team, not a production release.
- **Differentiator:** answers are customer-specific, computed and explainable. They are not generic document retrieval or "an LLM connected to a vector database."
- **Extensibility:** at least one reusable platform capability, proven by a second workflow built on it.

## 2. Problem Statement

| ID | Problem | What good looks like |
|---|---|---|
| A | Chatbot answers are generic, outdated or not specific to the customer. | Precise, explainable, customer-specific answers drawing on account data, policy, calculations and latest transactions. |
| B | Voice support means IVR menus and agents switching between systems. | Natural voice: follow-ups, interruptions, topic changes, responsive even when backends are slow. |
| C | Service actions span CRM, Loans, Payments, Policy and Service Ops, with varied latency and failures. | One AI experience that retrieves, reasons over rules and performs authorised actions across them. |
| D | Every new workflow takes weeks of bespoke integration, logic, UI and monitoring. | An extensible platform so new use cases reuse intelligence, integration, context and execution. |

- **Evidence:** the requirement gives volumes (2M customers, 100K interactions a day) but no baseline for containment, handle time or CSAT. Baselines are an open question.

## 3. Goals

- **G1 (A):** answer the five sample questions correctly, with the figures and sources visible.
- **G2 (B):** a live voice conversation with natural turn-taking on the same capabilities as text.
- **G3 (C):** at least one real action executed end to end across systems, with a consistent experience for lookups and actions.
- **G4 (D):** one reusable capability, shown by a second workflow built without rebuilding it.
- **G5:** measured latency evidence, and a design that can evolve toward 1,000 concurrent conversations.

## 4. Non-Goals

- Real banking integrations, production authentication, or real customer data (synthetic data and mock backends are explicitly allowed).
- A full platform roadmap; the requirement asks for architecture and practical extensibility only.
- Actually running 1,000 concurrent customers (the requirement says "capable of evolving toward"; see open question 6).
- Native mobile apps, telephony/IVR integration, underwriting or new-loan origination.
- Binding financial advice.

## 5. Personas

- **P1 Existing loan customer:** wants to understand EMI, payments, charges and options, and to raise requests.
- **P2 Customer calling in (voice):** wants to avoid menus and ask naturally.
- **P3 Enterprise evaluator (Blue Machines engineering team):** judges the demo, architecture, latency and extensibility. This is the real audience of the POC.
- **P4 Customer's technology team (secondary):** the future builders of new use cases on the platform.

## 6. User Stories and Journeys

**Three required journeys (Challenge 1 asks for at least three):**

| Journey | Story | Source |
|---|---|---|
| J1 Explain and simulate | As a customer, I ask "My EMI increased this month. Why? And if I make a ₹50,000 prepayment today, how much interest would I save?" and get the cause and the saving, with the numbers shown. | A, C2 |
| J2 Voice with interruptions | As a caller, I ask "What's my next EMI?", cut in with "Actually, check my last payment first," then ask whether ₹20,000 extra would shorten my tenure. | B, C3 |
| J3 Investigate and act | As a customer, I ask for my failed payments in the last six months with explanations, then raise a dispute on one without repeating my details. | A, C, C4 |

**Additional stories:**

- **US-4:** I ask whether I'm eligible for foreclosure without a penalty and get the answer with the rule applied.
- **US-5:** I ask "Based on my current loan and terms, what are my options?" and see options with trade-offs.
- **US-6:** I switch between text and voice and keep the conversation context.
- **US-7:** I request a prepayment, a statement or a ticket, confirm it, and get a reference ID and status.
- **US-8 (second workflow):** I use a different use case (proposal in section 7) through the same platform.
- **US-9:** a reviewer opens any answer and sees the data, rules and calculation behind it.

## 7. Functional Requirements

| ID | Requirement | Source |
|---|---|---|
| **Customer experience** | | |
| FR-1 | Web UI with text chat and live voice in one conversation. | C1 |
| FR-2 | An account view (loan summary, upcoming EMI, recent payments, open requests) next to the conversation. | C1 |
| FR-3 | Conversation memory: no re-asking for details already given or in the account. | C1 |
| FR-4 | The interface shows progress for slow operations. | B, C3 |
| **Query engine** | | |
| FR-5 | Combine structured data, policies and rules, calculations, prior turns and multiple systems in one answer. | C2 |
| FR-6 | Money figures (EMI, interest saved, tenure effect, penalties) come from a deterministic calculator, never from model arithmetic. | A, C2 |
| FR-7 | Policy answers are grounded in the policy source, with the clause cited. | A |
| FR-8 | Each answer has an "evidence" view: systems called, data used, rule applied, calculation inputs. | A |
| FR-9 | The assistant says "I don't know" or escalates instead of guessing. | A |
| FR-10 | Must handle all five sample questions, plus ones that generic retrieval cannot answer. | C2 |
| **Voice** | | |
| FR-11 | Live voice using the same tools and context as text. | C3 |
| FR-12 | Barge-in: the assistant stops speaking when interrupted. | B, C3 |
| FR-13 | Intent change and follow-ups mid-conversation without restarting. | B, C3 |
| FR-14 | Spoken filler or progress cues during multi-call queries. | B, C3 |
| **Integrations and actions** | | |
| FR-15 | Five simulated systems: CRM, Loan Management, Payments, Policy Knowledge, Service Operations. | C4 |
| FR-16 | Mocks have realistic, varied latency and injected intermittent failures. | C4 |
| FR-17 | At least one write action, chosen from: prepayment request, payment dispute, repayment statement, servicing ticket. Recommend **two**: dispute (J3) and prepayment request (J1). | C4 |
| FR-18 | Write actions need explicit customer confirmation, authorisation checks and idempotency, and return a trackable reference. | C4 |
| FR-19 | Graceful handling when a system fails: retry or fall back, and tell the customer honestly. | C |
| **Platform** | | |
| FR-20 | One reusable capability, built once and used by two workflows. **Recommendation:** a declarative tool and connector layer (typed tool definitions, timeouts, retries, circuit breaking, auth and audit, shared conversation context). | D, C5 |
| FR-21 | A second workflow built on it without rebuilding it. **Recommendation:** credit-card servicing (statement query, dispute), since it reuses CRM, Payments, Policy and Service Ops. | D, C5 |
| FR-22 | Adding a tool or workflow should be configuration plus small code. Show before and after effort. | D |
| **Security and measurement** | | |
| FR-23 | Customer identification before account data (mock verification is acceptable). Per-customer data isolation. | Constraints |
| FR-24 | Audit log of every turn, tool call and action. | Constraints |
| FR-25 | Latency instrumentation per turn and per backend call, exportable as evidence. | Deliverable 4 |

## 8. Acceptance Criteria (key scenarios)

```gherkin
Scenario: J1 EMI change plus prepayment saving
  Given a verified customer whose EMI rose this month
  When they ask why it increased and what ₹50,000 prepaid today would save
  Then the answer states both EMI amounts and the cause from loan and rate data
  And the interest saved matches the deterministic calculator for that loan
  And the evidence view lists the systems, rule and inputs used

Scenario: J2 voice interruption and topic change
  Given a live voice session
  When the assistant is speaking the next EMI and the caller says "actually check my last payment"
  Then the assistant stops speaking and answers about the last payment
  And a later "would ₹20,000 extra reduce my tenure?" uses the same loan without asking again

Scenario: J3 act on investigated data
  Given the assistant listed the customer's failed payments with reasons
  When the customer says "raise a dispute on the second one" and confirms
  Then a request is created once with a reference ID and status
  And repeating the command does not create a duplicate

Scenario: Backend failure
  Given the Payments mock is failing
  When the customer asks for failed payments
  Then the assistant says it can't reach that data right now, offers a retry or a ticket, and does not invent data

Scenario: Unverified customer
  Given a visitor who has not verified identity
  When they ask about "my EMI"
  Then no account data is returned and they are asked to verify

Scenario: Second workflow reuse
  Given the credit-card use case
  Then it is built using the same tool layer, context and audit without changes to the core
```

## 9. Non-Functional Requirements

- **Performance (assumed targets, see 12.4):**
  - Text: first response token within 2 s; full answer within 6 s for multi-system queries.
  - Voice: first audio within 1.5 s of the end of speech; barge-in stops speech within 300 ms.
  - Report p50, p95 and p99 for every metric.
- **Backend simulation:** mocks respond in about 100 ms to 3 s, with 5 to 10% injected failures or timeouts.
- **Scalability:** a stateless conversation tier, externalised session state and async I/O, so concurrency can grow toward 1,000. Document the bottlenecks.
- **Security:** least-privilege tool access per customer, no cross-customer leakage, prompt-injection defences, secrets outside code, PII masked in logs, TLS.
- **Reliability:** timeouts, retries with backoff and circuit breakers on every connector.
- **Observability:** trace per turn across model, tools and voice.
- **Accessibility:** a text equivalent for all voice features; WCAG 2.1 AA for the UI.
- **Reproducibility:** one documented path to run it locally.

## 10. Assumptions and Dependencies

- Synthetic data and mock services are acceptable (stated in the requirement).
- Hosted models, third-party voice services and open-source tools are allowed.
- The stack is free to choose, and it is still TBD in project context.
- Currency is ₹, so an Indian loan context is assumed.
- Effort budget is 3 days, so scope is proportionate.
- Keys, accounts and network access for hosted model and voice services are needed. Not confirmed.
- Reliable demo conditions (microphone, network) are needed.

## 11. Success Metrics

| Metric | Target | Source |
|---|---|---|
| Sample questions answered correctly | 5 of 5 | Test run |
| Calculator accuracy against an independent calculation | 100% | Tests |
| Golden test set of 50+ questions | ≥ 90% correct | Test harness |
| Journeys J1 to J3 completed end to end | 3 of 3, text and voice | Demo |
| Voice first-audio latency p95 | ≤ 1.5 s (assumed) | Instrumentation |
| Failure injection handled without invented answers | 100% | Tests |
| Time to add the second workflow | Measured and reported | Build log |
| Latency report delivered | Yes | Deliverable 4 |

## 13. Release Plan and Sign-off

- **Day 1:** mock backends with latency and failures; tool layer and calculator; text query engine for J1.
- **Day 2:** actions (dispute and prepayment), the account UI and the evidence view; voice including barge-in.
- **Day 3:** second workflow; latency measurement; hardening, README and architecture write-up; demo rehearsal.
- **Deliverables:** working app, functional backend, reusable component, performance evidence, technical explanation, source repository with run instructions.
- **Sign-off needed:** project lead and Blue Machines technical reviewer. There is no compliance reviewer in the loop for the POC.
- **Readiness:** ready to start building. Items 2, 4 and 6 are worth closing early.
