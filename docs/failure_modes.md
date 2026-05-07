# Failure Modes & Fallback Design

The most revealing thing about a payment system isn't what happens when everything works. It's what happens when something breaks mid-transaction.

This document covers the failure scenarios FraudShield is designed to handle explicitly — and the reasoning behind each fallback decision.

---

## Failure Mode 1: Wallet Screening API Timeout

**Scenario:** A stablecoin payment event arrives. FraudShield calls TRM Labs for wallet risk intelligence. The API doesn't respond within 3 seconds.

**What most systems do:** Fail open. Approve the transaction to avoid customer friction. Log a warning.

**What FraudShield does (and why it's different for stablecoin):**

| Payment Type | Timeout Behavior | Rationale |
|---|---|---|
| Card | +20 risk score, continue to decision | Card transactions are reversible. Chargeback window exists. Customer friction cost is real. |
| Stablecoin | Force REVIEW, `HOLD_PENDING_SCREENING` | On-chain transactions are irreversible. A timeout is not the same as a clean screen. The risk of approving a sanctioned wallet is asymmetric — you cannot undo the settlement. |

**System signal returned:**
```json
{
  "decision": "REVIEW",
  "fallback_behavior": "HOLD_PENDING_SCREENING",
  "screening_status": "TIMEOUT",
  "triggered_rules": [{
    "rule": "SCREENING_TIMEOUT_STABLECOIN",
    "severity": "HIGH",
    "detail": "Wallet screening API timed out. Cannot approve without confirmed screening result."
  }]
}
```

**Downstream expectation:** The compliance operations team receives a webhook with this payload and holds the transaction pending manual wallet review or a successful retry.

---

## Failure Mode 2: Duplicate Transaction (Idempotency)

**Scenario:** Due to a network retry or client-side bug, the same transaction_id is submitted twice to `/evaluate`.

**Current behavior:** FraudShield accepts both and evaluates them independently.

**Planned behavior (v0.2):** On duplicate `transaction_id`, return the original decision without re-evaluating. This prevents:
- Double-charging risk (two REVIEW holds on the same transaction)
- Inconsistent decisions if external data changed between calls (e.g., wallet screening result differs on retry)

**Why this matters for financial systems:** Idempotency is a first-class requirement in payment infrastructure. A risk engine that produces different decisions for the same transaction depending on timing is a liability.

---

## Failure Mode 3: Travel Rule — Missing Counterparty Data

**Scenario:** A stablecoin transaction of $1,500 USDC arrives. The Travel Rule threshold is triggered. The originator has not provided beneficiary identifying information.

**What FraudShield does:** Returns `REVIEW` with `fallback_behavior: HOLD_FOR_COMPLIANCE_REVIEW`. The transaction cannot be auto-approved regardless of risk score.

**What the downstream system must do:** Collect originator/beneficiary name, account number, and physical address per FATF Recommendation 16. Only after that information is captured should the hold be released.

**What FraudShield does NOT do:** Collect or store that data. FraudShield is a risk decisioning layer — not a KYC/KYB data store. The signal it sends is: *this transaction requires compliance action before it can proceed.*

---

## Failure Mode 4: Risk Engine Internal Error

**Scenario:** An unhandled exception occurs inside the rule evaluation loop (e.g., malformed screening response from TRM Labs).

**Behavior:** The API returns HTTP 500 with a generic error message. The transaction is NOT approved silently.

**Why not fail open?** In fraud systems, silent failures are worse than loud ones. An error that approves a fraudulent transaction is more damaging than an error that declines a legitimate one. The default posture is fail closed.

**Planned improvement (v0.2):** A circuit-breaker pattern for external integrations, so a degraded TRM Labs connection triggers a fallback mode (conservative scoring) rather than an unhandled exception.

---

## Failure Mode 5: Sanctions Hit on Receiver Wallet

**Scenario:** The sender wallet is clean, but the receiver wallet matches a sanctions list.

**Current behavior:** FraudShield screens sender only.

**Gap acknowledged:** This is a known limitation of v0.1. Screening only the sender misses money mule patterns where a clean wallet sends funds to a sanctioned destination.

**Planned behavior (v0.2):** Screen both sender and receiver wallets. Decision: DECLINE if either wallet returns a sanctions hit. The additional latency cost (~200ms for a second API call) is acceptable given the risk asymmetry.

---

## Summary: Fallback Decision Matrix

| Failure | Payment Type | FraudShield Response | Reasoning |
|---|---|---|---|
| Screening timeout | Card | +20 score, continue | Reversible |
| Screening timeout | Stablecoin | REVIEW + HOLD | Irreversible |
| Sanctions hit | Any | DECLINE | Hard block, no override |
| Travel Rule threshold | Stablecoin | REVIEW + HOLD | Compliance requirement |
| Internal error | Any | HTTP 500, no approval | Fail closed |
| Duplicate transaction_id | Any | Re-evaluates (v0.1 gap) | Idempotency planned for v0.2 |
