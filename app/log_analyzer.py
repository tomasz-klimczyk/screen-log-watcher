"""Analiza logów - dopasowywanie linii do reguł słów kluczowych.

Moduł dostaje listę reguł (config.Rule) i dla każdej linii sprawdza, czy
pasuje do którejś reguły (case-insensitive). Jeśli tak, tworzy DetectedEvent.

Mechanizm deduplikacji: porównujemy nowe linie z ostatnio widzianymi.
OCR czasem czyta linię trochę inaczej, więc używamy prostego podobieństwa
(oparte na zbiorach słów / normalizacji).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Set, Tuple

from .config import Rule
from .models import DetectedEvent


def _normalize(line: str) -> str:
    """Normalizuje linię: lowercase, usunięcie znaków nie-alfanumerycznych."""
    # Usuwamy wszystko, co nie jest literą/cyfrą/spacją.
    cleaned = re.sub(r"[^a-z0-9\s]", " ", line.lower())
    # Sklejamy podwójne spacje.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _line_signature(line: str) -> Set[str]:
    """Zwraca zbiór słów znormalizowanej linii - używany do deduplikacji.

    Dzięki temu OCR, który np. przeczyta "ERROR: foo" raz, a raz "ERROR:foo",
    potraktuje je jako podobne (oba zawierają te same słowa).
    """
    return set(_normalize(line).split())


def _lines_similar(a: str, b: str, threshold: float = 0.8) -> bool:
    """Czy dwie linie są na tyle podobne, że uznać je za tę samą?

    Jaccard similarity na zbiorach słów + dodatkowe sprawdzenie pełnej
    normalizacji (gdy OCR zmieni tylko interpunkcję).
    """
    if _normalize(a) == _normalize(b):
        return True
    sa = _line_signature(a)
    sb = _line_signature(b)
    if not sa and not sb:
        return True
    if not sa or not sb:
        return False
    inter = len(sa & sb)
    union = len(sa | sb)
    if union == 0:
        return False
    return (inter / union) >= threshold


class LogAnalyzer:
    """Przechowuje reguły i sprawdza, czy nowe linie pasują do reguł."""

    def __init__(self, rules: List[Rule]) -> None:
        self.rules = rules
        # Ostatnio widziane linie (oryginalny tekst) - do deduplikacji.
        self._seen_lines: List[str] = []

    def reset(self) -> None:
        """Czyści pamięć widzianych linii."""
        self._seen_lines = []

    def filter_new_lines(self, lines: List[str]) -> List[str]:
        """Zwraca tylko te linie, których nie widzieliśmy wcześniej.

        Linia jest 'nowa', jeśli nie jest podobna do żadnej z ostatnio
        zapamiętanych. Zapamiętujemy wszystkie widziane linie (MVP - w pełni
        działające, ograniczone pamięcią programu).
        """
        new_lines: List[str] = []
        for line in lines:
            # Linia jest 'nowa', jeśli nie jest podobna do niczego, co już
            # widzieliśmy (w tej lub poprzednich partiach).
            is_new = not any(_lines_similar(line, seen) for seen in self._seen_lines)
            if is_new:
                new_lines.append(line)
            # Każdą widzianą linię zapamiętujemy od razu, aby kolejne
            # duplikaty w tej samej partii też zostały odfiltrowane.
            self._seen_lines.append(line)
        return new_lines

    def analyze(self, line: str) -> List[DetectedEvent]:
        """Zwraca listę zdarzeń pasujących do danej linii (zazwyczaj 0 lub 1)."""
        events: List[DetectedEvent] = []
        normalized = _normalize(line)
        if not normalized:
            return events
        for rule in self.rules:
            matched = self._match_rule(rule, normalized)
            if matched is not None:
                events.append(
                    DetectedEvent(
                        timestamp=datetime.now(),
                        category=rule.category,
                        severity=rule.severity,
                        rule_name=rule.name,
                        matched_keyword=matched,
                        original_line=line,
                        important=rule.severity == "critical",
                    )
                )
        return events

    @staticmethod
    def _match_rule(rule: Rule, normalized_line: str) -> None | str:
        """Zwraca dopasowane słowo kluczowe lub None."""
        for kw in rule.keywords:
            kw_norm = _normalize(kw)
            if not kw_norm:
                continue
            if kw_norm in normalized_line:
                return kw
        return None

    def analyze_lines(self, lines: List[str]) -> Tuple[List[str], List[DetectedEvent]]:
        """Wygodna metoda: filtruje nowe linie i analizuje je pod kątem reguł."""
        new_lines = self.filter_new_lines(lines)
        events: List[DetectedEvent] = []
        for line in new_lines:
            events.extend(self.analyze(line))
        return new_lines, events
