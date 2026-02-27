from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal

from flightledger.adapters.base import Adapter
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem


class GdsXmlAdapter(Adapter):
    def parse(self, payload: str) -> list[CanonicalEvent]:
        root = ET.fromstring(payload)
        events: list[CanonicalEvent] = []
        for node in root.findall(".//record"):
            gross_amount = node.findtext("gross_amount")
            net_amount = node.findtext("net_amount")
            events.append(
                CanonicalEvent(
                    source_system=SourceSystem.GDS,
                    event_type=CanonicalEventType.SETTLEMENT_DUE,
                    ticket_number=node.findtext("ticket_number", ""),
                    coupon_number=int(node.findtext("coupon_number")) if node.findtext("coupon_number") else None,
                    currency=node.findtext("currency"),
                    gross_amount=Decimal(gross_amount) if gross_amount else None,
                    net_amount=Decimal(net_amount) if net_amount else None,
                    metadata={
                        "gds": node.findtext("gds"),
                        "settlement_week": node.findtext("settlement_week"),
                        "source_record_type": "gds_xml",
                    },
                )
            )
        return events

