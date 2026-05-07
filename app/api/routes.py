from fastapi import APIRouter, HTTPException
from app.models.payment import PaymentEvent
from app.models.decision import RiskDecision
from app.core.risk_engine import evaluate

router = APIRouter()


@router.post(
    "/evaluate",
    response_model=RiskDecision,
    summary="Evaluate payment risk",
    description=(
        "Submit a payment event (card or stablecoin) for real-time risk evaluation. "
        "Returns a risk decision with score, triggered rules, and audit reference."
    )
)
async def evaluate_payment(event: PaymentEvent) -> RiskDecision:
    """
    Core endpoint. Accepts both card and stablecoin payment events.
    Returns risk decision synchronously — evaluation target is <500ms.
    """
    try:
        return await evaluate(event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Risk evaluation failed: {str(e)}")


@router.get("/health")
async def health():
    return {"status": "ok", "service": "fraudshield-payment-api"}
