from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="FraudShield Payment Risk Monitor",
    description=(
        "Real-time fraud decisioning API for fiat and stablecoin payment flows. "
        "Demonstrates end-to-end risk evaluation including wallet screening, "
        "Travel Rule compliance, and explainable risk decisions."
    ),
    version="0.1.0",
    contact={
        "name": "Adolfo Mite",
        "url": "https://linkedin.com/in/mitelite",
    }
)

app.include_router(router, prefix="/api/v1")
