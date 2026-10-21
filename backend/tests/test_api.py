# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-prd-v1.md (v1), tool-platform-component-design-v1.md (v1)
# Ticket: none
from fastapi.testclient import TestClient

from app import main
from app.platform.tool_gateway import ToolGatewayError


def verified_session(client: TestClient, workflow: str = "loan-servicing") -> str:
    started = client.post("/api/session/start", json={"workflowId": workflow}).json()
    session_id = started["sessionId"]
    verified = client.post("/api/session/verify", json={"sessionId": session_id, "customerId": "CU-2291", "otp": "246810"})
    assert verified.status_code == 200
    return session_id


def test_account_is_not_available_before_identity_verification():
    with TestClient(main.app) as client:
        session_id = client.post("/api/session/start", json={"workflowId": "loan-servicing"}).json()["sessionId"]
        response = client.get("/api/account", params={"sessionId": session_id})
        assert response.status_code == 403


def test_emi_simulation_returns_calculated_evidence():
    main.LATENCIES.clear()
    main.AUDIT.clear()
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        result = client.post("/api/chat", json={"sessionId": session_id, "message": "Why did my EMI change? What would ₹50,000 prepaid save?", "workflowId": "loan-servicing"}).json()
        assert "₹10,950.00" in result["answer"]
        assert "₹11,250.00" in result["answer"]
        assert "interest" in result["answer"].lower()
        assert any(item["system"] == "POLICY" for item in result["evidence"])
        assert all(item["status"] == "OK" for item in result["evidence"])


def test_payment_failure_is_reported_without_inventing_results():
    main.FAILURES["payments"] = True
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        result = client.post("/api/chat", json={"sessionId": session_id, "message": "Show my failed payments", "workflowId": "loan-servicing"}).json()
        assert "can’t reach" in result["answer"]
        assert "PM-88213" not in result["answer"]
        assert any(item["status"] == "ERROR" for item in result["evidence"])
    main.FAILURES["payments"] = False


def test_confirmed_dispute_confirmation_is_single_use():
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        payload = {"sessionId": session_id, "workflowId": "loan-servicing", "channel": "TEXT"}
        first = client.post("/api/chat", json={**payload, "message": "Raise a dispute on PM-88213"}).json()
        assert first["action"]["summary"].endswith("PM-88213")
        first_result = client.post("/api/actions/confirm", json={"sessionId": session_id, "token": first["action"]["token"]}).json()
        second_confirmation = client.post("/api/actions/confirm", json={"sessionId": session_id, "token": first["action"]["token"]})
        assert first_result["reference"].startswith("SR-")
        assert second_confirmation.status_code == 200
        assert second_confirmation.json()["reference"] == first_result["reference"]
        assert second_confirmation.json()["replayed"] is True


def test_card_workflow_reuses_verified_session():
    with TestClient(main.app) as client:
        session_id = verified_session(client, "credit-card")
        result = client.post("/api/chat", json={"sessionId": session_id, "message": "Show my credit card statement", "workflowId": "credit-card"}).json()
        assert "Horizon Rewards Credit Card" in result["answer"]
        assert {item["system"] for item in result["evidence"] if item.get("type") != "verification"} == {"CRM", "PAYMENTS"}


def test_failed_payments_are_windowed_and_second_ordinal_selects_second_displayed_item():
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        listed = client.post("/api/chat", json={"sessionId": session_id, "message": "Show my failed payments", "workflowId": "loan-servicing"}).json()
        assert "PM-86109" not in listed["answer"]
        result = client.post("/api/chat", json={"sessionId": session_id, "message": "Raise a dispute on the second one", "workflowId": "loan-servicing"}).json()
        assert result["action"]["summary"].endswith("PM-87820")


def test_missing_prepayment_amount_asks_instead_of_assuming():
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        result = client.post("/api/chat", json={"sessionId": session_id, "message": "What would a prepayment save?", "workflowId": "loan-servicing"}).json()
        assert "What amount" in result["answer"]
        assert result["action"] is None


def test_card_dispute_requires_specific_statement_transaction():
    with TestClient(main.app) as client:
        session_id = verified_session(client, "credit-card")
        vague = client.post("/api/chat", json={"sessionId": session_id, "message": "Dispute a card transaction", "workflowId": "credit-card"}).json()
        assert vague["action"] is None
        specific = client.post("/api/chat", json={"sessionId": session_id, "message": "Dispute transaction TX-50081", "workflowId": "credit-card"}).json()
        assert specific["action"]["summary"].endswith("₹1,842.00)")


def test_non_applicable_foreclosure_rule_offers_confirmed_human_handoff():
    with TestClient(main.app) as client:
        started = client.post("/api/session/start", json={"workflowId": "loan-servicing"}).json()
        session_id = started["sessionId"]
        assert client.post("/api/session/verify", json={"sessionId": session_id, "customerId": "CU-3140", "otp": "246810"}).status_code == 200
        result = client.post("/api/chat", json={"sessionId": session_id, "message": "Am I eligible for foreclosure without a penalty?", "workflowId": "loan-servicing"}).json()
        assert "won’t guess" in result["answer"]
        assert result["action"]["summary"].startswith("Ask a loan servicing specialist")


def test_generic_service_request_clarifies_then_prepares_confirmable_ticket():
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        payload = {"sessionId": session_id, "workflowId": "loan-servicing"}
        clarification = client.post("/api/chat", json={**payload, "message": "I want to raise a request"}).json()
        assert clarification["action"] is None
        assert "describe the request" in clarification["answer"].lower()

        prepared = client.post("/api/chat", json={**payload, "message": "Update my mailing address"}).json()
        assert prepared["action"]["actionType"] == "TICKET"
        assert "update mailing address" in prepared["action"]["summary"].lower()

        submitted = client.post("/api/actions/confirm", json={"sessionId": session_id, "token": prepared["action"]["token"]}).json()
        assert submitted["reference"].startswith("SR-")
        assert submitted["status"] == "OPEN"


def test_service_request_can_be_cancelled_after_clarification():
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        payload = {"sessionId": session_id, "workflowId": "loan-servicing"}
        client.post("/api/chat", json={**payload, "message": "Open a service request"})
        cancelled = client.post("/api/chat", json={**payload, "message": "Cancel that"}).json()
        assert "cancelled" in cancelled["answer"].lower()
        assert cancelled["action"] is None


def test_specific_service_request_is_prepared_in_credit_card_workflow():
    with TestClient(main.app) as client:
        session_id = verified_session(client, "credit-card")
        result = client.post("/api/chat", json={
            "sessionId": session_id, "workflowId": "credit-card",
            "message": "Raise a request to update my mailing address",
        }).json()
        assert result["action"]["actionType"] == "TICKET"
        assert "card servicing specialist" in result["action"]["summary"].lower()


def test_unknown_write_outcome_can_retry_same_confirmation(monkeypatch):
    original = main.gateway.execute_write
    calls = 0

    async def timeout_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ToolGatewayError("OutcomeUnknown", "write timed out", retryable=True)
        return await original(*args, **kwargs)

    monkeypatch.setattr(main.gateway, "execute_write", timeout_once)
    with TestClient(main.app) as client:
        session_id = verified_session(client)
        turn = client.post("/api/chat", json={"sessionId": session_id, "message": "Raise a dispute on PM-88213", "workflowId": "loan-servicing"}).json()
        payload = {"sessionId": session_id, "token": turn["action"]["token"]}
        first = client.post("/api/actions/confirm", json=payload)
        assert first.status_code == 503
        second = client.post("/api/actions/confirm", json=payload)
        assert second.status_code == 200
        assert second.json()["reference"].startswith("SR-")
