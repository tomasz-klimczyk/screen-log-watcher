"""Silnik OCR oparty o pytesseract i Tesseract OCR.

Odpowiada za:
- konfigurację ścieżki do binarki tesseract,
- preprocessing obrazu (skala szarości, kontrast, skalowanie, binaryzacja),
- uruchomienie OCR i zwrócenie rozpoznanego tekstu.

Moduł nie wywołuje żadnych funkcji GUI i może być testowany niezależnie.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pytesseract
from PIL import Image, ImageEnhance, ImageOps

from .config import Preprocessing


class OCRError(Exception):
    """Błąd konfiguracji lub uruchomienia OCR (np. brak Tesseract)."""


class OCREngine:
    """Opakowanie wokół pytesseract z obsługą preprocessingu obrazu."""

    def __init__(
        self,
        tesseract_path: str = "",
        language: str = "eng",
        preprocessing: Optional[Preprocessing] = None,
    ) -> None:
        self._tesseract_path = ""
        self._language = language
        self._preprocessing = preprocessing or Preprocessing()
        self._configured = False
        # Jeśli podano ścieżkę w konstruktorze, ustaw ją od razu.
        if tesseract_path:
            self.set_tesseract_path(tesseract_path)

    # ----- Konfiguracja ------------------------------------------------------

    def set_tesseract_path(self, path: str) -> None:
        """Ustawia ścieżkę do binarki tesseract (istotne na Windows)."""
        if path and path != self._tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = path
        self._tesseract_path = path
        self._configured = bool(path)

    def set_language(self, language: str) -> None:
        self._language = language or "eng"

    def set_preprocessing(self, preprocessing: Preprocessing) -> None:
        self._preprocessing = preprocessing

    def verify(self) -> None:
        """Sprawdza, czy Tesseract jest dostępny. Rzuca OCRError, gdy nie."""
        try:
            pytesseract.get_tesseract_version()
        except EnvironmentError as exc:
            raise OCRError(
                "Nie znaleziono Tesseract OCR. Ustaw ścieżkę 'tesseract_path' "
                "w pliku config/config.json. Szczegóły: " + str(exc)
            ) from exc

    # ----- Preprocessing -----------------------------------------------------

    def _preprocess(self, image: Image.Image) -> Image.Image:
        pre = self._preprocessing
        img = image

        if pre.grayscale:
            img = ImageOps.grayscale(img)

        if pre.increase_contrast:
            # Współczynnik > 1 zwiększa kontrast, co często pomaga OCR.
            try:
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.8)
            except Exception:
                pass

        if pre.scale_factor and pre.scale_factor > 1:
            new_size = (img.width * pre.scale_factor, img.height * pre.scale_factor)
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        if pre.binary_threshold and pre.binary_threshold > 0:
            arr = np.array(img)
            if arr.ndim == 2:
                # Binaryzacja: piksele > threshold -> 255, reszta -> 0.
                arr = np.where(arr > pre.binary_threshold, 255, 0).astype(np.uint8)
                img = Image.fromarray(arr, mode="L")

        return img

    # ----- OCR ---------------------------------------------------------------

    def image_to_text(self, image: Image.Image) -> str:
        """Uruchamia OCR i zwraca rozpoznany tekst."""
        try:
            self.verify()
        except OCRError:
            # Próbujemy mimo braku weryfikacji - użytkownik może mieć tesseract w PATH.
            pass

        processed = self._preprocess(image) if self._preprocessing.enabled else image

        try:
            text = pytesseract.image_to_string(processed, lang=self._language)
        except pytesseract.TesseractNotFoundError as exc:
            raise OCRError(
                "Nie znaleziono Tesseract OCR. Dodaj go do PATH lub ustaw "
                "'tesseract_path' w config.json."
            ) from exc
        except Exception as exc:
            raise OCRError(f"Błąd OCR: {exc}") from exc

        return text or ""

    @staticmethod
    def split_lines(text: str) -> list:
        """Dzieli tekst na linie, usuwa puste i białe znaki na końcach."""
        if not text:
            return []
        lines = []
        for raw in text.splitlines():
            stripped = raw.strip()
            if stripped:
                lines.append(stripped)
        return lines
