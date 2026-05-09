"""
Risk Rules Engine

Each rule is a function that takes a PaymentEvent and returns a (score, detail) tuple.
Score is the points contributed. Detail is the human-readable explanation.

Design principle: rules are independent, composable, and explicit.
No hidden weights. No black box. Every point in the risk score is traceable
to a specific rule and a specific input value.

This matters for two reasons:
1. Regulators need explainable decisions.
2. Fraud analysts need to tune rules without reverse-engineering a model.
"""

from app.models.payment import PaymentEvent, PaymentType
from app.models.decision import TriggeredRule, RuleSeverity
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

# ─── Thresholds ────────────────────────────────────────────────────────────────

TRAVEL_RULE_THRESHOLD_USD = 1_000.00   # FATF Recommendation 16
HIGH_VALUE_CARD_USD = 2_000.00
MEDIUM_VALUE_USD = 500.00

# MCC codes associated with elevated fraud risk
HIGH_RISK_MCC = {"7995", "6051", "6011", "5912", "5999"}

# ─── Rule Functions ─────────────────────────────────────────────────────────────

def rule_travel_rule_threshold(event: PaymentEvent) -> Tuple[int, TriggeredRule | None]:
    """
    FATF Travel Rule: stablecoin transfers >= $1,000 require originator/beneficiary data.
    This is not optional compliance — it's a hard regulatory requirement for VASPs.
    Auto-approve is blocked when this rule fires.
    """
    if event.payment_type != PaymentType.STABLECOIN:
        return 0, None
    if event.amount_usd < TRAVEL_RULE_THRESHOLD_USD:
        return 0, None

    score = 25
    return score, TriggeredRule(
        rule="TRAVEL_RULE_THRESHOLD",
        severity=RuleSeverity.HIGH,
        detail=(
            f"Amount ${event.amount_usd:,.2f} meets or exceeds FATF Travel Rule threshold "
            f"(${TRAVEL_RULE_THRESHOLD_USD:,.0f}). "
            "Originator and beneficiary identifying information required before settlement."
        ),
        score_contribution=score
    )


def rule_sanctions_hit(event: PaymentEvent, screening_result: dict) -> Tuple[int, TriggeredRule | None]:
    """
    Hard block: if wallet screening returns a sanctions hit, decline immediately.
    Score of 100 ensures this cannot be overridden by other rules.
    """
    if event.payment_type != PaymentType.STABLECOIN:
        return 0, None

    risk_score = screening_result.get("risk_score", 0)
    is_sanctioned = screening_result.get("is_sanctioned", False)

    if not is_sanctioned and risk_score < 80:
        return 0, None

    score = 100  # Hard block
    reason = screening_result.get("reason", "Wallet flagged by screening provider")
    return score, TriggeredRule(
        rule="SANCTIONS_HIT",
        severity=RuleSeverity.CRITICAL,
        detail=f"Wallet screening returned high-risk or sanctions match: {reason}",
        score_contribution=score
    )


def rule_screening_timeout(event: PaymentEvent, screening_timed_out: bool) -> Tuple[int, TriggeredRule | None]:
    """
    Critical design decision: timeout handling differs by payment type.

    Card: conservative fallback (+20), continue to decision. Reversible.
    Stablecoin: hard hold. Transaction is irreversible. Timeout ≠ clean screen.

    This is where most fraud engines get it wrong when extended to on-chain payments.
    """
    if not screening_timed_out:
        return 0, None
    if event.payment_type != PaymentType.STABLECOIN:
        score = 20
        return score, TriggeredRule(
            rule="SCREENING_TIMEOUT_CARD",
            severity=RuleSeverity.MEDIUM,
            detail="External enrichment timed out. Conservative +20 applied. Card transaction is reversible.",
            score_contribution=score
        )

    score = 75  # Forces REVIEW at minimum for stablecoin
    return score, TriggeredRule(
        rule="SCREENING_TIMEOUT_STABLECOIN",
        severity=RuleSeverity.HIGH,
        detail=(
            "Wallet screening API timed out. Stablecoin transactions are irreversible — "
            "cannot approve without confirmed screening result. Hold for manual review."
        ),
        score_contribution=score
    )


def rule_high_value_amount(event: PaymentEvent) -> Tuple[int, TriggeredRule | None]:
    """Amount-based risk signal. Applies to both payment types."""
    if event.amount_usd >= HIGH_VALUE_CARD_USD:
        score = 20
        return score, TriggeredRule(
            rule="HIGH_VALUE_TRANSACTION",
            severity=RuleSeverity.MEDIUM,
            detail=f"Transaction amount ${event.amount_usd:,.2f} exceeds high-value threshold ${HIGH_VALUE_CARD_USD:,.0f}.",
            score_contribution=score
        )
    if event.amount_usd >= MEDIUM_VALUE_USD:
        score = 10
        return score, TriggeredRule(
            rule="MEDIUM_VALUE_TRANSACTION",
            severity=RuleSeverity.LOW,
            detail=f"Transaction amount ${event.amount_usd:,.2f} exceeds medium-value threshold ${MEDIUM_VALUE_USD:,.0f}.",
            score_contribution=score
        )
    return 0, None


def rule_high_risk_mcc(event: PaymentEvent) -> Tuple[int, TriggeredRule | None]:
    """MCC-based risk for card transactions. Gambling, crypto exchanges, cash advance."""
    if event.payment_type != PaymentType.CARD or event.merchant is None:
        return 0, None
    if event.merchant.mcc not in HIGH_RISK_MCC:
        return 0, None

    score = 45
    return score, TriggeredRule(
        rule="HIGH_RISK_MCC",
        severity=RuleSeverity.HIGH,
        detail=f"Merchant category code {event.merchant.mcc} is associated with elevated fraud and AML risk.",
        score_contribution=score
    )


def rule_cross_border_stablecoin(event: PaymentEvent) -> Tuple[int, TriggeredRule | None]:
    """
    Stablecoin transfers inherently cross jurisdictions — there's no geographic constraint
    on blockchain transactions. This is a baseline risk signal for all stablecoin events.
    """
    if event.payment_type != PaymentType.STABLECOIN:
        return 0, None

    score = 10
    return score, TriggeredRule(
        rule="STABLECOIN_CROSS_BORDER_BASELINE",
        severity=RuleSeverity.LOW,
        detail=(
            "Stablecoin transfers are jurisdiction-agnostic by nature. "
            "Baseline risk applied pending wallet history and screening results."
        ),
        score_contribution=score
    )
