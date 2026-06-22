"""Ładowanie i zapis konfiguracji aplikacji.

Cała konfiguracja jest w plikach JSON, dzięki czemu użytkownik może ją łatwo
modyfikować bez zmiany kodu. Ten moduł dostarcza klasę `AppConfig` ładującą
plik `config.json` oraz `RulesConfig` ładującą `rules.json`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import Region


DEFAULT_CONFIG: Dict[str, Any] = {
    "capture_region": {"left": 0, "top": 0, "width": 0, "height": 0},
    "interval_seconds": 1.0,
    "ocr_language": "eng",
    "tesseract_path": "",
    "preprocessing": {
        "enabled": True,
        "grayscale": True,
        "increase_contrast": True,
        "scale_factor": 2,
        "binary_threshold": 0,
    },
    "alerts": {"enabled": True, "sound_enabled": False, "sound_path": ""},
    "storage": {
        "save_lines_to_txt": True,
        "save_lines_to_csv": True,
        "save_events_to_csv": True,
        "logs_dir": "./logs",
        "lines_file": "lines.log",
        "events_file": "events.csv",
    },
    "gui": {
        "preview_max_width": 480,
        "max_visible_new_lines": 200,
        "max_visible_events": 200,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Łączy dwa słowniki - brakujące klucze z override uzupełnia z base."""
    result: Dict[str, Any] = {}
    for key, value in base.items():
        if key in override:
            if isinstance(value, dict) and isinstance(override[key], dict):
                result[key] = _deep_merge(value, override[key])
            else:
                result[key] = override[key]
        else:
            result[key] = value
    return result


@dataclass
class Preprocessing:
    enabled: bool = True
    grayscale: bool = True
    increase_contrast: bool = True
    scale_factor: int = 2
    binary_threshold: int = 0


@dataclass
class AlertsConfig:
    enabled: bool = True
    sound_enabled: bool = False
    sound_path: str = ""


@dataclass
class StorageConfig:
    save_lines_to_txt: bool = True
    save_lines_to_csv: bool = True
    save_events_to_csv: bool = True
    logs_dir: str = "./logs"
    lines_file: str = "lines.log"
    events_file: str = "events.csv"


@dataclass
class GuiConfig:
    preview_max_width: int = 480
    max_visible_new_lines: int = 200
    max_visible_events: int = 200


@dataclass
class Rule:
    name: str
    category: str
    keywords: List[str]
    severity: str = "warning"


@dataclass
class AppConfig:
    region: Region = field(default_factory=lambda: Region(0, 0, 0, 0))
    interval_seconds: float = 1.0
    ocr_language: str = "eng"
    tesseract_path: str = ""
    preprocessing: Preprocessing = field(default_factory=Preprocessing)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)
    rules: List[Rule] = field(default_factory=list)

    # ----- Ładowanie / zapis -------------------------------------------------

    @classmethod
    def load(cls, config_path: str, rules_path: str) -> "AppConfig":
        config = cls()
        config._load_config_file(config_path)
        config._load_rules_file(rules_path)
        return config

    def _load_config_file(self, config_path: str) -> None:
        if not os.path.isfile(config_path):
            self.save_config(config_path)
            return
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                raw: Dict[str, Any] = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Nie można wczytać pliku konfiguracyjnego '{config_path}': {exc}"
            ) from exc

        data = _deep_merge(DEFAULT_CONFIG, raw)

        self.region = Region.from_dict(data.get("capture_region"))
        self.interval_seconds = float(data.get("interval_seconds", 1.0))
        self.ocr_language = str(data.get("ocr_language", "eng"))
        self.tesseract_path = str(data.get("tesseract_path", ""))

        pre = data.get("preprocessing", {})
        self.preprocessing = Preprocessing(
            enabled=bool(pre.get("enabled", True)),
            grayscale=bool(pre.get("grayscale", True)),
            increase_contrast=bool(pre.get("increase_contrast", True)),
            scale_factor=int(pre.get("scale_factor", 2)),
            binary_threshold=int(pre.get("binary_threshold", 0)),
        )

        alerts = data.get("alerts", {})
        self.alerts = AlertsConfig(
            enabled=bool(alerts.get("enabled", True)),
            sound_enabled=bool(alerts.get("sound_enabled", False)),
            sound_path=str(alerts.get("sound_path", "")),
        )

        storage = data.get("storage", {})
        self.storage = StorageConfig(
            save_lines_to_txt=bool(storage.get("save_lines_to_txt", True)),
            save_lines_to_csv=bool(storage.get("save_lines_to_csv", True)),
            save_events_to_csv=bool(storage.get("save_events_to_csv", True)),
            logs_dir=str(storage.get("logs_dir", "./logs")),
            lines_file=str(storage.get("lines_file", "lines.log")),
            events_file=str(storage.get("events_file", "events.csv")),
        )

        gui = data.get("gui", {})
        self.gui = GuiConfig(
            preview_max_width=int(gui.get("preview_max_width", 480)),
            max_visible_new_lines=int(gui.get("max_visible_new_lines", 200)),
            max_visible_events=int(gui.get("max_visible_events", 200)),
        )

    def _load_rules_file(self, rules_path: str) -> None:
        if not os.path.isfile(rules_path):
            self.save_rules(rules_path)
            return
        try:
            with open(rules_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Nie można wczytać pliku reguł '{rules_path}': {exc}"
            ) from exc

        rules_list = raw.get("rules", []) if isinstance(raw, dict) else raw
        self.rules = []
        for item in rules_list:
            self.rules.append(
                Rule(
                    name=str(item.get("name", "RULE")),
                    category=str(item.get("category", "Inne")),
                    keywords=[str(k) for k in item.get("keywords", [])],
                    severity=str(item.get("severity", "warning")),
                )
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capture_region": self.region.to_dict(),
            "interval_seconds": self.interval_seconds,
            "ocr_language": self.ocr_language,
            "tesseract_path": self.tesseract_path,
            "preprocessing": {
                "enabled": self.preprocessing.enabled,
                "grayscale": self.preprocessing.grayscale,
                "increase_contrast": self.preprocessing.increase_contrast,
                "scale_factor": self.preprocessing.scale_factor,
                "binary_threshold": self.preprocessing.binary_threshold,
            },
            "alerts": {
                "enabled": self.alerts.enabled,
                "sound_enabled": self.alerts.sound_enabled,
                "sound_path": self.alerts.sound_path,
            },
            "storage": {
                "save_lines_to_txt": self.storage.save_lines_to_txt,
                "save_lines_to_csv": self.storage.save_lines_to_csv,
                "save_events_to_csv": self.storage.save_events_to_csv,
                "logs_dir": self.storage.logs_dir,
                "lines_file": self.storage.lines_file,
                "events_file": self.storage.events_file,
            },
            "gui": {
                "preview_max_width": self.gui.preview_max_width,
                "max_visible_new_lines": self.gui.max_visible_new_lines,
                "max_visible_events": self.gui.max_visible_events,
            },
        }

    def rules_to_dict(self) -> Dict[str, Any]:
        return {
            "rules": [
                {
                    "name": rule.name,
                    "category": rule.category,
                    "keywords": rule.keywords,
                    "severity": rule.severity,
                }
                for rule in self.rules
            ]
        }

    def save_config(self, config_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=4, ensure_ascii=False)

    def save_rules(self, rules_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(rules_path)), exist_ok=True)
        with open(rules_path, "w", encoding="utf-8") as fh:
            json.dump(self.rules_to_dict(), fh, indent=4, ensure_ascii=False)

    def save_all(self, config_path: str, rules_path: str) -> None:
        self.save_config(config_path)
        self.save_rules(rules_path)


def resolve_path(base_dir: str, path: str) -> str:
    """Zamienia ścieżkę względną na bezwzględną względem katalogu base_dir."""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(base_dir, path))
