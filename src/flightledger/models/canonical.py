from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SourceSystem(str, Enum):
    PSS = "reservation_pss"
    DCS = "departure_control"
    GDS = "gds_agent_settlement"
    OTA = "ota_partner"
    INTERLINE = "interline_partner"


class CanonicalEventType(str, Enum):
    TICKET_ISSUED = "ticket_issued"
    TICKET_REISSUED = "ticket_reissued"
    TICKET_VOIDED = "ticket_voided"
    COUPON_FLOWN = "coupon_flown"
    REFUND_REQUESTED = "refund_requested"
    SETTLEMENT_DUE = "settlement_due"
    BOOKING_MODIFIED = "booking_modified"
    INTERLINE_CLAIM = "interline_claim"


class CanonicalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_system: SourceSystem
    event_type: CanonicalEventType
    ticket_number: str
    coupon_number: int | None = None
    pnr: str | None = None
    passenger_name: str | None = None
    marketing_carrier: str | None = None
    operating_carrier: str | None = None
    flight_number: str | None = None
    flight_date: date | None = None
    origin: str | None = None
    destination: str | None = None
    currency: str | None = None
    gross_amount: Decimal | None = None
    net_amount: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

