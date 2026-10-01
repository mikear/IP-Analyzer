"""Genera los artefactos de release de IP Analyzer.

Produce (en dist/):
  - IP-Analyzer/                       aplicacion portable (GUI onedir + CLI + manifest)
  - IP-Analyzer-vX.Y.Z-win64-portable.zip
  - IP-Analyzer-Setup-vX.Y.Z-win64.exe (instalador Inno Setup, con desinstalador)

Requiere Inno Setup 6 (ISCC.exe) para el paso de instalador.

Uso:
    python scripts/build_release.py [--skip-gui] [--skip-cli] [--skip-installer] [--skip-zip]
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_DIR = DIST / "IP-Analyzer"
GUI_EXE = APP_DIR / "IP-Analyzer.exe"
CLI_EXE = DIST / "ip-analyzer-cli.exe"
ASSETS = ROOT / "assets"

APP_ID = "IP-Analyzer"
MANIFEST_NAME = "manifest.json"


def get_version():
    text = (SRC / "ip_analyzer_gui.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise RuntimeError("No se encontró APP_VERSION en ip_analyzer_gui.py")
    version = match.group(1)
    return version if version.count(".") == 2 else f"{version}.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args, label):
    print(f"\n=== {label} ===\n> {' '.join(str(a) for a in args)}", flush=True)
    result = subprocess.run([str(a) for a in args], cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(f"Fallo al ejecutar: {label} (exit {result.returncode})")


def clean():
    for path in (BUILD, DIST / APP_ID, DIST / "ip-analyzer-cli", DIST / "IPAnalyzer.cli.spec"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink()


def version_file(version: str) -> Path:
    parts = [int(p) for p in version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    tuple_str = tuple(parts)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple_str},
    prodvers={tuple_str},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'Diego A. Rabalo'),
            StringStruct('FileDescription', 'IP Analyzer - analisis forense de IPs'),
            StringStruct('FileVersion', '{version}'),
            StringStruct('InternalName', '{APP_ID}'),
            StringStruct('LegalCopyright', '(c) Diego A. Rabalo. Licencia MIT.'),
            StringStruct('OriginalFilename', '{APP_ID}.exe'),
            StringStruct('ProductName', 'IP Analyzer'),
            StringStruct('ProductVersion', '{version}'),
          ],
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""
    path = BUILD / "file_version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def build_gui(version: str):
    run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--windowed",
            "--name", APP_ID,
            "--icon", ASSETS / "app_icon.ico",
            "--version-file", version_file(version),
            "--add-data", f"{ASSETS / 'app_icon.png'};assets",
            "--collect-data", "qtawesome",
            "--collect-data", "fpdf2",
            "--collect-all", "tzdata",
            "--hidden-import", "PySide6.QtSvg",
            "--hidden-import", "PySide6.QtSvgWidgets",
            "--exclude-module", "chardet",
            "--paths", SRC,
            SRC / "ip_analyzer_gui.py",
        ],
        "GUI (onedir)",
    )
    if not GUI_EXE.is_file():
        raise SystemExit(f"No se generó {GUI_EXE}")


def build_cli(version: str):
    run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--console", "--onefile",
            "--name", "ip-analyzer-cli",
            "--icon", ASSETS / "app_icon.ico",
            "--collect-all", "tzdata",
            "--exclude-module", "chardet",
            "--paths", SRC,
            SRC / "main_cli.py",
        ],
        "CLI (onefile)",
    )
    source = DIST / "ip-analyzer-cli.exe"
    if not source.is_file():
        raise SystemExit(f"No se generó {source}")
    shutil.copy2(source, APP_DIR / source.name)


def write_readme(version: str):
    text = f"""IP Analyzer v{version} - EDICION PORTABLE
========================================

No requiere instalacion: basta con extraer el ZIP y ejecutar IP-Analyzer.exe.

Contenido
---------
  IP-Analyzer.exe          Interfaz grafica (doble clic)
  ip-analyzer-cli.exe      Version de linea de comandos (consola)
  _internal\\               Bibliotecas y recursos de la aplicacion
  manifest.json            Manifiesto SHA-256 de integridad (usado por el instalador)

Configuracion (token IPINFO)
----------------------------
Opcion A - desde la GUI:  Archivo > Gestionar Token IPInfo...
Opcion B - manual:        crear un archivo .env junto a IP-Analyzer.exe con:

    IPINFO_TOKEN=tu_token

Si no hay token, la aplicacion funciona en modo local (sin geolocalizacion).

CLI
---
  ip-analyzer-cli.exe <archivo> -o <salida> -tz "America/Argentina/Buenos_Aires" -m "Investigador=Juan Perez"

Notas
-----
  - Los informes exportados se guardan donde usted elija (por defecto junto al origen).
  - Este programa no modifica el registro ni instala servicios.

Ayuda: https://github.com/mikear/IP-Analyzer
"""
    (APP_DIR / "LEEME.txt").write_text(text, encoding="utf-8")


def write_manifest(version: str):
    files = {}
    for path in sorted(APP_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(APP_DIR).as_posix()
        if rel == MANIFEST_NAME:
            continue
        files[rel] = sha256_file(path)
    manifest = {
        "app": APP_ID,
        "version": version,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(files),
        "files": files,
    }
    (APP_DIR / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    total = sum((APP_DIR / rel).stat().st_size for rel in files)
    print(f"Payload: {len(files)} archivos, {total / (1024 * 1024):.1f} MB")


def make_portable_zip(version: str):
    folder_name = f"{APP_ID}-{version}-win64"
    staging = DIST / "_zip" / folder_name
    if staging.parent.exists():
        shutil.rmtree(staging.parent, ignore_errors=True)
    staging.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(APP_DIR, staging)
    zip_path = DIST / f"{folder_name}-portable.zip"
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=staging.parent, base_dir=folder_name)
    shutil.rmtree(staging.parent, ignore_errors=True)
    print(f"Portable: {zip_path.name} ({zip_path.stat().st_size / (1024 * 1024):.1f} MB)")
    return zip_path


def find_iscc() -> Path:
    found = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def build_installer(version: str) -> Path:
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit(
            "No se encontró ISCC.exe (Inno Setup 6). Instale Inno Setup "
            "o ejecute con --skip-installer."
        )
    run(
        [iscc, "/Q", f"/DMyAppVersion={version}", ROOT / "scripts" / "IP-Analyzer.iss"],
        f"Instalador (Inno Setup {iscc})",
    )
    built = DIST / f"IP-Analyzer-Setup-v{version}-win64.exe"
    if not built.is_file():
        raise SystemExit(f"No se generó {built}")
    print(f"Setup: {built.name} ({built.stat().st_size / (1024 * 1024):.1f} MB)")
    return built


def write_checksums(artifacts):
    lines = []
    for path in artifacts:
        if path and Path(path).is_file():
            lines.append(f"{sha256_file(path)}  {Path(path).name}")
    out = DIST / "SHA256SUMS.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Checksums: {out}")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-gui", action="store_true")
    parser.add_argument("--skip-cli", action="store_true")
    parser.add_argument("--skip-installer", action="store_true")
    parser.add_argument("--skip-zip", action="store_true")
    args = parser.parse_args()

    version = get_version()
    print(f"IP Analyzer v{version} - build {time.strftime('%Y-%m-%d %H:%M:%S')}")

    if not args.skip_gui:
        clean()
        build_gui(version)
    if not args.skip_cli:
        build_cli(version)

    write_readme(version)
    write_manifest(version)

    artifacts = []
    if not args.skip_zip:
        artifacts.append(make_portable_zip(version))
    if not args.skip_installer:
        artifacts.append(build_installer(version))
    write_checksums(artifacts)
    print("\nListo.")


if __name__ == "__main__":
    main()
