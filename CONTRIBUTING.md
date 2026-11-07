# Contributing

Contributions are welcome: bug reports, IP/timestamp format ideas, UI improvements, translations, and documentation fixes.

- Read this file and the [Code of Conduct](CODE_OF_CONDUCT.md).
- Use the [bug report](https://github.com/mikear/IP-Analyzer/issues/new?template=bug_report.yml) or [feature request](https://github.com/mikear/IP-Analyzer/issues/new?template=feature_request.yml) templates.
- Ask questions and share workflows in [Discussions](https://github.com/mikear/IP-Analyzer/discussions) if enabled, otherwise open an issue.
- Never open a public issue for a vulnerability; see [SECURITY.md](SECURITY.md).

## Build from source

Requirements: Python 3.10+ (3.8 compatible), `pip install -r requirements.txt`.

```bash
python -m venv venv
.\venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m compileall src scripts
python src/ip_analyzer_gui.py
python src/main_cli.py registros_ips_demo.txt -o export/demo -tz UTC
```

Build installers:

```bash
python scripts/build_release.py
python scripts/build_release.py --skip-gui --skip-cli
```

## Keep it simple

- No new dependencies for a few lines of code — standard library and existing deps first.
- Keep tests manual (there is no test suite by design). One small runnable check per non-trivial change.
