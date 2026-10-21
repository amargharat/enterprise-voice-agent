## ADR-002: Build live voice as a cascaded STT → LLM → TTS pipeline

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Amar Gharat (project lead), Design Architect (Amol)

### Context
- PRD problem B and challenge 3: natural voice with follow-ups, interruptions and topic changes, using the same capabilities as text, and responsive even when backends are slow.
- Targets assumed in the PRD: first audio within 1.5 s of end of speech; barge-in cancels speech within 300 ms.
- The business requirement says the interaction is evaluated, "not just the underlying speech-to-text or text-to-speech integration."
- Voice must call the same tools, rules and calculator as text (ADR-001).

### Decision
Voice uses streaming speech-to-text, the same tool-using orchestrator as text, and streaming text-to-speech, with our own turn manager handling barge-in and progress cues.

### Options considered

#### Option A: Cascaded STT → LLM → TTS (chosen)
- **Pros:** one orchestrator serves text and voice, so capabilities and context are shared by construction; we control barge-in, sentence-level TTS streaming and filler phrases during slow tools; providers are swappable behind adapters.
- **Cons:** three latency stages to tune (estimated about 1.2 s to first audio in the design budget, unmeasured); end-of-speech detection errors cause early cut-ins or delays.
- **Risks:** misrecognition of amounts (for example ₹20,000 versus ₹2,000); mitigated by echoing figures back and confirming before actions.

#### Option B: Speech-to-speech realtime model with tool calling
- **Pros:** lower base latency and more natural prosody; built-in interruption handling.
- **Cons:** less control over the verifier, evidence and progress cues; tool use and the number check are harder to enforce; behaviour is harder to reproduce and test.
- **Risks:** provider lock-in and unverifiable spoken figures, which conflicts with ADR-001.

#### Option C: Hybrid, realtime model for chat and cascaded path for tool-heavy turns
- **Pros:** best feel for small talk.
- **Cons:** two voice stacks and a handoff to build and test in 3 days.
- **Risks:** inconsistent behaviour between paths.

### Rationale
Criteria: verifiable answers on the same capabilities as text, controllable interruption and progress behaviour, and buildable in the time. Option A keeps voice a thin channel over one brain. Latency is the cost, accepted because the evaluation looks at conversational behaviour under slow backends, which we control best in a cascade.

### Consequences

**Positive:**
- No duplicate logic for voice; a fix to a tool benefits both channels.
- Barge-in and filler cues are ours to tune and demonstrate.

**Negative:**
- Latency depends on three providers plus our turn manager.
- We own endpointing and echo-handling quality.

**Monitoring:**
- Time to first audio p50, p95 and p99 by stage (STT, model, tools, TTS).
- Barge-in cancel latency against the 300 ms target.
- Mis-heard-amount rate in test calls; if above a small agreed threshold, add read-back for every amount.

### Linked ADRs
- ADR-001 (same tools and verifier used in voice).
- ADR-004 (audio transport).
