---
artifact-type: sequence-diagram
subject: Customer journeys J1 (EMI explain and prepayment), J2 (voice with interruption), J3 (failed payments and dispute)
version: 1
supersedes: none
generated-by: h-bmad-generate-sequence-diagram
source-design:
  - enterprise-voice-agent-system-design-v1.md
  - tool-platform-enterprise-systems-integration-design-v1.md
  - tool-platform-component-design-v1.md
ticket: none
---

# Sequence Diagrams: Journeys J1 to J3

Mermaid syntax validated. `-->>` is used for returns and for async fire-and-forget (notes mark the async audit lines).

## J1: Explain the EMI rise and simulate a prepayment (text)

```mermaid
sequenceDiagram
  actor Cust as Customer
  participant UI as Web UI
  participant Orch as Orchestrator
  participant LLM as Model
  participant TG as Tool Gateway
  participant Loan as Loan Mgmt
  participant Pay as Payments
  participant Pol as Policy
  participant Calc as Calculator
  participant Aud as Audit

  Cust->>UI: Why did my EMI rise? Save on 50,000 prepay?
  UI->>Orch: turn(text, session)
  activate Orch
  Orch->>LLM: plan(context, tool specs)
  LLM-->>Orch: calls: loan, rate-history, payments, prepay rules
  Orch->>TG: execute_many(calls, ctx)
  activate TG
  Note over TG: customer_id injected from session, never from the model
  par Loan data
    TG->>Loan: GET loan, rate-history
  and Payment data
    TG->>Pay: GET recent payments
  and Policy data
    TG->>Pol: GET prepayment rules
  end
  alt all systems answer
    TG-->>Orch: typed results + evidence
  else Payments times out
    loop one retry with jittered backoff
      TG->>Pay: GET payments (new request id)
    end
    TG-->>Orch: partial results, Payments marked ERROR
    Note over Orch: answer states what could not be checked, no invented data
  end
  deactivate TG
  Orch->>Calc: emi_change(), interest_saved(50000)
  Calc-->>Orch: exact Decimal figures
  Orch->>LLM: compose(evidence only)
  LLM-->>Orch: draft answer
  alt every number found in evidence
    Orch-->>UI: stream answer + evidence view
  else number not in evidence
    Orch->>LLM: regenerate with figures from evidence
    Note over Orch: if still failing, fall back to evidence template
    Orch-->>UI: stream verified answer
  end
  Orch-->>Aud: record turn, calls, evidence (async)
  deactivate Orch
  UI-->>Cust: answer with sources and calculation inputs
```

## J2: Voice with an interruption and a topic change

```mermaid
sequenceDiagram
  actor Caller
  participant Voice as Voice Gateway
  participant STT as Speech to Text
  participant TTS as Text to Speech
  participant Orch as Orchestrator
  participant TG as Tool Gateway
  participant Loan as Loan Mgmt
  participant Pay as Payments
  participant Calc as Calculator

  Caller->>Voice: audio: What is my next EMI?
  Voice->>STT: stream audio
  STT-->>Voice: final transcript
  Voice->>Orch: turn 1 (text)
  activate Orch
  Orch->>TG: loan summary
  TG->>Loan: GET loan
  Loan-->>TG: next EMI
  TG-->>Orch: result + evidence
  Orch-->>Voice: sentence 1 (streamed)
  Voice->>TTS: speak sentence 1
  TTS-->>Caller: audio: Your next EMI is...
  Note over Voice,TTS: sentences stream to TTS as produced, first audio under 1.5 s
  Caller->>Voice: audio (interrupts): actually check my last payment
  Voice->>TTS: cancel playback
  Voice->>Orch: cancel turn 1, barge-in
  deactivate Orch
  Note over Voice,Orch: cancel within 300 ms, in-flight reads finish and fill the cache
  Voice->>Orch: turn 2: last payment (loan from session context)
  activate Orch
  Orch->>TG: last payment
  alt tools slower than 700 ms
    Orch-->>Voice: progress phrase: let me check that
    Voice->>TTS: speak progress phrase
  end
  TG->>Pay: GET last payment
  Pay-->>TG: payment record
  TG-->>Orch: result + evidence
  Orch-->>Voice: answer sentences
  Voice->>TTS: speak
  TTS-->>Caller: audio: Your last payment was...
  deactivate Orch
  Caller->>Voice: audio: would 20,000 extra reduce my tenure?
  Voice->>Orch: turn 3 (same loan, no re-asking)
  activate Orch
  Orch->>Calc: tenure_effect(extra=20000)
  Calc-->>Orch: new tenure, exact figures
  Orch-->>Voice: verified answer
  Voice->>TTS: speak
  TTS-->>Caller: audio: Paying 20,000 extra would...
  deactivate Orch
  alt speech-to-text stream drops
    Voice-->>Caller: switch to text, transcript kept
  end
```

## J3: Investigate failed payments, then raise a dispute

```mermaid
sequenceDiagram
  actor Cust as Customer
  participant UI as Web UI
  participant Orch as Orchestrator
  participant TG as Tool Gateway
  participant Pay as Payments
  participant Pol as Policy
  participant Tok as Token Store
  participant SO as Service Ops
  participant Aud as Audit

  Cust->>UI: Show failed payments, last six months
  UI->>Orch: turn
  Orch->>TG: execute_many(failed payments, failure reasons)
  par Payments
    TG->>Pay: GET payments status=FAILED
  and Policy
    TG->>Pol: GET failure-code texts
  end
  TG-->>Orch: failed list + reasons + evidence
  Orch-->>UI: list with explanations
  Cust->>UI: Raise a dispute on the second one
  UI->>Orch: turn
  Orch->>TG: prepare_action(dispute, PM-88213)
  activate TG
  TG->>Tok: store single-use token (5 min, params digest)
  TG-->>Orch: confirmation request
  deactivate TG
  Orch-->>UI: confirmation card (action summary from tool definition)
  Note over UI,TG: only the UI confirm button can execute, the model cannot self-confirm
  Cust->>UI: Confirm
  UI->>TG: confirm_action(token)
  activate TG
  TG->>Tok: consume token
  alt token expired or reused
    TG-->>UI: error, nothing sent
  else token valid
    TG->>Aud: write ACTION_EXECUTED record
    alt audit write fails
      TG-->>UI: fatal, write refused
    else audit recorded
      TG->>SO: POST service-requests (Idempotency-Key)
      alt created
        SO-->>TG: 201 reference SR-550214
      else timeout
        loop one retry with the same key
          TG->>SO: POST (same Idempotency-Key)
        end
        alt still unknown
          TG->>SO: GET request status by key
          SO-->>TG: exists or not found
        end
      end
      Note over TG,SO: same key means a retry or double click never creates two disputes
    end
  end
  TG-->>UI: result or honest unknown-status message
  deactivate TG
  UI-->>Cust: reference SR-550214 and status
  TG-->>Aud: outcome recorded (async)
```

## Summary

J1 fans out three reads in parallel, computes figures in the calculator, and checks every number against the evidence before answering. J2 shows the same orchestrator behind voice, with barge-in cancelling speech, kept context across turns, and a progress phrase when tools are slow. J3 separates investigating from acting: the model can only prepare an action, and the customer's confirmation, a single-use token and an idempotency key govern the write.

## Key design decisions

- **Parallel reads:** latency is the slowest system, not the sum, which keeps J1 within the response targets.
- **Partial results are honest:** a failed system is reported as unavailable, never filled in.
- **Verify before sending:** numbers in a draft must exist in the evidence, otherwise regenerate or use the evidence template.
- **Barge-in cancels only the output:** in-flight reads finish and warm the cache, so the next turn is faster.
- **Confirmation is out of the model's hands:** the UI confirm triggers the write, so a prompt injection cannot execute an action.
- **Audit before write:** if the audit record can't be written, the write is refused.
- **Write timeout means "unknown," not "failed":** retry with the same key, then check status before telling the customer anything.

*Payloads and phrases (for example the progress phrase text and PM-88213) are illustrative.*
