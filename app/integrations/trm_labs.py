"""
TRM Labs Wallet Screening Integration

TRM Labs is an industry-standard blockchain intelligence provider used by
financial institutions, exchanges, and payment processors for on-chain risk.

This module wraps the TRM Labs /v2/screening/addresses endpoint.
Sandbox API key works for development — see https://www.trmlabs.com/

Design decisions:
- Timeout is set to 3s. For stablecoin transactions, a timeout is treated
  as a hard hold downstream (not a soft approve). See risk_engine.py.
- We screen the SENDER wallet. In a full implementation, both sender and
  receiver would be screened — receiver screening catches money mule patterns.
- Response is normalized to a simple dict so the rules engine doesn't
  depend on TRM Labs' specific response shape.
"""

import httpx
import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

TRM_API_BASE = "https://api.trmlabs.com"
TRM_API_KEY = os.getenv("TRM_LABS_API_KEY", "")
SCREENING_TIMEOUT_SECONDS = 3.0


async def screen_wallet(wallet_address: str) -> Tuple[str, dict, bool]:
    """
    Screen a wallet address against TRM Labs risk intelligence.

    Returns:
        screening_status: "CLEAN" | "FLAGGED" | "TIMEOUT" | "ERROR"
        screening_result: normalized risk dict
        timed_out: bool
    """
    if not TRM_API_KEY:
        logger.warning("TRM_LABS_API_KEY not set — returning mock CLEAN result")
        return _mock_clean_result()

    try:
        async with httpx.AsyncClient(timeout=SCREENING_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{TRM_API_BASE}/v2/screening/addresses",
                headers={
                    "Authorization": f"Basic {TRM_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=[{"address": wallet_address, "chain": "ethereum"}]
            )
            response.raise_for_status()
            data = response.json()
            return _normalize_trm_response(data, wallet_address)

    except httpx.TimeoutException:
        logger.warning(f"TRM Labs screening timed out for wallet {wallet_address[:10]}...")
        return "TIMEOUT", {}, True

    except httpx.HTTPStatusError as e:
        logger.error(f"TRM Labs API error: {e.response.status_code}")
        return "ERROR", {}, False

    except Exception as e:
        logger.error(f"Unexpected screening error: {str(e)}")
        return "ERROR", {}, False


def _normalize_trm_response(data: list, wallet_address: str) -> Tuple[str, dict, bool]:
    """
    Normalize TRM Labs response to a shape the risk engine can use
    without knowing TRM Labs' internal schema.
    """
    if not data:
        return "CLEAN", {"risk_score": 0, "is_sanctioned": False}, False

    result = data[0]
    risk_score = result.get("riskIndicators", [{}])
    is_sanctioned = any(
        r.get("ruleName", "").lower().contains("sanction")
        for r in result.get("riskIndicators", [])
        if isinstance(r, dict)
    ) if result.get("riskIndicators") else False

    # TRM uses categoryRiskScoreLevelLabel: LOW | MEDIUM | HIGH | SEVERE
    severity_label = result.get("categoryRiskScoreLevelLabel", "LOW")
    severity_map = {"LOW": 10, "MEDIUM": 40, "HIGH": 70, "SEVERE": 95}
    numeric_score = severity_map.get(severity_label, 10)

    normalized = {
        "risk_score": numeric_score,
        "is_sanctioned": is_sanctioned,
        "severity": severity_label,
        "reason": result.get("categoryRiskScoreDetails", ""),
        "wallet": wallet_address,
    }

    status = "FLAGGED" if numeric_score >= 70 or is_sanctioned else "CLEAN"
    return status, normalized, False


def _mock_clean_result() -> Tuple[str, dict, bool]:
    """Used when no API key is configured (local dev without credentials)."""
    return "CLEAN", {"risk_score": 5, "is_sanctioned": False, "reason": "mock"}, False
