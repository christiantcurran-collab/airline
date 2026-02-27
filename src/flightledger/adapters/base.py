from __future__ import annotations

from abc import ABC, abstractmethod

from flightledger.models.canonical import CanonicalEvent


class Adapter(ABC):
    @abstractmethod
    def parse(self, payload: str) -> list[CanonicalEvent]:
        """Normalize a source payload to canonical events."""

