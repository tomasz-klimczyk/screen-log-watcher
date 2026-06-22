# Screen Log Watcher

Aplikacja desktopowa do **bieżącego czytania i analizowania logów widocznych na ekranie**.

Program pozwala zaznaczyć dowolny prostokątny obszar ekranu (konsola, terminal,
okno przeglądarki, panel diagnostyczny, program serwisowy), a następnie cyklicznie
wykonuje zrzut tego obszaru, odczytuje tekst przez OCR (Tesseract) i na bieżąco
analizuje nowe linie, wykrywając ważne zdarzenia (ERROR, WARNING, TIMEOUT,
problemy Modbus/TCP itp.).

Program **nie wymaga** wczytywania plików logów — analizuje to, co aktualnie
widać na ekranie.

> Status: **MVP** — działająca, lokalna wersja. Priorytet: Windows 10/11.
> Kod jest napisany tak, aby w przyszłości łatwo dodać obsługę Linuksa.

---

## Spis treści

1. [Funkcjonalności](#funkcjonalności)
2. [Wymagania](#wymagania)
3. [Instalacja Tesseract OCR (Windows)](#instalacja-tesseract-ocr-windows)
4. [Instalacja i uruchomienie programu](#instalacja-i-uruchomienie-programu)
5. [Szybki start (jak używać)](#szybki-start-jak-używać)
6. [Struktura projektu](#struktura-projektu)
7. [Konfiguracja (config.json)](#konfiguracja-configjson)
8. [Reguły analizy (rules.json)](#reguły-analizy-rulesjson)
9. [Ograniczenia OCR](#ograniczenia-ocr)
10. [Rozwiązywanie problemów](#rozwiązywanie-problemów)
11. [Plany na kolejne wersje](#plany-na-kolejne-wersje)

---

## Funkcjonalności

- **Wybór obszaru ekranu** — przezroczysta nakładka, zaznaczenie myszką,
  współrzędne zapisywane w `config.json`.
- **Podgląd** przechwytywanego obszaru w oknie + przycisk **Test OCR**
  (pojedynczy zrzut i rozpoznany tekst).
- **Odczyt na żywo** — cykliczny zrzut + OCR (domyślnie co 1 s, konfigurowalny
  0.2–60 s).
- **Deduplikacja linii** — tylko nowe linie są analizowane (mechanizm odporny
  na drobne różnice w odczycie OCR — porównanie zbiorem słów).
- **Analiza logów** — konfigurowalne reguły ze słowami kluczowymi i kategoriami
  (Błąd krytyczny, Ostrzeżenie, Problem z połączeniem, Problem z autoryzacją,
  Problem Modbus/TCP, Inne).
- **Okno wyników** — status, ostatni odczyt, lista nowych linii, lista problemów
  (krytyczne na czerwono), liczniki błędów/ostrzeżeń, czas ostatniego odczytu.
- **Alerty** — powiadomienie w aplikacji (miganie na pasku zadań), opcjonalny
  dźwięk.
- **Zapis wyników** — `logs/lines.log` (TXT), `logs/lines.csv`, `logs/events.csv`
  oraz eksport raportu sesji do TXT.
- **Preprocessing obrazu** — skala szarości, zwiększenie kontrastu, skalowanie 2x,
  opcjonalna binaryzacja (przełączane w `config.json`).
- **Nieblokujący interfejs** — zrzut i OCR wykonują się w wątku roboczym
  (`QThread`), GUI pozostaje płynne.

---

## Wymagania

- **Windows 10/11** (priorytet). Program powinien działać też na Linuksie po
  drobnych modyfikacjach (mss i PySide6 są wieloplatformowe).
- **Python 3.11+** (testowano na 3.13).
- **Tesseract OCR** (osobny instalator — patrz niżej).

---

## Instalacja Tesseract OCR (Windows)

Aplikacja używa [Tesseract OCR](https://github.com/tesseract-ocr/tesseract).
Na Windowsie trzeba go zainstalować osobno — same `pip install` go nie pobierze.

### Opcja A — instalator (zalecane)

1. Pobierz instalator ze strony:
   https://github.com/UB-Mannheim/tesseract/wiki
   (plik np. `tesseract-ocr-w64-setup-5.x.x.exe`).
2. Uruchom instalator. **Zapamiętaj ścieżkę instalacji**, domyślnie:
   ```
   C:\Program Files\Tesseract-OCR\
   ```
3. W instalatorze zaznacz dodatkowe języki, jeśli potrzebujesz
   (np. *Polish language data*).
4. (Opcjonalnie) Dodaj `C:\Program Files\Tesseract-OCR\` do zmiennej `PATH`.

### Opcja B — Scoop / Chocolatey

```powershell
# Chocolatey
choco install tesseract

# Scoop
scoop install tesseract
```

### Wskazanie Tesseracta w aplikacji

Jeśli Tesseract **nie jest** w `PATH`, ustaw ścieżkę w `config/config.json`:

```json
{
  "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
}
```

...lub w polu „Tesseract path” w oknie aplikacji (przycisk `...`).

Weryfikacja instalacji w konsoli:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

---

## Instalacja i uruchomienie programu

```powershell
cd C:\screen-log-watcher

# (opcjonalnie) utwórz wirtualne środowisko
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# instalacja zależności
pip install -r requirements.txt

# uruchomienie
python main.py
```

> Jeśli `python` uruchamia sklep Microsoft Store, użyj `py -3 main.py`.

---

## Szybki start (jak używać)

1. Uruchom `python main.py`.
2. Kliknij **Wybierz obszar** i zaznacz myszką obszar ekranu z logami.
3. (Opcjonalnie) Kliknij **Test OCR**, aby wykonać pojedynczy odczyt
   i zobaczyć rozpoznany tekst.
4. Ustaw interwał (np. 1 s) i język OCR (`eng`, `pol` lub `eng+pol`).
5. Kliknij **Start**, aby rozpocząć monitoring.
6. Nowe linie pojawiają się na liście po lewej, wykryte problemy po prawej
   (krytyczne na czerwono).
7. Kliknij **Zapisz log**, aby wyeksportować raport sesji do TXT.
8. **Stop** zatrzymuje monitoring. **Wyczyść wyniki** resetuje listy i liczniki.

---

## Struktura projektu

```
screen-log-watcher/
├── main.py                  # punkt wejścia (uruchomienie aplikacji)
├── requirements.txt         # zależności Pythona
├── README.md
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── gui.py               # interfejs PySide6 (okno + nakładka + wątek)
│   ├── screen_capture.py    # przechwytywanie obszaru ekranu (mss)
│   ├── ocr_engine.py        # OCR (pytesseract) + preprocessing obrazu
│   ├── log_analyzer.py      # reguły + deduplikacja linii
│   ├── config.py            # ładowanie/zapis config.json i rules.json
│   ├── storage.py           # zapis logów/zdarzeń do TXT i CSV
│   └── models.py            # modele danych (Region, LogLine, DetectedEvent)
├── config/
│   ├── config.json          # konfiguracja aplikacji
│   └── rules.json           # reguły analizy logów
└── logs/                    # katalog wyników (TXT/CSV) — tworzony automatycznie
```

---

## Konfiguracja (config.json)

Plik `config/config.json` jest tworzony automatycznie z wartościami domyślnymi,
jeśli go brak. Najważniejsze pola:

| Pole                       | Opis                                                                 |
|----------------------------|----------------------------------------------------------------------|
| `capture_region`           | Współrzędne obszaru (`left`, `top`, `width`, `height`).             |
| `interval_seconds`         | Interwał odczytu (sekundy, min. 0.2).                               |
| `ocr_language`             | Język Tesseract (`eng`, `pol`, `eng+pol`).                          |
| `tesseract_path`           | Pełna ścieżka do `tesseract.exe` (pusty = szukaj w PATH).           |
| `preprocessing.enabled`    | Włącza/wyłącza obróbkę obrazu przed OCR.                            |
| `preprocessing.grayscale`  | Konwersja do skali szarości.                                        |
| `preprocessing.increase_contrast` | Zwiększenie kontrastu (często poprawia czytelność).           |
| `preprocessing.scale_factor` | Powiększenie obrazu (2 = 2x). Lepsze dla małego tekstu.            |
| `preprocessing.binary_threshold` | Próg binaryzacji (0 = wyłączona, zwykle 100–180).            |
| `alerts.enabled`           | Włącza alerty w aplikacji.                                          |
| `alerts.sound_enabled`     | Odtwarza dźwięk przy błędzie krytycznym.                            |
| `storage.logs_dir`         | Katalog zapisu logów (względem katalogu projektu).                  |
| `storage.save_*`           | Włącza/zapis konkretnych plików (TXT/CSV linii, CSV zdarzeń).       |

---

## Reguły analizy (rules.json)

Reguły są w pełni konfigurowalne w `config/rules.json`. Każda reguła:

```json
{
  "name": "MODBUS_TCP_ERROR",
  "category": "Problem Modbus/TCP",
  "keywords": ["MODBUS ERROR", "TCP ERROR", "UNIT ID", "CRC"],
  "severity": "critical"
}
```

- `name` — unikalna nazwa reguły (używana w raportach).
- `category` — kategoria wyświetlana w GUI i CSV.
- `keywords` — lista słów/wyrażeń (dopasowanie zawieraści, wielkość liter
  nie ma znaczenia; znaki interpunkcyjne są ignorowane).
- `severity` — `critical` (czerwony, liczone jako błąd) lub `warning`
  (żółty, liczone jako ostrzeżenie).

Domyślne reguły obejmują m.in.: ERROR, ERR, FAILED, FAIL, WARNING, WARN,
TIMEOUT, DISCONNECTED, CONNECTION LOST, REFUSED, DENIED, CRITICAL, EXCEPTION,
TRACEBACK, MODBUS ERROR, TCP ERROR, UNIT ID, CRC, RETRY.

Dodawanie własnych słów = dopisanie ich do odpowiedniej reguły w `rules.json`.

---

## Ograniczenia OCR

- OCR nigdy nie jest w 100% dokładny — zwłaszcza przy małej czcionce, niskim
  kontraście, antyaliasingu lub kolorowym tle.
- Czasem myli podobne znaki (`0`/`O`, `1`/`l`/`I`, `:`/`;`).
- Aby poprawić jakość:
  - zwiększ `scale_factor` (np. 2–3) dla małego tekstu,
  - włącz `increase_contrast`,
  - zwiększ rozmiar/czcionkę w monitorowanym oknie,
  - dla stałej czcionki (np. konsola) włącz `binary_threshold` (np. 140).
- Aplikacja używa deduplikacji odpornej na drobne różnice, ale bardzo różne
  odczyty tej samej linii mogą zostać uznane za różne.
- Przechwytywanie ekranu na Windowsie zazwyczaj działa bez dodatkowych uprawnień.
  Na Linuksie/Mac może wymagać zgody na nagrywanie ekranu.

---

## Rozwiązywanie problemów

| Objaw | Rozwiązanie |
|-------|-------------|
| „Tesseract NIEDOSTĘPNY” / `TesseractNotFoundError` | Zainstaluj Tesseract i ustaw `tesseract_path` w `config.json` lub w polu w aplikacji. |
| „Brak obszaru” | Kliknij **Wybierz obszar** i zaznacz prostokąt. |
| OCR zwraca pusty tekst | Włącz preprocessing, zwiększ `scale_factor`, sprawdź kontrast obszaru, spróbuj innego języka. |
| GUI „zamraża się” | Zwiększ interwał (np. 2 s). OCR wykonywany jest w wątku roboczym, ale bardzo duże obszary mogą trwać. |
| Brak uprawnień do ekranu | Uruchom aplikację bez `Run as administrator` (lub odwrotnie — zależy od systemu). |
| Brak pliku `config.json` | Zostanie utworzony automatycznie przy pierwszym uruchomieniu. |

Pliki z błędami i zdarzeniami znajdziesz w `logs/`:
- `lines.log` / `lines.csv` — nowe rozpoznane linie,
- `events.csv` — wykryte zdarzenia (data, kategoria, reguła, linia).

---

## Plany na kolejne wersje

- Skrócone okno podglądu na żywo z nałożonymi highlightami wykrytych słów.
- Eksport do formatów Bogatsze alerty (e-mail, webhook).
- Bufor ograniczający pamięć deduplikacji (sliding window zamiast pełnej historii).
- Obsługa wielu monitorów w nakładce wyboru (już działa przez wirtualny pulpit).
- Interpretacja struktury logów (timestamps, poziomy) zamiast czystego dopasowania.
- Wsparcie dla Linuksa (testy, ewentualne drobne poprawki `mss`/uprawnień).
- Pakiet instalacyjny (`.exe` przez PyInstaller).

---

## Stack technologiczny

- **Python 3.11+**
- **PySide6** (Qt 6) — interfejs graficzny
- **mss** — szybki zrzut ekranu
- **pytesseract** + **Tesseract OCR** — rozpoznawanie tekstu
- **Pillow**, **NumPy**, **opencv-python** — obróbka obrazu

---

## Licencja

Projekt edukacyjny / narzędziowy. Możesz dowolnie modyfikować i używać.
