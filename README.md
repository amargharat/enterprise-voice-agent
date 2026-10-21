<!-- Generated from design: enterprise-voice-agent-system-design-v1.md (v1) -->
<!-- Supporting design: enterprise-voice-agent-prd-v1.md (v1) -->
<!-- Ticket: none -->

# Horizon Service Studio

This local proof of concept follows the architecture in `_bmad-output/planning-artifacts/enterprise-voice-agent-system-design-v1.md`: React/Vite, an async FastAPI conversation service, a separate mock-enterprise REST service, declarative typed tools, PostgreSQL, Redis, WebSockets, and Prometheus/OpenTelemetry. It uses synthetic data only; it is not connected to a bank and is not suitable for real customer information.

## Run the designed stack

Requirements: Docker Engine, `docker-compose` (or Docker Compose v2), and Node.js 22.12+ only if building the frontend outside Compose.

1. Copy `.env.example` to `.env`. The committed defaults are local demo credentials, not production secrets.
2. From the repository root, build and start all services with `docker-compose up --build`.
3. Open <http://localhost:5173>.

Services:

| Service | Local URL |
|---|---|
| React client | <http://localhost:5173> |
| Conversation API / OpenAPI | <http://localhost:8000/docs> |
| Mock enterprise API / OpenAPI | <http://localhost:8001/docs> |
| Prometheus | <http://localhost:9090> |
| Grafana | <http://localhost:3000> (user `admin`; password from `GRAFANA_PASSWORD`) |

Postgres and Redis stay private on the Compose network. The app, mock API, and observability UIs publish host ports for local development; use only on a trusted development machine/network, and do not expose them as production services. The first Postgres initialization runs the synthetic core schema/seed migration. To reset the demo database and Redis state, stop the stack and remove its volumes; this deletes all locally created synthetic requests and telemetry.

## Demo identities and journeys

- Customer IDs: `CU-2291` or `CU-3140`; demo code: `246810`.
- Ask “Why did my EMI change? What would ₹50,000 prepaid save?” to see tool-backed loan/rate/payment/policy evidence and deterministic `Decimal` results.
- Ask “Show my failed payments”, then “Raise a dispute on the second one”. The six-month result list is retained as turn context; review and confirm the exact reference.
- Say “I want to raise a request”, describe what you need, then review and confirm the service ticket to receive a reference and status.
- Switch to Credit card to see statement transactions, then dispute a specific `TX-…` item through the same gateway.
- Ask about foreclosure eligibility to see the evaluated rule and clause citation.
- Toggle Payments outage to test partial failure and honest fallback behavior.
- Voice audio uses WebSocket frames and provider-neutral STT/TTS adapters when endpoints are configured. Without server STT configuration, the UI uses browser speech recognition as a clearly labeled local fallback; text and transcript turns share the same WebSocket orchestrator.

## Local Ollama setup

The default `.env` values use Ollama on the Mac host for LLM intent/tool planning and answer wording; the backend container reaches it at `http://host.docker.internal:11435/v1`. Install Ollama, make its API reachable from Docker, start its service, and download the configured model:

```sh
brew install ollama
launchctl setenv OLLAMA_HOST 0.0.0.0:11435
brew services restart ollama
ollama pull qwen2.5:3b
```

The Ollama API has no built-in authentication. Binding to `0.0.0.0` is needed for Docker Desktop host access, so use this only on a trusted development machine/network and never expose it as a production service. Port `11435` avoids the default Ollama port if it is already occupied. Restart the app stack with `docker-compose up --build` after changing provider settings. The first model response can be slow while Ollama loads weights; the backend allows up to 30 seconds and falls back to its deterministic planner/templates if Ollama is unavailable or rejects a response. Ollama serves locally and does not require a cloud API key; `LLM_API_KEY=ollama` is a compatibility placeholder.

The `.env` provider values can be changed if needed:

- `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`: OpenAI-compatible chat-completions endpoint used for intent/tool planning and optional answer wording. The local deterministic planner remains available if Ollama is stopped or unset.
- `STT_ENDPOINT` and `TTS_ENDPOINT`: adapter endpoints. STT accepts raw audio with its MIME type and returns `{"text":"…"}`; TTS accepts `{"text":"…","voice":"en-IN"}` and returns audio bytes.
- `VOICE_PROVIDER_API_KEY`: optional bearer credential shared by those adapters.
- `MOCK_LATENCY_MIN_MS`, `MOCK_LATENCY_MAX_MS`, and `MOCK_FAILURE_RATE`: injected backend latency and failure profile.

## Implementation boundaries

- `backend/app/platform/tool_registry.json` is the single tool/workflow registry. The gateway validates inputs and outputs, injects verified identity, enforces scopes/allowlists, applies timeouts/retry/circuit breaking, caches policy reads in Redis, and emits evidence/audit records.
- `mock_enterprise/` exposes separate CRM, Loans, Payments, Policy, and Service Ops REST endpoints. Operational synthetic entities and confirmed requests are in PostgreSQL; conversation sessions and single-use confirmations are in Redis.
- The orchestrator uses the configured model adapter for a restricted JSON intent/tool plan; provider failures or no configured model fall back to the local deterministic planner. Money remains calculated with `Decimal`; policy conditions are evaluated by the rules engine and clause IDs are included in evidence.
- If a rule does not apply or evidence is insufficient, the named HumanHandoff component offers a specialist ticket; the customer must confirm before Service Ops receives it.
- Text turns and server audio frames use `/ws/conversations/{session_id}`. Voice endpointing/streaming behavior and <300 ms barge-in remain provider/browser dependent and must be measured with a selected STT/TTS provider; no provider or quota is selected in the design.
- Prometheus exposes per-tool and per-stage latency histograms; optional OTLP traces go to the local collector. These are demo measurements, not evidence of 1,000-conversation capacity. No load claim is made.
- This remains a POC: OTP and service credentials are fixed local demo values, TLS/production identity/compliance/retention are not implemented, and only synthetic data may be used.

## Tests and frontend build

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest backend/tests
```

```sh
cd frontend && npm ci && npm run build
```

With the Compose API running, the bounded local load test reports p50/p95/p99 and refuses non-local targets:

```sh
python scripts/load_test.py --requests 20 --concurrency 5
```

This is a small POC latency sample, not a 1,000-conversation capacity test.

Sample run on 2026-10-21 against the Compose stack (20 turns, concurrency 5): first visible WebSocket progress p50/p95/p99 **716/739/776 ms**; full turn p50/p95/p99 **2,493/5,228/5,271 ms**; HTTP/WebSocket failures **0**. This sample meets the documented first-response and full-answer budgets for this run only; it is not a production SLO or capacity claim.

## Design references

- `_bmad-output/planning-artifacts/enterprise-voice-agent-prd-v1.md`
- `_bmad-output/planning-artifacts/enterprise-voice-agent-system-design-v1.md`
- `_bmad-output/planning-artifacts/enterprise-voice-agent-data-design-v1.md`
- `_bmad-output/planning-artifacts/enterprise-voice-agent-journeys-sequence-diagram-v1.md`
- `_bmad-output/planning-artifacts/tool-platform-component-design-v1.md`
- `_bmad-output/planning-artifacts/tool-platform-enterprise-systems-integration-design-v1.md`
