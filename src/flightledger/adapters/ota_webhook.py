from __future__ import annotations

import json
from decimal import Decimal

from flightledger.adapters.base import Adapter
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem


class OtaWebhookAdapter(Adapter):
    def parse(self, payload: str) -> list[CanonicalEvent]:
        body = json.loads(payload)
        bookings = body if isinstance(body, list) else [body]
        events: list[CanonicalEvent] = []
        for booking in bookings:
            raw_event_type = booking.get("event_type", CanonicalEventType.BOOKING_MODIFIED.value)
            event_type = CanonicalEventType(raw_event_type)
            events.append(
                CanonicalEvent(
                    source_system=SourceSystem.OTA,
                    event_type=event_type,
                    ticket_number=booking["ticket_number"],
                    pnr=booking.get("pnr"),
                    passenger_name=booking.get("passenger_name"),
                    flight_number=booking.get("flight_number"),
                    flight_date=booking.get("flight_date"),
                    origin=booking.get("origin"),
                    destination=booking.get("destination"),
                    currency=booking.get("currency"),
                    gross_amount=Decimal(str(booking["gross_amount"])) if booking.get("gross_amount") else None,
                    net_amount=Decimal(str(booking["net_amount"])) if booking.get("net_amount") else None,
                    metadata={
                        "ota": booking.get("ota"),
                        "status": booking.get("status"),
                        "source_record_type": "ota_webhook_json",
                    },
                )
            )
        return events

