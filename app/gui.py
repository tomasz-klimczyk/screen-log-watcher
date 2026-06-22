"""Interfejs graficzny aplikacji (PySide6).

Zawiera:
- RegionSelector - przezroczysta nakładka pełnoekranowa do zaznaczania obszaru,
- OCRWorker - wątek roboczy wykonujący zrzut+OCR+analizę bez blokowania GUI,
- MainWindow - główne okno aplikacji.

Wszystkie długotrwałe operacje (przechwytywanie, OCR) są wykonywane w wątku
roboczym, więc interfejs pozostaje responsywny.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import List

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    QThread,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig
from .log_analyzer import LogAnalyzer
from .models import DetectedEvent, LogLine, Region
from .ocr_engine import OCREngine, OCRError
from .screen_capture import CaptureError, ScreenCapture
from .storage import Storage


# ============================================================================
# RegionSelector - przezroczysta nakładka do zaznaczania obszaru ekranu
# ============================================================================


class RegionSelector(QWidget):
    """Pełnoekranowa przezroczysta nakładka.

    Użytkownik przeciąga myszką prostokąt. Po zwolnieniu emituje sygnał
    region_selected z wybranym Regionem (współrzędne ekranu). ESC anuluje.
    """

    region_selected = Signal(object)  # Region lub None

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._origin = None
        self._current = None

        # Nakładka musi pokrywać wszystkie monitory - bierzemy wirtualny pulpit.
        screen_geo = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(screen_geo)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._cancel)

    def _cancel(self) -> None:
        self.region_selected.emit(None)
        self.close()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
            end = event.position().toPoint()
            start = self._origin
            self._origin = None
            self._current = None

            # Współrzędne QWidget są względem tego widgeta (który pokrywa pulpit),
            # więc bezpośrednio dają nam globalne współrzędne ekranu.
            left = min(start.x(), end.x())
            top = min(start.y(), end.y())
            width = abs(end.x() - start.x())
            height = abs(end.y() - start.y())

            region = Region(left, top, width, height)
            if region.is_valid():
                self.region_selected.emit(region)
            else:
                self.region_selected.emit(None)
            self.close()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # Półprzezroczysta ciemna maska na cały ekran.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        # Instrukcja na górze ekranu.
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(0, 30, 0, 0),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "Zaznacz obszar logów myszką. ESC = anuluj.",
        )

        # Rysujemy zaznaczony prostokąt na bieżąco.
        if self._origin is not None and self._current is not None:
            rect = self._make_rect(self._origin, self._current)
            # "Wycinamy" wybrany obszar z maski - rysujemy go przezroczyście
            # i obrysowujemy jaskrawą ramką.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(0, 200, 255), 2)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.GlobalColor.transparent))
            painter.drawRect(rect)
            # Wymiary tekstowo.
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(
                rect.adjusted(0, -22, 0, 0),
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                f"{rect.width()} x {rect.height()}",
            )

    @staticmethod
    def _make_rect(p1, p2):
        from PySide6.QtCore import QRect

        return QRect(
            min(p1.x(), p2.x()),
            min(p1.y(), p2.y()),
            abs(p2.x() - p1.x()),
            abs(p2.y() - p1.y()),
        )


# ============================================================================
# OCRWorker - wątek roboczy wykonujący zrzut + OCR + analizę
# ============================================================================


class OCRWorker(QObject):
    """Wątek roboczy wykonujący pełen cykl: capture -> OCR -> analyze.

    Komunikuje się z GUI wyłącznie przez sygnały (Qt jest bezpieczne między
    wątkami dla sygnałów/slotów).
    """

    # Sygnały:
    ocr_text = Signal(str)              # pełen rozpoznany tekst (pojedynczy test)
    new_lines = Signal(list)            # list[LogLine]
    new_events = Signal(list)           # list[DetectedEvent]
    preview = Signal(object)            # QPixmap
    error = Signal(str)                 # komunikat błędu
    status = Signal(str)                # krótki status
    finished_cycle = Signal(str)        # timestamp ostatniego cyklu
    trigger_run_once = Signal()         # wyzwolenie pojedynczego cyklu (z GUI)

    def __init__(
        self,
        config: AppConfig,
        base_dir: str,
        config_path: str,
        rules_path: str,
    ) -> None:
        super().__init__()
        self.config = config
        self.base_dir = base_dir
        self.config_path = config_path
        self.rules_path = rules_path
        self._running = False

        self._capture = ScreenCapture()
        self._ocr = OCREngine(
            tesseract_path=config.tesseract_path,
            language=config.ocr_language,
            preprocessing=config.preprocessing,
        )
        self._analyzer = LogAnalyzer(config.rules)
        self._storage = Storage(config.storage, base_dir)

    # ----- Sterowanie --------------------------------------------------------

    def update_config(self, config: AppConfig) -> None:
        """Aktualizuje konfigurację z poziomu GUI (z wątku głównego)."""
        self.config = config
        self._ocr.set_tesseract_path(config.tesseract_path)
        self._ocr.set_language(config.ocr_language)
        self._ocr.set_preprocessing(config.preprocessing)
        self._analyzer = LogAnalyzer(config.rules)

    def reset_memory(self) -> None:
        self._analyzer.reset()

    @Slot()
    def run_once(self) -> None:
        """Pojedynczy zrzut + OCR (używane przez 'Test OCR' i monitor)."""
        try:
            image = self._capture.capture_region(self.config.region)
        except CaptureError as exc:
            self.error.emit(str(exc))
            self.status.emit("Brak obszaru")
            return

        self._emit_preview(image)

        timer = QElapsedTimer()
        timer.start()
        try:
            text = self._ocr.image_to_text(image)
        except OCRError as exc:
            self.error.emit(str(exc))
            self.status.emit("Błąd OCR")
            return
        except Exception as exc:
            self.error.emit(f"Nieoczekiwany błąd OCR: {exc}")
            self.status.emit("Błąd OCR")
            return

        self.ocr_text.emit(text)
        elapsed = timer.elapsed()

        all_lines = self._ocr.split_lines(text)
        if not all_lines:
            self.status.emit(f"OCR OK (brak tekstu, {elapsed} ms)")
            return

        new_lines_text, events = self._analyzer.analyze_lines(all_lines)

        # Zapis logów.
        log_lines = [LogLine(text=t) for t in new_lines_text]
        self._storage.save_lines(log_lines)
        self._storage.save_events(events)

        if new_lines_text:
            self.new_lines.emit(log_lines)
        if events:
            self.new_events.emit(events)

        self.finished_cycle.emit(datetime.now().isoformat(timespec="seconds"))
        self.status.emit(f"OCR OK ({elapsed} ms, +{len(new_lines_text)} nowych)")

    def _emit_preview(self, image) -> None:
        """Konwertuje PIL.Image na QPixmap i emituje."""
        try:
            from PIL import ImageQt

            qimage = ImageQt.ImageQt(image.convert("RGBA"))
            pixmap = QPixmap.fromImage(qimage)
            self.preview.emit(pixmap)
        except Exception:
            # Podgląd jest opcjonalny - nie przerywamy pracy.
            pass


# ============================================================================
# MainWindow
# ============================================================================


class MainWindow(QMainWindow):
    """Główne okno aplikacji Screen Log Watcher."""

    def __init__(self, config: AppConfig, base_dir: str, config_path: str, rules_path: str) -> None:
        super().__init__()
        self.config = config
        self.base_dir = base_dir
        self.config_path = config_path
        self.rules_path = rules_path

        self.setWindowTitle("Screen Log Watcher")
        self.resize(1100, 760)

        self._worker = OCRWorker(config, base_dir, config_path, rules_path)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._monitor_timer = None  # QTimer do cyklicznego OCR
        self._error_count = 0
        self._warning_count = 0

        self._build_ui()
        self._connect_signals()
        self._refresh_region_label()
        self._refresh_status_text("Zatrzymano")

    # ----- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)

        # --- Górny pasek przycisków ---
        top = QHBoxLayout()

        self.btn_select = QPushButton("Wybierz obszar")
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_test_ocr = QPushButton("Test OCR")
        self.btn_clear = QPushButton("Wyczyść wyniki")
        self.btn_save = QPushButton("Zapisz log")

        top.addWidget(self.btn_select)
        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_test_ocr)
        top.addStretch(1)
        top.addWidget(self.btn_clear)
        top.addWidget(self.btn_save)
        root.addLayout(top)

        # --- Sekcja konfiguracji ---
        cfg_group = QGroupBox("Konfiguracja")
        cfg_layout = QVBoxLayout(cfg_group)

        region_row = QHBoxLayout()
        region_row.addWidget(QLabel("Obszar (L, T, W, H):"))
        self.lbl_region = QLabel("-")
        self.lbl_region.setStyleSheet("font-family: monospace;")
        region_row.addWidget(self.lbl_region, 1)
        cfg_layout.addLayout(region_row)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("Interwał (s):"))
        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setRange(0.2, 60.0)
        self.spin_interval.setSingleStep(0.5)
        self.spin_interval.setValue(self.config.interval_seconds)
        interval_row.addWidget(self.spin_interval)

        interval_row.addWidget(QLabel("Język OCR:"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["eng", "pol", "eng+pol"])
        self.combo_lang.setCurrentText(self.config.ocr_language)
        interval_row.addWidget(self.combo_lang)

        interval_row.addWidget(QLabel("Skala:"))
        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 4)
        self.spin_scale.setValue(self.config.preprocessing.scale_factor)
        interval_row.addWidget(self.spin_scale)

        self.chk_preprocess = QCheckBox("Preprocessing")
        self.chk_preprocess.setChecked(self.config.preprocessing.enabled)
        interval_row.addWidget(self.chk_preprocess)

        interval_row.addStretch(1)
        cfg_layout.addLayout(interval_row)

        tesseract_row = QHBoxLayout()
        tesseract_row.addWidget(QLabel("Tesseract path:"))
        self.edit_tesseract = QLineEdit(self.config.tesseract_path)
        self.edit_tesseract.setPlaceholderText("np. C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
        tesseract_row.addWidget(self.edit_tesseract, 1)
        self.btn_browse_tesseract = QPushButton("...")
        self.btn_browse_tesseract.setMaximumWidth(30)
        tesseract_row.addWidget(self.btn_browse_tesseract)
        cfg_layout.addLayout(tesseract_row)

        root.addWidget(cfg_group)

        # --- Sekcja podglądu i statystyk ---
        mid = QHBoxLayout()

        preview_box = QGroupBox("Podgląd obszaru")
        preview_layout = QVBoxLayout(preview_box)
        self.lbl_preview = QLabel("Brak podglądu")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setMinimumSize(360, 200)
        self.lbl_preview.setStyleSheet("background: #222; color: #aaa;")
        preview_layout.addWidget(self.lbl_preview)
        self.lbl_preview_note = QLabel("OCR: nie testowano")
        preview_layout.addWidget(self.lbl_preview_note)
        mid.addWidget(preview_box)

        stats_box = QGroupBox("Status")
        stats_layout = QVBoxLayout(stats_box)
        self.lbl_status_value = QLabel("Zatrzymano")
        f = self.lbl_status_value.font()
        f.setPointSize(12)
        f.setBold(True)
        self.lbl_status_value.setFont(f)
        stats_layout.addWidget(self.lbl_status_value)
        self.lbl_last_read = QLabel("Ostatni odczyt: -")
        stats_layout.addWidget(self.lbl_last_read)
        self.lbl_counters = QLabel("Błędy: 0   |   Ostrzeżenia: 0")
        stats_layout.addWidget(self.lbl_counters)
        stats_layout.addStretch(1)
        mid.addWidget(stats_box)

        root.addLayout(mid, 1)

        # --- Lista nowych linii i zdarzeń ---
        lists = QHBoxLayout()

        lines_box = QGroupBox("Nowe linie logu")
        lines_layout = QVBoxLayout(lines_box)
        self.list_lines = QListWidget()
        lines_layout.addWidget(self.list_lines)
        lists.addWidget(lines_box)

        events_box = QGroupBox("Wykryte problemy")
        events_layout = QVBoxLayout(events_box)
        self.list_events = QListWidget()
        events_layout.addWidget(self.list_events)
        lists.addWidget(events_box)

        root.addLayout(lists, 2)

        # --- Ostatni odczytany tekst ---
        text_box = QGroupBox("Ostatnio odczytany tekst")
        text_layout = QVBoxLayout(text_box)
        self.text_last = QPlainTextEdit()
        self.text_last.setReadOnly(True)
        self.text_last.setMaximumHeight(120)
        text_layout.addWidget(self.text_last)
        root.addWidget(text_box)

        # --- StatusBar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Ładny szary motyw listy zdarzeń - krytyczne na czerwono.
        self.list_events.setStyleSheet(
            "QListWidget::item { padding: 2px; }"
        )

    def _connect_signals(self) -> None:
        self.btn_select.clicked.connect(self._on_select_region)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_test_ocr.clicked.connect(self._on_test_ocr)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_save.clicked.connect(self._on_save_log)
        self.btn_browse_tesseract.clicked.connect(self._on_browse_tesseract)

        # Spinboxy zapisują konfigurację na bieżąco.
        self.spin_interval.valueChanged.connect(self._on_interval_changed)
        self.combo_lang.currentTextChanged.connect(self._on_lang_changed)
        self.spin_scale.valueChanged.connect(self._on_scale_changed)
        self.chk_preprocess.toggled.connect(self._on_preprocess_toggled)
        self.edit_tesseract.editingFinished.connect(self._on_tesseract_changed)

        # Sygnały z workera (cross-thread).
        self._worker.ocr_text.connect(self._on_ocr_text)
        self._worker.new_lines.connect(self._on_new_lines)
        self._worker.new_events.connect(self._on_new_events)
        self._worker.preview.connect(self._on_preview)
        self._worker.error.connect(self._on_error)
        self._worker.status.connect(self._on_worker_status)
        self._worker.finished_cycle.connect(self._on_finished_cycle)

        # Połączenie sygnału wyzwalającego ze slotem workera.
        # Dzięki temu emit() z wątku GUI automatycznie trafi do kolejki
        # zdarzeń wątku workera (QueuedConnection).
        self._worker.trigger_run_once.connect(self._worker.run_once)

        # Timer cyklu monitoringu (żądania do workera).
        self._monitor_timer = self._create_monitor_timer()

    def _create_monitor_timer(self):
        from PySide6.QtCore import QTimer

        timer = QTimer(self)
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        timer.timeout.connect(self._on_monitor_tick)
        return timer

    # ----- Akcje użytkownika -------------------------------------------------

    def _on_select_region(self) -> None:
        # Chowamy główne okno, aby nie przeszkadzało w zaznaczaniu.
        self.hide()
        QApplication.processEvents()
        QApplication.processEvents()
        self._selector = RegionSelector()
        self._selector.region_selected.connect(self._on_region_selected)
        self._selector.showFullScreen()

    def _on_region_selected(self, region) -> None:
        self.showNormal()
        self.activateWindow()
        if region is None:
            self.status_bar.showMessage("Anulowano wybór obszaru", 3000)
            return
        self.config.region = region
        self._save_config()
        self._refresh_region_label()
        self._worker.update_config(self.config)
        self.status_bar.showMessage(
            f"Ustawiono obszar: {region.left},{region.top} {region.width}x{region.height}",
            4000,
        )

    def _on_start(self) -> None:
        if not self._thread.isRunning():
            self._thread.start()
        if not self.config.region.is_valid():
            QMessageBox.warning(
                self,
                "Brak obszaru",
                "Najpierw wybierz obszar ekranu (przycisk 'Wybierz obszar').",
            )
            return
        # Upewnij się, że worker ma aktualną konfigurację.
        self._worker.update_config(self.config)
        interval_ms = int(self.spin_interval.value() * 1000)
        self._monitor_timer.start(interval_ms)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._refresh_status_text("OCR działa")
        self.status_bar.showMessage("Monitoring uruchomiony", 3000)

    def _on_stop(self) -> None:
        self._monitor_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._refresh_status_text("Zatrzymano")
        self.status_bar.showMessage("Monitoring zatrzymany", 3000)

    def _on_monitor_tick(self) -> None:
        # Wyzwalamy cykl w wątku workera (cross-thread signal/slot).
        self._worker.trigger_run_once.emit()

    def _on_test_ocr(self) -> None:
        if not self._thread.isRunning():
            self._thread.start()
        if not self.config.region.is_valid():
            QMessageBox.warning(
                self,
                "Brak obszaru",
                "Najpierw wybierz obszar ekranu.",
            )
            return
        self._worker.update_config(self.config)
        self.status_bar.showMessage("Wykonuję pojedynczy OCR...", 2000)
        self._worker.trigger_run_once.emit()

    def _on_clear(self) -> None:
        self.list_lines.clear()
        self.list_events.clear()
        self.text_last.clear()
        self._error_count = 0
        self._warning_count = 0
        self._update_counters()
        self._worker.reset_memory()
        self.status_bar.showMessage("Wyczyszczono wyniki", 3000)

    def _on_save_log(self) -> None:
        lines = [self.list_lines.item(i).text() for i in range(self.list_lines.count())]
        events = self._events_cache if hasattr(self, "_events_cache") else []
        default_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz raport", os.path.join(self.base_dir, "logs", default_name), "Text (*.txt)"
        )
        if not path:
            return
        try:
            Storage(self.config.storage, self.base_dir).export_session_txt(lines, events, path)
            self.status_bar.showMessage(f"Zapisano: {path}", 4000)
        except OSError as exc:
            QMessageBox.critical(self, "Błąd zapisu", str(exc))

    def _on_browse_tesseract(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz tesseract.exe",
            "C:\\Program Files\\Tesseract-OCR",
            "tesseract.exe (tesseract.exe);;Wszystkie pliki (*.*)",
        )
        if path:
            self.edit_tesseract.setText(path)
            self._on_tesseract_changed()

    # ----- Spinboxy/konfiguracja na bieżąco ---------------------------------

    def _on_interval_changed(self, value: float) -> None:
        self.config.interval_seconds = float(value)
        self._save_config()
        if self._monitor_timer.isActive():
            self._monitor_timer.setInterval(int(value * 1000))

    def _on_lang_changed(self, value: str) -> None:
        self.config.ocr_language = value
        self._save_config()
        self._worker.update_config(self.config)

    def _on_scale_changed(self, value: int) -> None:
        self.config.preprocessing.scale_factor = int(value)
        self._save_config()
        self._worker.update_config(self.config)

    def _on_preprocess_toggled(self, checked: bool) -> None:
        self.config.preprocessing.enabled = bool(checked)
        self._save_config()
        self._worker.update_config(self.config)

    def _on_tesseract_changed(self) -> None:
        path = self.edit_tesseract.text().strip()
        self.config.tesseract_path = path
        self._save_config()
        self._worker.update_config(self.config)
        self._check_tesseract()

    def _check_tesseract(self) -> None:
        try:
            OCREngine(self.config.tesseract_path, self.config.ocr_language).verify()
            self.lbl_preview_note.setText("OCR: Tesseract dostępny")
        except OCRError as exc:
            self.lbl_preview_note.setText("OCR: Tesseract NIEDOSTĘPNY")

    def _save_config(self) -> None:
        try:
            self.config.save_all(self.config_path, self.rules_path)
        except OSError as exc:
            self.status_bar.showMessage(f"Nie zapisano konfiguracji: {exc}", 4000)

    # ----- Obsługa sygnałów z workera ---------------------------------------

    @Slot(str)
    def _on_ocr_text(self, text: str) -> None:
        self.text_last.setPlainText(text)

    @Slot(list)
    def _on_new_lines(self, lines: List[LogLine]) -> None:
        max_items = self.config.gui.max_visible_new_lines
        for line in lines:
            self.list_lines.insertItem(0, line.text)
        # Ograniczamy liczbę widocznych pozycji (MVP - prosty limit).
        while self.list_lines.count() > max_items:
            self.list_lines.takeItem(self.list_lines.count() - 1)

    @Slot(list)
    def _on_new_events(self, events: List[DetectedEvent]) -> None:
        max_items = self.config.gui.max_visible_events
        if not hasattr(self, "_events_cache"):
            self._events_cache = []
        for ev in events:
            self._events_cache.append(ev)
            label = (
                f"[{ev.timestamp.strftime('%H:%M:%S')}] "
                f"[{ev.severity.upper()}] [{ev.category}] "
                f"{ev.rule_name} :: {ev.original_line}"
            )
            item_text = label
            item = QListWidgetItem(item_text)
            if ev.severity == "critical":
                item.setForeground(QColor(255, 80, 80))
            else:
                item.setForeground(QColor(230, 200, 80))
            self.list_events.insertItem(0, item)
            if ev.severity == "critical":
                self._error_count += 1
            else:
                self._warning_count += 1
        while self.list_events.count() > max_items:
            self.list_events.takeItem(self.list_events.count() - 1)
        self._update_counters()

        # Alerty.
        if self.config.alerts.enabled and events:
            critical = [e for e in events if e.severity == "critical"]
            if critical:
                QApplication.alert(self)
                if self.config.alerts.sound_enabled:
                    self._play_alert_sound()

    @Slot(object)
    def _on_preview(self, pixmap) -> None:
        if pixmap is None or pixmap.isNull():
            return
        scaled = pixmap.scaledToWidth(
            min(self.config.gui.preview_max_width, pixmap.width()),
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_preview.setPixmap(scaled)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self.status_bar.showMessage(message, 5000)
        self.lbl_preview_note.setText("OCR: błąd")

    @Slot(str)
    def _on_worker_status(self, text: str) -> None:
        if self._monitor_timer.isActive():
            self._refresh_status_text(text)
        else:
            self.lbl_preview_note.setText("OCR: " + text)

    @Slot(str)
    def _on_finished_cycle(self, ts: str) -> None:
        self.lbl_last_read.setText(f"Ostatni odczyt: {ts}")

    # ----- Pomocnicze --------------------------------------------------------

    def _refresh_region_label(self) -> None:
        r = self.config.region
        if r.is_valid():
            self.lbl_region.setText(f"L={r.left}, T={r.top}, W={r.width}, H={r.height}")
        else:
            self.lbl_region.setText("nie wybrano (kliknij 'Wybierz obszar')")

    def _refresh_status_text(self, text: str) -> None:
        self.lbl_status_value.setText(text)

    def _update_counters(self) -> None:
        self.lbl_counters.setText(
            f"Błędy: {self._error_count}   |   Ostrzeżenia: {self._warning_count}"
        )

    def _play_alert_sound(self) -> None:
        try:
            if self.config.alerts.sound_path and os.path.isfile(self.config.alerts.sound_path):
                from PySide6.QtMultimedia import QSoundEffect
                from PySide6.QtCore import QUrl

                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(self.config.alerts.sound_path))
                effect.setVolume(0.8)
                effect.play()
            else:
                QApplication.beep()
        except Exception:
            QApplication.beep()

    def closeEvent(self, event) -> None:
        try:
            if self._monitor_timer:
                self._monitor_timer.stop()
            self._worker.update_config(self.config)
            self._save_config()
        finally:
            self._thread.quit()
            self._thread.wait(2000)
            super().closeEvent(event)
