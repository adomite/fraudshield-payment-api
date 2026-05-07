# FraudShield Payment Risk Monitor

**Real-time fraud decisioning for fiat and stablecoin payment flows.**

FraudShield is a working API that demonstrates end-to-end fraud prevention logic across traditional card payments and stablecoin transactions. It normalizes both payment types into a unified risk evaluation layer, applies rule-based and enriched risk scoring, and returns an authorization decision with a full audit trail.

Built to show how fraud controls integrate into modern payment infrastructure — including on-chain risk surfaces that traditional fraud engines weren't designed to handle.

---

## Why This Exists

Traditional fraud engines (Actimize, Falcon, FICO) were built for card transactions: known merchants, fixed rails, reversible payments. Stablecoins break those assumptions — transactions are pseudonymous, irreversible, and settled on-chain in seconds. The risk surface is different. The integration patterns are different. The compliance obligations (Travel Rule, wallet screening) are new.

This project demonstrates:
- How a unified fraud decisioning layer can handle both payment types
- Where the risk logic differs between fiat and on-chain transactions
- How to encode Travel Rule compliance as a system behavior, not a manual check
- What an auditable, explainable risk decision looks like at the API level

---

## Payment Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     PAYMENT EVENT                           │
│         (card transaction OR stablecoin transfer)           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  NORMALIZATION LAYER                        │
│   Unified PaymentEvent schema regardless of payment type   │
│   Fiat: card BIN, merchant MCC, authorization amount       │
│   On-chain: wallet address, chain, token, block timestamp  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  ENRICHMENT LAYER                           │
│   Fiat: BIN lookup, merchant risk category                 │
│   On-chain: wallet screening (TRM Labs API)                │
│   Both: velocity checks, amount thresholds, geo risk       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  RISK EVALUATION ENGINE                     │
│   Rule-based scoring with weighted risk factors            │
│   Travel Rule flag: >$1,000 USDC triggers compliance hold  │
│   Sanctions screening result from wallet enrichment        │
│   Velocity rules: frequency, amount, merchant exposure     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  DECISION ENGINE                            │
│   APPROVE  — score < 40, no hard blocks                   │
│   REVIEW   — score 40–74, or Travel Rule triggered        │
│   DECLINE  — score ≥ 75, or sanctions hit, or velocity    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│               AUDIT LOG + WEBHOOK                           │
│   Immutable record: what was evaluated, why, what decided  │
│   Downstream system notified via webhook                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Why Fiat and On-Chain Risk Logic Differs

| Dimension | Card / Fiat | Stablecoin / On-chain |
|---|---|---|
| **Reversibility** | Chargeback possible (T+60 days) | Irreversible once confirmed |
| **Identity** | Card BIN, merchant MID, named account | Pseudonymous wallet address |
| **Settlement speed** | T+1 to T+2 | Minutes to seconds |
| **Fraud signal** | Velocity, geo, MCC, BIN risk | Wallet history, chain analysis, mixer exposure |
| **Compliance trigger** | AML thresholds, Reg E | Travel Rule (>$1,000 FATF threshold) |
| **Fallback on timeout** | Soft decline / approve with flag | Must not approve — irreversible |

This difference matters for system design. A timeout fallback that soft-approves a card transaction (to preserve customer experience) is the wrong default for a stablecoin transaction. FraudShield encodes this as a hard rule.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| API framework | FastAPI (Python) | Async, auto-schema, close to production patterns |
| Data validation | Pydantic v2 | Strict schemas, clear error messages |
| Risk rules engine | Custom (pure Python) | Transparent logic, no black box |
| Wallet screening | TRM Labs API (sandbox) | Industry standard on-chain risk |
| Audit log | PostgreSQL (append-only table) | Immutable, queryable, production-realistic |
| Webhook delivery | Background task + retry | Simulates real downstream notification |
| Tests | Pytest | Core flow coverage + failure scenarios |
| Docs | OpenAPI (auto-generated) | Interactive API exploration |

---

## Project Structure

```
fraudshield-payment-api/
├── app/
│   ├── api/
│   │   ├── routes.py          # POST /evaluate, GET /decision/{id}, GET /audit/{id}
│   │   └── deps.py            # Shared dependencies
│   ├── core/
│   │   ├── risk_engine.py     # Scoring logic + decision thresholds
│   │   ├── rules.py           # Individual risk rules (velocity, amount, geo, travel_rule)
│   │   └── audit.py           # Audit log writer
│   ├── integrations/
│   │   ├── trm_labs.py        # Wallet screening integration
│   │   └── webhook.py         # Outbound webhook with retry
│   └── models/
│       ├── payment.py         # PaymentEvent schema (fiat + stablecoin)
│       ├── decision.py        # RiskDecision response schema
│       └── audit.py           # AuditRecord schema
├── tests/
│   ├── test_risk_engine.py    # Core scoring unit tests
│   ├── test_api.py            # Endpoint integration tests
│   └── scenarios/             # Named test cases (sanctions_hit, travel_rule_trigger, etc.)
├── docs/
│   ├── architecture.md        # This system's design decisions
│   └── failure_modes.md       # What breaks and what happens
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## API Reference

### `POST /evaluate`
Submit a payment event for risk evaluation.

**Request — Card Transaction:**
```json
{
  "payment_type": "card",
  "transaction_id": "txn_abc123",
  "amount_usd": 450.00,
  "currency": "USD",
  "card": {
    "bin": "424242",
    "last4": "4242",
    "country_of_issue": "US"
  },
  "merchant": {
    "mcc": "5411",
    "name": "Whole Foods Market",
    "country": "US"
  },
  "customer_id": "cust_001",
  "timestamp": "2025-05-06T14:30:00Z"
}
```

**Request — Stablecoin Transaction:**
```json
{
  "payment_type": "stablecoin",
  "transaction_id": "txn_def456",
  "amount_usd": 1250.00,
  "currency": "USDC",
  "onchain": {
    "sender_wallet": "0xAbC123...",
    "receiver_wallet": "0xDeF456...",
    "chain": "ethereum",
    "token_contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
  },
  "customer_id": "cust_002",
  "timestamp": "2025-05-06T14:31:00Z"
}
```

**Response:**
```json
{
  "decision_id": "dec_789xyz",
  "transaction_id": "txn_def456",
  "decision": "REVIEW",
  "risk_score": 62,
  "triggered_rules": [
    {
      "rule": "TRAVEL_RULE_THRESHOLD",
      "severity": "HIGH",
      "detail": "Amount $1,250 exceeds FATF $1,000 threshold. Originator/beneficiary data required."
    },
    {
      "rule": "STABLECOIN_FIRST_TIME_WALLET",
      "severity": "MEDIUM",
      "detail": "Receiver wallet has no prior transaction history in system."
    }
  ],
  "fallback_behavior": "HOLD_FOR_COMPLIANCE_REVIEW",
  "evaluated_at": "2025-05-06T14:31:00.412Z",
  "audit_id": "aud_101112"
}
```

---

## Failure Mode Design

**What happens when the TRM Labs wallet screening API times out?**

For card transactions: the system applies a conservative fallback score (+20 risk points) and continues to a decision. Customer experience is preserved.

For stablecoin transactions: the system **does not approve**. It returns REVIEW with `fallback_behavior: HOLD_PENDING_SCREENING`. This is a hard rule — stablecoin transactions are irreversible. A timeout is not the same as a clean screen.

This distinction is documented in [`docs/failure_modes.md`](docs/failure_modes.md).

---

## Travel Rule Implementation

Per FATF Recommendation 16, Virtual Asset Service Providers (VASPs) must collect and transmit originator and beneficiary information for transfers above $1,000 USD equivalent.

FraudShield encodes this as a system rule, not a manual check:

1. If `payment_type == stablecoin` AND `amount_usd >= 1000`: rule `TRAVEL_RULE_THRESHOLD` fires
2. Decision is automatically set to minimum `REVIEW` (cannot be auto-approved)
3. `fallback_behavior` field signals downstream compliance system what action is required
4. Audit record captures the rule trigger with timestamp for regulatory traceability

Reference: [FATF Guidance on Virtual Assets (2021)](https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Guidance-rba-virtual-assets-2021.html)

---

## Running Locally

```bash
# Clone and install
git clone https://github.com/adomite/fraudshield-payment-api.git
cd fraudshield-payment-api
pip install -r requirements.txt

# Environment variables
cp .env.example .env
# Add your TRM_LABS_API_KEY (sandbox key works)

# Start with Docker
docker-compose up

# Or directly
uvicorn app.main:app --reload

# Run tests
pytest tests/ -v
```

API docs available at `http://localhost:8000/docs`

---

## About This Project

Built by [Adolfo Mite](https://linkedin.com/in/mitelite) — Fraud Prevention Tech Lead with 14 years building real-time risk infrastructure at Banamex/Citibanamex.
[linkedin.com/in/mitelite](https://www.linkedin.com/in/mitelite)

This project translates that experience into code: specifically to explore how traditional fraud prevention patterns extend (and where they break) when applied to stablecoin payment flows.

Questions, feedback, or collaborations: let's connect on LinkedIn.