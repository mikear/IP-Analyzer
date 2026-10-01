# AGENTS.md

## What this is

IP Analyzer v2.2 — desktop (PySide6/Qt) and CLI tool for IP extraction, geolocation, and forensic reporting. No tests, no CI, no linter/typechecker configured.

## Entry points

- **GUI:** `python src/ip_analyzer_gui.py` (PySide6 app, requires display)
- **CLI:** `python src/main_cli.py <file> -o <output> -tz <timezone> -m "Key=Value"`

## Architecture (src/)

| File | Role |
|---|---|
| `ip_analyzer_gui.py` | GUI: MainWindow, AnalysisWorker (QThread), dialogs, export/filter logic. Also holds `APP_VERSION = "2.2"` (single source for builds/about) |
| `main_cli.py` | CLI entry point, argparse, calls processing |
| `processing.py` | Core analysis: IP extraction, timezone conversion, ipinfo.io enrichment |
| `api_clients.py` | HTTP calls to ipinfo.io, deterministic IP/timestamp extraction |
| `file_io.py` | Read input files (.txt/.log/.csv/.docx), export to PDF/CSV/JSON/TXT |
| `config.py` | Load/save `.env` (IPINFO_TOKEN), mode-aware (source/portable/installed) |

## Verification (there is no test suite)

```bash
python -m compileall src scripts        # syntax check, this is the closest to "lint"
QT_QPA_PLATFORM=offscreen python -c "import sys; sys.path.insert(0,'src'); from PySide6.QtWidgets import QApplication; from ip_analyzer_gui import init_icons, MainWindow; app=QApplication([]); assert init_icons(); w=MainWindow(); print(w.windowTitle())"
```

Don't look for pytest/unittest/ruff/mypy — none exist. Manually test CLI runs against a real `.txt` log; geolocalization needs a token, without it the app runs local-only.

## Setup

```bash
python -m venv venv
.\venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

`requirements.txt` lists runtime deps only. **Build-only deps (installed but not listed):** `pyinstaller` (6.10) and Inno Setup 6 (`ISCC.exe`, found by `scripts/build_release.py` in PATH / Program Files / `%LOCALAPPDATA%\Programs`).

## Build & release

```bash
python scripts/build_release.py                 # GUI onedir + CLI onefile + LEEME + manifest + zip + installer + SHA256SUMS
python scripts/build_release.py --skip-gui --skip-cli   # only zip + installer + checksums (fast, for .iss changes)
```

- Version is read from `APP_VERSION` in `src/ip_analyzer_gui.py` (`"2.2"` → `2.2.0`). Bump it there, never in the script.
- Installer script: `scripts/IP-Analyzer.iss` (per-user, no admin; `[UninstallRun]` taskkills the app so uninstall leaves zero files).
- Outputs land in `dist/` (gitignored): `IP-Analyzer/`, `IP-Analyzer-Setup-v2.2.0-win64.exe`, `*-portable.zip`, `SHA256SUMS.txt`.
- **Release flow:** commit → `git push origin main` → create a token env and publish:
  ```powershell
  $env:GH_TOKEN = (("protocol=https`nhost=github.com`n`n" | git credential fill | Where-Object { $_ -like "password=*" }) -replace "^password=","")
  gh release create v2.2.0 --title "IP Analyzer v2.2.0" --notes-file dist\RELEASE_NOTES.md dist\*.exe dist\*.zip dist\SHA256SUMS.txt
  ```
  `gh auth login --with-token` FAILS (stored PAT lacks `read:org`); pass `GH_TOKEN` per command instead. PAT scopes: `gist, repo, workflow`.

## Quirks an agent would miss

- **`--exclude-module chardet` is mandatory in PyInstaller builds.** Installed chardet 7.6.0 is mypyc-compiled and crashes PyInstaller (`module filename missing`); `build_release.py` already passes it. Don't remove.
- **`.env` location depends on mode** (`config.py` resolves it): source → `src/.env`; frozen + installed via setup (registry `HKCU\Software\IP-Analyzer` value `InstalledBySetup`) → `%APPDATA%\IP-Analyzer\.env`; frozen portable → next to the exe if writable. Saves fall back to `%APPDATA%`.
- **Icons depend on `qtawesome`.** `init_icons()` MUST be called AFTER `QApplication` creation; the global `ICONS` dict stays empty until then (`main()` exits if it fails).
- **Worker→GUI signals are connected with explicit `Qt.QueuedConnection`** (`ip_analyzer_gui.py:1036-1039`, `:315`). Keep it — cross-thread Qt connections are the app's cancellation/log plumbing.
- **Export is split:** PDF/CSV/JSON/TXT writers in `file_io.py` (latin-1 via `_to_latin1`, CSV keeps `#` metadata lines); dialog, filter/selection and `_export_report` live in `ip_analyzer_gui.py`.
- **CSV metadata:** generated CSVs start with `#` comment lines; read them back with `pandas.read_csv(ruta, comment='#')`.
- **Timezone conversion** uses `zoneinfo` with `pytz` fallback; `_tz_to_etc()` (gui) maps display strings like `UTC-3` to POSIX `Etc/GMT+3` (sign inverted).
- **Shell here is PowerShell 5.1:** no heredocs, and `$var:` inside double quotes raises `InvalidVariableReferenceWithDrive` — build a `.ps1` or use `Write-Host ("x " + $var)`. `rg` is not installed; use the grep tool or `python -c`.
- **`.gitignore` covers generated output:** `export/`, `dist/`, `build/`, `*.spec`, `release/`, `*.zip`, `.env`, `Informe_IP_*`. Never commit those; release assets go to GitHub via `gh`, not the repo.
