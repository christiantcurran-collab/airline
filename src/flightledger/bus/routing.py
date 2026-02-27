from __future__ import annotations

from flightledger.models.canonical import CanonicalEventType


EVENT_TOPIC_MAP = {
    CanonicalEventType.TICKET_ISSUED: "ticket.issued",
    CanonicalEventType.TICKET_REISSUED: "ticket.issued",
    CanonicalEventType.TICKET_VOIDED: "ticket.issued",
    CanonicalEventType.COUPON_FLOWN: "coupon.flown",
    CanonicalEventType.REFUND_REQUESTED: "refund.requested",
    CanonicalEventType.SETTLEMENT_DUE: "settlement.due",
    CanonicalEventType.BOOKING_MODIFIED: "booking.modified",
    CanonicalEventType.INTERLINE_CLAIM: "settlement.due",
}

