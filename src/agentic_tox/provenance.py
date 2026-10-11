"""Provenance records.

Every fact this demo prints carries one of these. A fact without a record is a
bug, not a shortcut: the point of the exercise is that an agent's answer can be
checked line by line against a named source.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def now() -> str:
    """UTC timestamp, second resolution, for the moment a fact was obtained."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Source:
    """Where a fact came from."""

    kind: str  # "dataset" | "api" | "model"
    name: str
    version: str
    url: str
    retrieved_at: str = field(default_factory=now)
    digest: str = ""  # sha256 or md5 of the bytes actually used, when there are bytes
    detail: dict = field(default_factory=dict)

    def line(self) -> str:
        bits = [f"{self.kind}={self.name}", f"version={self.version}"]
        if self.digest:
            bits.append(f"digest={self.digest[:16]}...")
        bits.append(f"retrieved={self.retrieved_at}")
        bits.append(self.url)
        return "   provenance: " + "  ".join(bits)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Fact:
    """One statement plus the source that supports it."""

    statement: str
    source: Source
    value: object = None

    def lines(self) -> list[str]:
        return [f" - {self.statement}", self.source.line()]

    def to_dict(self) -> dict:
        return {"statement": self.statement, "value": self.value, "source": self.source.to_dict()}
