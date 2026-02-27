from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO

from flightledger.adapters.base import Adapter
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem


class PssCsvAdapter(Adapter):
    def parse(self, payload: str) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        rows = csv.DictReader(StringIO(payload))
        for row in rows:
            event_type = CanonicalEventType(row["event_type"])
            coupon_number = int(row["coupon_number"]) if row.get("coupon_number") else None
            gross = Decimal(row["gross_amount"]) if row.get("gross_amount") else None
            net = Decimal(row["net_amount"]) if row.get("net_amount") else None
            events.append(
                CanonicalEvent(
                    source_system=SourceSystem.PSS,
                    event_type=event_type,
                    ticket_number=row["ticket_number"],
                    coupon_number=coupon_number,
                    pnr=row.get("pnr"),
                    passenger_name=row.get("passenger_name"),
                    marketing_carrier=row.get("marketing_carrier"),
                    operating_carrier=row.get("operating_carrier"),
                    flight_number=row.get("flight_number"),
                    flight_date=row.get("flight_date") or None,
                    origin=row.get("origin"),
                    destination=row.get("destination"),
                    currency=row.get("currency"),
                    gross_amount=gross,
                    net_amount=net,
                    metadata={
                        "source_record_type": "pss_csv",
                        "sales_channel": row.get("sales_channel"),
                    },
                )
            )
        return events
