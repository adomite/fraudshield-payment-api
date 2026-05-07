"""
Risk Evaluation Engine

Orchestrates rule execution and produces a final RiskDecision.

Decision thresholds:
  APPROVE  → score < 40, no hard blocks
  REVIEW   → score 40–74, OR Travel Rule triggered, OR screening timeout on stablecoin
  DECLINE  → score >= 75, OR sanctions hit, OR critical rule fired
"""

import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from app.models.payment import PaymentEvent, PaymentType
from app.models.decision import RiskDecision, DecisionOutcome, FallbackBehavior, TriggeredRule
from app.core.rules import (
    rule_travel_rule_threshold,
    rule_sanctions_hit,
    rule_screening_timeout,
    rule_high_value_amount,
    rule_high_risk_mcc,
    rule_cross_border_stablecoin,
)
from app.integrations.trm_labs import screen_wallet

logger = logging.getLogger(__name__)

APPROVE_THRESHOLD = 40
DECLINE_THRESHOLD = 75


async def evaluate(event: PaymentEvent) -> RiskDecision:
    start_time = time.monotonic()

    triggered_rules: list[TriggeredRule] = []
    total_score = 0
    screening_result = {}
    screening_status = "NOT_APPLICABLE"
    screening_timed_out = False

    # ── Wallet screening for stablecoin payments ──────────────────────────────
    if event.payment_type == PaymentType.STABLECOIN and event.onchain:
        screening_status, screening_result, screening_timed_out = await screen_wallet(
            event.onchain.sender_wallet
        )

    # ── Apply rules ───────────────────────────────────────────────────────────
    rules_to_run = [
        rule_travel_rule_threshold(event),
        rule_sanctions_hit(event, screening_result),
        rule_screening_timeout(event, screening_timed_out),
        rule_high_value_amount(event),
        rule_high_risk_mcc(event),
        rule_cross_border_stablecoin(event),
    ]

    for score, rule in rules_to_run:
        if rule is not None:
            triggered_rules.append(rule)
            total_score += score

    total_score = min(total_score, 100)

    # ── Determine decision ────────────────────────────────────────────────────
    travel_rule_applicable = any(r.rule == "TRAVEL_RULE_THRESHOLD" for r in triggered_rules)
    sanctions_hit = any(r.rule == "SANCTIONS_HIT" for r in triggered_rules)
    stablecoin_timeout = any(r.rule == "SCREENING_TIMEOUT_STABLECOIN" for r in triggered_rules)

    decision, fallback = _resolve_decision(
        total_score, travel_rule_applicable, sanctions_hit, stablecoin_timeout
    )

    # ── Build decision record ─────────────────────────────────────────────────
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    audit_id = f"aud_{uuid.uuid4().hex[:8]}"
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"

    risk_decision = RiskDecision(
        decision_id=decision_id,
        transaction_id=event.transaction_id,
        decision=decision,
        risk_score=total_score,
        triggered_rules=triggered_rules,
        fallback_behavior=fallback,
        screening_status=screening_status,
        travel_rule_applicable=travel_rule_applicable,
        evaluated_at=datetime.now(timezone.utc),
        evaluation_latency_ms=elapsed_ms,
        audit_id=audit_id,
    )

    logger.info(
        "risk_decision",
        extra={
            "transaction_id": event.transaction_id,
            "decision": decision,
            "score": total_score,
            "rules_fired": len(triggered_rules),
            "latency_ms": elapsed_ms,
        }
    )

    return risk_decision


def _resolve_decision(
    score: int,
    travel_rule: bool,
    sanctions_hit: bool,
    stablecoin_timeout: bool
) -> tuple[DecisionOutcome, FallbackBehavior]:
    """
    Decision resolution logic. Order matters — hard blocks evaluated first.
    """
    if sanctions_hit:
        return DecisionOutcome.DECLINE, FallbackBehavior.AUTO_DECLINED_SANCTIONS

    if score >= DECLINE_THRESHOLD:
        return DecisionOutcome.DECLINE, FallbackBehavior.NONE

    if stablecoin_timeout:
        return DecisionOutcome.REVIEW, FallbackBehavior.HOLD_PENDING_SCREENING

    if travel_rule:
        return DecisionOutcome.REVIEW, FallbackBehavior.HOLD_FOR_COMPLIANCE_REVIEW

    if score >= APPROVE_THRESHOLD:
        return DecisionOutcome.REVIEW, FallbackBehavior.NONE

    return DecisionOutcome.APPROVE, FallbackBehavior.NONE
