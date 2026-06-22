"""Zapis logów i zdarzeń do plików.

Klasy są proste i synchroniczne. Zapis nie powinien być wywoływany w wątku
GUI - pracownik (timer/wątek roboczy) wywołuje storage, zapisując kolejne
linie i zdarzenia.

Formaty:
- lines.log (TXT) - kolejne nowe linie, każda z timestampem.
- lines.csv      - dwie kolumny: timestamp, line.
- events.csv     - pełne informacje o każdym wykrytym zdarzeniu.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import List

from .config import StorageConfig
from .models import DetectedEvent, LogLine


class Storage:
    """Obsługuje zapis logów i zdarzeń do plików."""

    def __init__(self, storage_cfg: StorageConfig, base_dir: str) -> None:
        self.cfg = storage_cfg
        self.base_dir = base_dir
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        os.makedirs(self.logs_dir_abs, exist_ok=True)

    @property
    def logs_dir_abs(self) -> str:
        path = self.cfg.logs_dir
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.base_dir, path))

    @property
    def lines_txt_path(self) -> str:
        return os.path.join(self.logs_dir_abs, self.cfg.lines_file)

    @property
    def lines_csv_path(self) -> str:
        return os.path.join(self.logs_dir_abs, "lines.csv")

    @property
    def events_csv_path(self) -> str:
        return os.path.join(self.logs_dir_abs, self.cfg.events_file)

    # ----- Linie -------------------------------------------------------------

    def save_lines(self, lines: List[LogLine]) -> None:
        if not lines:
            return
        if self.cfg.save_lines_to_txt:
            self._append_txt(lines)
        if self.cfg.save_lines_to_csv:
            self._append_lines_csv(lines)

    def _append_txt(self, lines: List[LogLine]) -> None:
        with open(self.lines_txt_path, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(f"[{line.timestamp.isoformat(timespec='seconds')}] {line.text}\n")

    def _append_lines_csv(self, lines: List[LogLine]) -> None:
        new_file = not os.path.exists(self.lines_csv_path)
        with open(self.lines_csv_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if new_file:
                writer.writerow(["timestamp", "line"])
            for line in lines:
                writer.writerow(
                    [line.timestamp.isoformat(timespec="seconds"), line.text]
                )

    # ----- Zdarzenia ---------------------------------------------------------

    def save_events(self, events: List[DetectedEvent]) -> None:
        if not events or not self.cfg.save_events_to_csv:
            return
        new_file = not os.path.exists(self.events_csv_path)
        with open(self.events_csv_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if new_file:
                writer.writerow(
                    [
                        "timestamp",
                        "category",
                        "severity",
                        "rule_name",
                        "matched_keyword",
                        "original_line",
                        "important",
                    ]
                )
            for ev in events:
                writer.writerow(
                    [
                        ev.timestamp.isoformat(timespec="seconds"),
                        ev.category,
                        ev.severity,
                        ev.rule_name,
                        ev.matched_keyword,
                        ev.original_line,
                        "yes" if ev.important else "no",
                    ]
                )

    # ----- Pomocnicze --------------------------------------------------------

    def export_session_txt(self, lines: List[str], events: List[DetectedEvent], path: str) -> str:
        """Eksportuje bieżącą sesję (linie + zdarzenia) do TXT - przycisk 'Zapisz log'."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"Raport Screen Log Watcher - {datetime.now().isoformat(timespec='seconds')}\n")
            fh.write("=" * 60 + "\n\n")
            fh.write("Wykryte linie:\n")
            for line in lines:
                fh.write(f"- {line}\n")
            fh.write("\nWykryte zdarzenia:\n")
            for ev in events:
                fh.write(
                    f"[{ev.timestamp.isoformat(timespec='seconds')}] "
                    f"[{ev.severity.upper()}] [{ev.category}] "
                    f"{ev.rule_name} :: {ev.original_line}\n"
                )
        return path
