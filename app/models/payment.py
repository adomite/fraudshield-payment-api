from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class PaymentType(str, Enum):
    CARD = "card"
    STABLECOIN = "stablecoin"


class CardDetails(BaseModel):
    bin: str = Field(..., min_length=6, max_length=8, description="Bank Identification Number")
    last4: str = Field(..., min_length=4, max_length=4)
    country_of_issue: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2")


class MerchantDetails(BaseModel):
    mcc: str = Field(..., description="Merchant Category Code (ISO 18245)")
    name: str
    country: str = Field(..., min_length=2, max_length=2)


class OnchainDetails(BaseModel):
    sender_wallet: str = Field(..., description="Originator wallet address")
    receiver_wallet: str = Field(..., description="Beneficiary wallet address")
    chain: Literal["ethereum", "polygon", "solana", "tron"] = Field(
        ..., description="Blockchain network"
    )
    token_contract: Optional[str] = Field(
        None, description="ERC-20 or equivalent token contract address"
    )
    tx_hash: Optional[str] = Field(None, description="On-chain transaction hash if available")


class PaymentEvent(BaseModel):
    """
    Unified payment event schema for both card and stablecoin transactions.

    Design decision: a single schema forces explicit handling of both payment types
    at the normalization layer, rather than letting type-specific logic bleed into
    the risk engine. The risk engine receives a PaymentEvent and shouldn't care
    which path it came from.
    """
    payment_type: PaymentType
    transaction_id: str = Field(..., description="Caller-provided idempotency key")
    amount_usd: float = Field(..., gt=0, description="USD equivalent amount")
    currency: str = Field(..., description="ISO 4217 for fiat, token symbol for crypto")
    customer_id: str
    timestamp: datetime
    ip_address: Optional[str] = None
    device_fingerprint: Optional[str] = None

    # Type-specific fields — exactly one must be present
    card: Optional[CardDetails] = None
    merchant: Optional[MerchantDetails] = None
    onchain: Optional[OnchainDetails] = None

    @validator("card", always=True)
    def card_required_for_card_payments(cls, v, values):
        if values.get("payment_type") == PaymentType.CARD and v is None:
            raise ValueError("card details required for payment_type=card")
        return v

    @validator("onchain", always=True)
    def onchain_required_for_stablecoin(cls, v, values):
        if values.get("payment_type") == PaymentType.STABLECOIN and v is None:
            raise ValueError("onchain details required for payment_type=stablecoin")
        return v

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "payment_type": "stablecoin",
                    "transaction_id": "txn_def456",
                    "amount_usd": 1250.00,
                    "currency": "USDC",
                    "customer_id": "cust_002",
                    "timestamp": "2025-05-06T14:31:00Z",
                    "onchain": {
                        "sender_wallet": "0xAbC123def456...",
                        "receiver_wallet": "0xDeF456abc789...",
                        "chain": "ethereum",
                        "token_contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
                    }
                }
            ]
        }
