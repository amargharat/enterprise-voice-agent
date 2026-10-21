# Generated from design: tool-platform-component-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-system-design-v1.md (v1)
# Ticket: none
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.platform.tool_gateway import CircuitBreaker, ToolCall, ToolGateway, ToolGatewayError, ToolRegistry, TurnContext
from app.rules_engine import RulesEngine
from app.verifier import verify_rewrite


def test_registry_returns_workflow_scoped_tools_and_scopes():
    registry = ToolRegistry()
    assert "card.statement" in {tool["name"] for tool in registry.list_tools("credit-card")}
    assert "card.statement" not in {tool["name"] for tool in registry.list_tools("loan-servicing")}
    assert "service-requests:write" in registry.scopes_for("loan-servicing")


def test_gateway_rejects_identity_injected_by_model():
    gateway = ToolGateway()
    context = TurnContext(
        session_id="session", turn_id="turn", customer_id="CU-2291", workflow_id="loan-servicing",
        scopes=gateway.registry.scopes_for("loan-servicing"), deadline=datetime.now(timezone.utc) + timedelta(seconds=5),
    )
    async def run():
        return await gateway.execute_many([ToolCall(tool_name="loan.summary", arguments={"customerId": "CU-3140"})], context)
    with pytest.raises(ToolGatewayError, match="identity"):
        asyncio.run(run())


def test_circuit_breaker_opens_after_threshold_and_recovers_after_cooldown(monkeypatch):
    breaker = CircuitBreaker()
    for _ in range(10):
        breaker.record("PAYMENTS", True)
    assert breaker.state("PAYMENTS") == "OPEN"
    assert not breaker.permit("PAYMENTS")
    breaker.open_until["PAYMENTS"] = 0
    assert breaker.permit("PAYMENTS")


def test_policy_rule_requires_condition_match():
    engine = RulesEngine()
    rule = {
        "ruleId": "PL-FC-001", "clauseId": "PL-TERMS-7.2", "clauseText": "No charges on floating-rate loans.",
        "condition": {"all": [{"field": "rateType", "op": "eq", "value": "FLOATING"}]},
        "outcome": {"penaltyPercent": "0.00"},
    }
    assert engine.evaluate(rule, {"rateType": "FLOATING"}).applies is True
    assert engine.evaluate(rule, {"rateType": "FIXED"}).applies is False


def test_answer_rewrite_rejects_changed_money_or_clause():
    draft = "EMI ₹11,250.00; saves ₹20,222.80. Rule PL-TERMS-5.4 applies."
    assert verify_rewrite(draft, "Your EMI is ₹11,250.00 and it saves ₹20,222.80 under PL-TERMS-5.4.")[0]
    assert not verify_rewrite(draft, "Your EMI is ₹10,000.00 and it saves ₹20,222.80 under PL-TERMS-5.4.")[0]
    assert not verify_rewrite(draft, "Your EMI is ₹11,250.00 and it saves ₹20,222.80 under PL-TERMS-7.2.")[0]


def verified_session(client: TestClient) -> str:
    session_id = client.post("/api/session/start", json={"workflowId": "loan-servicing"}).json()["sessionId"]
    response = client.post("/api/session/verify", json={"sessionId": session_id, "customerId": "CU-2291", "otp": "246810"})
    assert response.status_code == 200
    return session_id


def test_websocket_streams_shared_orchestrator_turn_and_evidence():
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        with client.websocket_connect(f"/ws/conversations/{session_id}") as socket:
            socket.send_json({"type": "turn", "workflowId": "loan-servicing", "channel": "TEXT", "message": "What is my next EMI?"})
            frames = []
            while True:
                frame = socket.receive_json()
                frames.append(frame)
                if frame["type"] == "turn.completed":
                    break
        assert frames[0]["type"] == "turn.started"
        assert any(frame["type"] == "assistant.delta" for frame in frames)
        assert frames[-1]["type"] == "turn.completed"
        assert frames[-1]["evidence"]


def test_voice_socket_reports_provider_fallback_without_storing_audio():
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        with client.websocket_connect(f"/ws/conversations/{session_id}") as socket:
            socket.send_json({"type": "voice.audio.start", "mimeType": "audio/webm", "workflowId": "loan-servicing"})
            result = socket.receive_json()
        assert result["type"] == "voice.unavailable"
