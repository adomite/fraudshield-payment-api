"""
Named Test Scenarios

These are the cases that matter. Not happy paths — edge cases,
failure modes, and compliance boundaries.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def card_transaction_base():
    return {
        "payment_type": "card",
        "transaction_id": "txn_test_001",
        "amount_usd": 150.00,
        "currency": "USD",
        "customer_id": "cust_001",
        "timestamp": "2025-05-06T14:30:00Z",
        "card": {"bin": "424242", "last4": "4242", "country_of_issue": "US"},
        "merchant": {"mcc": "5411", "name": "Whole Foods", "country": "US"}
    }


@pytest.fixture
def stablecoin_transaction_base():
    return {
        "payment_type": "stablecoin",
        "transaction_id": "txn_test_002",
        "amount_usd": 500.00,
        "currency": "USDC",
        "customer_id": "cust_002",
        "timestamp": "2025-05-06T14:31:00Z",
        "onchain": {
            "sender_wallet": "0xCleanWallet123",
            "receiver_wallet": "0xReceiverWallet456",
            "chain": "ethereum",
            "token_contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        }
    }


@pytest.mark.asyncio
async def test_scenario_travel_rule_triggers_review(stablecoin_transaction_base):
    """
    SCENARIO: Stablecoin transfer at $1,250 — above FATF $1,000 threshold.
    EXPECTED: REVIEW decision, travel_rule_applicable=True, cannot be APPROVE.
    """
    stablecoin_transaction_base["amount_usd"] = 1250.00
    stablecoin_transaction_base["transaction_id"] = "txn_travel_rule_001"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/evaluate", json=stablecoin_transaction_base)

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] in ("REVIEW", "DECLINE")
    assert data["travel_rule_applicable"] is True
    assert any(r["rule"] == "TRAVEL_RULE_THRESHOLD" for r in data["triggered_rules"])
    assert data["decision"] != "APPROVE", "Travel Rule transactions must never be auto-approved"


@pytest.mark.asyncio
async def test_scenario_low_value_stablecoin_below_travel_rule(stablecoin_transaction_base):
    """
    SCENARIO: Stablecoin transfer at $500 — below Travel Rule threshold.
    EXPECTED: travel_rule_applicable=False. Decision based on other risk factors only.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/evaluate", json=stablecoin_transaction_base)

    assert response.status_code == 200
    data = response.json()
    assert data["travel_rule_applicable"] is False
    assert not any(r["rule"] == "TRAVEL_RULE_THRESHOLD" for r in data["triggered_rules"])


@pytest.mark.asyncio
async def test_scenario_high_risk_mcc_card(card_transaction_base):
    """
    SCENARIO: Card transaction at a gambling merchant (MCC 7995).
    EXPECTED: HIGH_RISK_MCC rule fires, elevated score.
    """
    card_transaction_base["merchant"]["mcc"] = "7995"
    card_transaction_base["merchant"]["name"] = "Casino XYZ"
    card_transaction_base["transaction_id"] = "txn_mcc_001"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/evaluate", json=card_transaction_base)

    assert response.status_code == 200
    data = response.json()
    assert any(r["rule"] == "HIGH_RISK_MCC" for r in data["triggered_rules"])
    assert data["risk_score"] >= 30


@pytest.mark.asyncio
async def test_scenario_card_not_affected_by_travel_rule(card_transaction_base):
    """
    SCENARIO: Card transaction at $5,000 — Travel Rule should NOT apply.
    Travel Rule is stablecoin-specific (VASP requirement).
    EXPECTED: travel_rule_applicable=False regardless of amount.
    """
    card_transaction_base["amount_usd"] = 5000.00
    card_transaction_base["transaction_id"] = "txn_card_highamount"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/evaluate", json=card_transaction_base)

    assert response.status_code == 200
    data = response.json()
    assert data["travel_rule_applicable"] is False


@pytest.mark.asyncio
async def test_scenario_missing_card_details_rejected():
    """
    SCENARIO: payment_type=card but no card details provided.
    EXPECTED: 422 validation error. System rejects at schema level, not logic level.
    """
    bad_payload = {
        "payment_type": "card",
        "transaction_id": "txn_bad_001",
        "amount_usd": 100.00,
        "currency": "USD",
        "customer_id": "cust_bad",
        "timestamp": "2025-05-06T14:30:00Z"
        # Missing card and merchant fields
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/evaluate", json=bad_payload)

    assert response.status_code == 422
