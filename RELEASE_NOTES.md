# IP Analyzer — Release Notes

## v2.2.0 (2026-10-01)

- Full IPv6 extraction, robust IPv4/IPv6 candidates (no truncation).
- Timestamps: Common Log Format (`21/Aug/2024:13:09:43 +0000`) and `DD/MM/YYYY` with ambiguity warning.
- Timezone validated before analysis: invalid zone aborts without calling the API.
- Clean cancellation with a notice in report metadata.
- GUI: KPI panel, error highlighting, live log, non-editable table, debounced search, export all/filtered/selected (PDF, CSV, JSON, TXT).
- CLI: repeatable `-m "Key=Value"`, validated `-tz`, safe encoding.
- PDF latin-1 without broken characters; CSV metadata as `#` lines (`pandas.read_csv(..., comment='#')`).
- New build pipeline: `scripts/build_release.py` (PyInstaller GUI + CLI, zip, Inno Setup installer, `SHA256SUMS.txt`).

See GitHub Releases for downloads and checksums.
