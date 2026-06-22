"""Przechwytywanie prostokątnego obszaru ekranu.

Moduł używa biblioteki `mss`, która jest bardzo szybka i wieloplatformowa.
Główna funkcja `capture_region` zwraca obraz PIL.

Moduł jest celowo odseparowany od OCR i od GUI, aby łatwo było go podmienić
(np. w przyszłości na implementację Linuksa lub inny backend).
"""

from __future__ import annotations

import platform
from typing import Optional

import mss
from PIL import Image

from .models import Region


class CaptureError(Exception):
    """Błąd podczas przechwytywania ekranu."""


class ScreenCapture:
    """Nakładka na bibliotekę mss pozwalająca łatwo przechwytywać Region."""

    def __init__(self) -> None:
        # mss tworzy własne kontekst w każdej operacji, ale trzymamy instancję,
        # aby uniknąć wielokrotnego tworzenia obiektu (zysk wydajności).
        self._sct: Optional[mss.base.MSSBase] = None

    def _get_sct(self) -> mss.base.MSSBase:
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def capture_region(self, region: Region) -> Image.Image:
        """Przechwuje zadany Region i zwraca obraz PIL.Image w trybie RGB."""
        if not region.is_valid():
            raise CaptureError(
                "Nie wybrano poprawnego obszaru ekranu (szerokość i wysokość > 0)."
            )

        monitor = {
            "left": int(region.left),
            "top": int(region.top),
            "width": int(region.width),
            "height": int(region.height),
        }

        sct = self._get_sct()
        try:
            raw = sct.grab(monitor)
        except Exception as exc:  # mss rzuca różne wyjątki zależnie od platformy
            raise CaptureError(f"Błąd przechwytywania ekranu: {exc}") from exc

        # mss zwraca bajty w formacie BGRA - konwertujemy na RGB przez PIL.
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img

    def grab_full_screen(self, monitor_index: int = 0) -> Image.Image:
        """Przechwuje cały ekran o indeksie monitor_index (0 = główny)."""
        sct = self._get_sct()
        monitors = sct.monitors
        if monitor_index < 0 or monitor_index >= len(monitors):
            monitor_index = 1 if len(monitors) > 1 else 0
        mon = monitors[monitor_index]
        raw = sct.grab(mon)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def list_monitors(self) -> list:
        """Zwraca listę dostępnych monitorów (do debugowania/przyszłych funkcji)."""
        return list(self._get_sct().monitors)

    @staticmethod
    def platform_supported() -> bool:
        """Czy aktualna platforma jest wspierana (informacyjnie)."""
        return platform.system() in ("Windows", "Linux", "Darwin")
