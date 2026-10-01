# AGENTS.md

## What this is

IP Analyzer v2.2 — desktop (PySide6/Qt) and CLI tool for IP extraction, geolocation, and forensic reporting. No tests, no CI, no linter configured.

## Entry points

- **GUI:** `python src/ip_analyzer_gui.py` (PySide6 app, requires display)
- **CLI:** `python src/main_cli.py <file> -o <output> -tz <timezone> -m "Key=Value"`

## Architecture (src/)

| File | Role |
|---|---|
| `ip_analyzer_gui.py` | GUI: MainWindow, AnalysisWorker (QThread), dialogs, export logic |
| `main_cli.py` | CLI entry point, argparse, calls processing |
| `processing.py` | Core analysis: IP extraction, timezone conversion, ipinfo.io enrichment |
| `api_clients.py` | HTTP calls to ipinfo.io, deterministic IP/timestamp extraction |
| `file_io.py` | Read input files (.txt/.log/.csv/.docx), export to PDF/CSV/JSON/TXT |
| `config.py` | Load/save `.env` (IPINFO_TOKEN) via python-dotenv |

## Setup

```bash
python -m venv venv
.\venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Token API goes in `src/.env`:
```
IPINFO_TOKEN=tu_token_aqui
```
Without token, runs in local-only mode (no geolocation/ISP).

## Quirks an agent would miss

- **No test suite exists.** Don't look for pytest/unittest — there are none.
- **No linting/typecheck configured.** No ruff, mypy, flake8, black. Code style is informal.
- **`.env` lives in `src/`**, not project root. `config.py` searches from `src/` upward.
- **Icons depend on `qtawesome`.** `init_icons()` MUST be called AFTER `QApplication` is created. The `ICONS` dict is global and empty until then.
- **Export logic is in `file_io.py`** but export dialog + filter/selection logic is in `ip_analyzer_gui.py` (`_export_report`, `_get_filtered_results`, `_get_selected_results`).
- **Timezone conversion** uses `zoneinfo` (Python 3.9+) with `pytz` fallback. `_tz_to_etc()` in gui converts display strings like "UTC-3" to POSIX "Etc/GMT+3" (sign inverted).
- **No packaging/build step.** No setup.py, pyproject.toml, or Makefile. Just run directly.
- **Windows-only path handling** in some places (backslash paths in CLI examples).
- **`.gitignore` excludes `export/`, `*.zip`, `Informe_IP_*.json|.txt`** — generated outputs.
