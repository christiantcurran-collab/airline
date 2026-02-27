from __future__ import annotations

import json
from decimal import Decimal

from flightledger.adapters.base import Adapter
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem


class InterlineRestAdapter(Adapter):
    def parse(self, payload: str) -> list[CanonicalEvent]:
        body = json.loads(payload)
        claims = body.get("claims", []) if isinstance(body, dict) else body
        events: list[CanonicalEvent] = []
        for claim in claims:
            events.append(
                CanonicalEvent(
                    source_system=SourceSystem.INTERLINE,
                    event_type=CanonicalEventType.INTERLINE_CLAIM,
                    ticket_number=claim["ticket_number"],
                    coupon_number=claim.get("coupon_number"),
                    currency=claim.get("currency"),
                    gross_amount=Decimal(str(claim["claim_amount"])) if claim.get("claim_amount") else None,
                    metadata={
                        "partner_carrier": claim.get("partner_carrier"),
                        "claim_id": claim.get("claim_id"),
                        "claim_status": claim.get("claim_status"),
                        "source_record_type": "interline_rest_json",
                    },
                )
            )
        return events

