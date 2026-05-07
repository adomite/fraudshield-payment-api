from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class DecisionOutcome(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    DECLINE = "DECLINE"


class FallbackBehavior(str, Enum):
    NONE = "NONE"
    HOLD_FOR_COMPLIANCE_REVIEW = "HOLD_FOR_COMPLIANCE_REVIEW"
    HOLD_PENDING_SCREENING = "HOLD_PENDING_SCREENING"
    AUTO_DECLINED_SANCTIONS = "AUTO_DECLINED_SANCTIONS"
    AUTO_DECLINED_VELOCITY = "AUTO_DECLINED_VELOCITY"


class RuleSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TriggeredRule(BaseModel):
    rule: str = Field(..., description="Rule identifier")
    severity: RuleSeverity
    detail: str = Field(..., description="Human-readable explanation of why this rule fired")
    score_contribution: int = Field(..., description="Points this rule added to risk score")


class RiskDecision(BaseModel):
    """
    The complete output of the risk evaluation for a single payment event.

    Every field exists to serve one purpose: make the decision explainable.
    A fraud decision that can't be explained is a liability — for the customer,
    for operations, and for regulators.
    """
    decision_id: str
    transaction_id: str
    decision: DecisionOutcome
    risk_score: int = Field(..., ge=0, le=100, description="Composite risk score 0-100")
    triggered_rules: List[TriggeredRule]
    fallback_behavior: FallbackBehavior = FallbackBehavior.NONE
    screening_status: Optional[str] = Field(
        None,
        description="Wallet screening result: CLEAN, FLAGGED, TIMEOUT, NOT_APPLICABLE"
    )
    travel_rule_applicable: bool = Field(
        False,
        description="True if FATF Travel Rule threshold was met (>=$1,000 USDC equivalent)"
    )
    evaluated_at: datetime
    evaluation_latency_ms: Optional[int] = None
    audit_id: str

    class Config:
        json_schema_extra = {
            "example": {
                "decision_id": "dec_789xyz",
                "transaction_id": "txn_def456",
                "decision": "REVIEW",
                "risk_score": 62,
                "triggered_rules": [
                    {
                        "rule": "TRAVEL_RULE_THRESHOLD",
                        "severity": "HIGH",
                        "detail": "Amount $1,250 exceeds FATF $1,000 threshold. Originator/beneficiary data required.",
                        "score_contribution": 25
                    }
                ],
                "fallback_behavior": "HOLD_FOR_COMPLIANCE_REVIEW",
                "screening_status": "CLEAN",
                "travel_rule_applicable": True,
                "evaluated_at": "2025-05-06T14:31:00.412Z",
                "evaluation_latency_ms": 312,
                "audit_id": "aud_101112"
            }
        }
