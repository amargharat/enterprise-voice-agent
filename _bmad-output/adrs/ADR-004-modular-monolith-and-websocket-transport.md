## ADR-004: Use a modular monolith for the conversation tier and WebSocket for audio and events

**Status:** Proposed
**Date:** 2026-10-21
**Deciders:** Amar Gharat (project lead), Design Architect (Amol)

### Context
- The POC has a 3-day budget and must show a working product, architecture and a path toward 1,000 concurrent conversations.
- The conversation tier covers session, voice gateway, orchestrator, tool platform, calculator and rules engine; the five enterprise systems are mocks.
- Voice needs bidirectional audio and events between browser and server, with barge-in.

### Decision
Run the conversation tier as one stateless, async service with clear module boundaries, keep the mock enterprise systems as a separate service, and carry audio and events over WebSocket, with WebRTC as the production upgrade.

### Options considered

#### Option A: Modular monolith plus separate mocks, WebSocket transport (chosen)
- **Pros:** fastest to build and demo (one Compose stack); stateless workers with session state in Redis scale horizontally; module seams allow later extraction; WebSocket is simple to debug.
- **Cons:** audio over WebSocket handles poor networks worse than WebRTC (no built-in jitter handling or congestion control); one deployable means one blast radius.
- **Risks:** a CPU-heavy component (for example audio processing) could starve text turns; mitigated by async I/O and by keeping heavy processing in provider services.

#### Option B: Microservices per component
- **Pros:** independent scaling and deployment; mirrors a production target.
- **Cons:** network hops add latency to every turn against a 1.5 s budget; far more infrastructure for 3 days.
- **Risks:** time lost on plumbing instead of the journeys.

#### Option C: WebRTC with a media server from day one
- **Pros:** production-grade audio, echo cancellation and resilience.
- **Cons:** significant setup and moving parts; harder to run reproducibly from a README.
- **Risks:** demo failure from media-server configuration.

### Rationale
Criteria: delivery within 3 days, a reproducible demo, latency budget, and a credible scale story. Option A meets all four. The scale path (stateless workers, Redis, load balancer, later WebRTC and service extraction) is documented rather than built.

### Consequences

**Positive:**
- Simple local run, easy tracing of one turn end to end.
- Horizontal scale by adding workers.

**Negative:**
- Audio quality on poor networks is a known limit.
- Splitting services later needs deliberate work along the module seams.

**Monitoring:**
- Dropped or reconnected WebSocket sessions per 100 voice sessions.
- Per-worker CPU and event-loop lag under the load test; if lag rises before provider limits, extract the voice gateway.
- Concurrency at which p95 latency leaves target.

### Linked ADRs
- ADR-002 (voice pipeline carried over this transport).
- ADR-003 (platform hosted in the monolith).
