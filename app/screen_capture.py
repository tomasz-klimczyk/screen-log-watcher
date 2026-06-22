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
        # Współczynnik skalowania DPI (logical -> physical pixels).
        # Qt podaje współrzędne w pikselach logicznych, mss przechwytuje
        # w pikselach fizycznych - bez tego na ekranach ze skalowaniem
        # (np. 125%, 150%) przechwytywany obszar jest przesunięty/zły.
        self._scale: float = 1.0

    def _get_sct(self) -> mss.base.MSSBase:
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def set_scale(self, scale: float) -> None:
        """Ustawia współczynnik DPI (1.0 = brak skalowania, 1.25/1.5/2.0 = skalowanie)."""
        try:
            s = float(scale)
        except (TypeError, ValueError):
            s = 1.0
        self._scale = s if s and s > 0 else 1.0

    @property
    def scale(self) -> float:
        return self._scale

    def _physical_monitor(self, region: Region) -> dict:
        """Przelicza Region (logical) na współrzędne fizyczne dla mss."""
        s = self._scale
        return {
            "left": int(round(region.left * s)),
            "top": int(round(region.top * s)),
            "width": int(round(region.width * s)),
            "height": int(round(region.height * s)),
        }

    def capture_region(self, region: Region) -> Image.Image:
        """Przechwuje zadany Region i zwraca obraz PIL.Image w trybie RGB."""
        if not region.is_valid():
            raise CaptureError(
                "Nie wybrano poprawnego obszaru ekranu (szerokość i wysokość > 0)."
            )

        monitor = self._physical_monitor(region)

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
