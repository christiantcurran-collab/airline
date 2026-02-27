from __future__ import annotations

import json

from flightledger.adapters.base import Adapter
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem


class DcsStreamAdapter(Adapter):
    def parse(self, payload: str) -> list[CanonicalEvent]:
        parsed = json.loads(payload)
        records = parsed if isinstance(parsed, list) else [parsed]
        return [
            CanonicalEvent(
                source_system=SourceSystem.DCS,
                event_type=CanonicalEventType.COUPON_FLOWN,
                ticket_number=record["ticket_number"],
                coupon_number=record.get("coupon_number"),
                pnr=record.get("pnr"),
                flight_number=record.get("flight_number"),
                flight_date=record.get("flight_date"),
                origin=record.get("origin"),
                destination=record.get("destination"),
                metadata={
                    "boarded_at": record.get("boarded_at"),
                    "gate": record.get("gate"),
                    "source_record_type": "dcs_json",
                },
            )
            for record in records
        ]

