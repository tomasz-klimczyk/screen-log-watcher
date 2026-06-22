"""Modele danych używane w aplikacji.

Klasy danych są proste (dataclasses) i niezależne od GUI, aby łatwo było
je reużywać oraz testować.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Region:
    """Prostokątny obszar ekranu (w pikselach, współrzędne ekranu)."""

    left: int
    top: int
    width: int
    height: int

    def is_valid(self) -> bool:
        """Zwraca True, jeśli obszar ma sensowny rozmiar (> 0)."""
        return self.width > 0 and self.height > 0

    def to_dict(self) -> dict:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "Region":
        if not data:
            return cls(0, 0, 0, 0)
        return cls(
            left=int(data.get("left", 0)),
            top=int(data.get("top", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
        )


@dataclass
class LogLine:
    """Pojedyncza nowa linia logu rozpoznana przez OCR."""

    text: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DetectedEvent:
    """Zdarzenie wykryte na podstawie reguł analizy logów."""

    timestamp: datetime
    category: str
    severity: str
    rule_name: str
    matched_keyword: str
    original_line: str
    important: bool = False

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "category": self.category,
            "severity": self.severity,
            "rule_name": self.rule_name,
            "matched_keyword": self.matched_keyword,
            "original_line": self.original_line,
            "important": "yes" if self.important else "no",
        }
