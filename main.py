"""Punkt wejścia aplikacji Screen Log Watcher.

Uruchamia aplikację PySide6, wczytuje konfigurację z config/config.json oraz
reguły z config/rules.json i wyświetla główne okno.

Użycie:
    python main.py
"""

from __future__ import annotations

import os
import sys
import traceback


def _enable_dpi_awareness() -> None:
    """Ustawia per-monitor DPI awareness na Windows (przed PySide6!).

    Bez tego Qt widzi często tylko główny monitor (reszta jest niewidoczna),
    a zrzuty ekranu mają niską rozdzielczość i są przesunięte. Świadomość DPI
    musi być ustawiona PRZED utworzeniem QApplication / pierwszym użyciem GUI.

    Kolejno próbujemy nowszego SetProcessDpiAwarenessContext (PER_MONITOR_AWARE_V2,
    Windows 10 1703+), starszego SetProcessDpiAwareness oraz SetProcessDPIAware.
    """
    if sys.platform != "win32":
        return
    import ctypes

    # Sposób 1: SetProcessDpiAwarenessContext (-4 = PER_MONITOR_AWARE_V2).
    try:
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_bool
        if fn(-4):
            return
    except Exception:
        pass
    # Sposób 2: SetProcessDpiAwareness (2 = PER_MONITOR_AWARE).
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    # Sposób 3: SetProcessDPIAware (najstarsze API).
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# KLUCZOWE: wywołujemy PRZED jakimkolwiek importem PySide6 / tworzeniem QApplication.
_enable_dpi_awareness()


def _project_base_dir() -> str:
    """Zwraca katalog, w którym znajduje się ten plik main.py."""
    return os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    base_dir = _project_base_dir()
    config_path = os.path.join(base_dir, "config", "config.json")
    rules_path = os.path.join(base_dir, "config", "rules.json")

    # PySide6 musi być importowany dopiero tutaj - dzięki temu funkcja main()
    # może być wywołana z czystym tracebackiem w razie braku zależności.
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        sys.stderr.write(
            "Brak biblioteki PySide6. Zainstaluj zależności:\n"
            "    pip install -r requirements.txt\n"
        )
        return 2

    from app.config import AppConfig
    from app.gui import MainWindow
    from app.ocr_engine import OCREngine, OCRError

    # Wczytanie konfiguracji (próba utworzenia domyślnej, jeśli brak pliku).
    try:
        config = AppConfig.load(config_path, rules_path)
    except Exception as exc:
        sys.stderr.write(f"Błąd wczytywania konfiguracji: {exc}\n")
        return 3

    # Aplikacja Qt - High DPI jest domyślnie włączone w PySide6 >= 6.
    app = QApplication(sys.argv)
    app.setApplicationName("Screen Log Watcher")

    window = MainWindow(config, base_dir, config_path, rules_path)
    window.show()

    # Sprawdzenie dostępności Tesseracta - tylko informacyjnie w statusie.
    try:
        OCREngine(config.tesseract_path, config.ocr_language).verify()
    except OCRError as exc:
        window.status_bar.showMessage(
            "UWAGA: Tesseract OCR nie został znaleziony. "
            "Ustaw ścieżkę w konfiguracji.",
            8000,
        )

    try:
        return app.exec()
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
