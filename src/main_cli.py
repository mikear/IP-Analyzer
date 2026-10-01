import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
import re

# --- Asegurar que el directorio src esté en el path ---
script_dir = Path(__file__).parent.resolve()
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from config import load_config
from file_io import export_to_csv, export_to_json, export_to_pdf, export_to_txt, format_report
from processing import process_ip_analysis, _check_critical_dependencies, validate_timezone

# Extensiones de salida gestionadas por export_to_* (para no destruir sufijos del usuario).
_KNOWN_EXPORT_SUFFIXES = {".txt", ".csv", ".json", ".pdf"}


def _output_path(base_path: Path, ext: str) -> Path:
    """Devuelve `base_path` con la extensión dada, sin truncar nombres con puntos."""
    if base_path.suffix.lower() in _KNOWN_EXPORT_SUFFIXES:
        return base_path.with_suffix(ext)
    return base_path.with_name(base_path.name + ext)


def main_cli() -> None:
    """Punto de entrada para la ejecución desde línea de comandos."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger(__name__)
    logger.info("--- Analizador IP/ISP Backend (CLI Mode) ---")

    missing_deps = _check_critical_dependencies()
    if missing_deps:
        logger.critical("Error Crítico: Faltan dependencias esenciales:")
        for dep in missing_deps: logger.critical(f" - {dep}")
        logger.critical("\nInstálalas usando pip:")
        logger.critical(f"   pip install {' '.join(missing_deps)}")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Analiza un archivo de texto para extraer IPs, obtener su información de ISP/geolocalización y generar un informe.",
        epilog="Ejemplo: python src/main_cli.py C:\\ruta\\al\\archivo.txt -o C:\\ruta\\informe --timezone America/Bogota"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Ruta al archivo de entrada (txt, docx, csv, log)."
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Ruta base para los archivos de salida (sin extensión). Se generarán .txt, .csv, .json y .pdf."
    )
    parser.add_argument(
        "-tz", "--timezone",
        default="UTC",
        help=f"Zona horaria para convertir los timestamps. Default: UTC."
    )
    parser.add_argument(
        "-m", "--meta",
        nargs='*',
        action='append',
        metavar="'clave=valor'",
        help="Añade metadatos al informe. Se puede usar varias veces. Ej: -m \"Investigador=John Doe\" -m \"Caso=123-ABC\""
    )
    args = parser.parse_args()

    if not validate_timezone(args.timezone):
        logger.critical(
            f"Zona horaria no válida o no disponible: '{args.timezone}'. "
            f"Ejemplos válidos: UTC, America/Bogota, Etc/GMT+3."
        )
        sys.exit(2)

    logger.info("Cargando configuración desde .env...")
    ipinfo_token = load_config()
    if not ipinfo_token:
        logger.warning("Aviso: Token API IPInfo no configurado en .env. El análisis se ejecutará en modo local sin geolocalización enriquecida.")

    metadata_dict = {}
    if args.meta:
        logger.info("Parseando metadatos...")
        for meta_list in args.meta:
            item_str = ' '.join(meta_list)
            match = re.match(r'^(.+?)\s*=\s*(.+)$', item_str)
            if match:
                key = match.group(1).strip().replace(" ", "_").lower()
                value = match.group(2).strip().strip('"\'')
                metadata_dict[key] = value
                logger.info(f"  - Añadido metadata: {key} = '{value}'")
            else: logger.warning(f"Ignorando metadato mal formateado: '{item_str}'.")
    metadata_dict.setdefault('archivo_origen', args.input_file.name)
    metadata_dict.setdefault('fecha_analisis_cli', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    metadata_dict["zona_horaria_cli"] = args.timezone

    logger.info(f"\nIniciando análisis para '{args.input_file.name}'...")
    logger.info(f"Zona Horaria Objetivo: {args.timezone}")
    
    # --- Llamada a process_ip_analysis ---
    results_wrapper = process_ip_analysis(
        input_filepath=args.input_file,
        target_timezone=args.timezone,
        ipinfo_token=ipinfo_token,
        progress_queue=None
    )

    print("\n--- Fin Log Detallado ---") # Separador visual

    if results_wrapper is None:
        logger.critical("Análisis falló (revisar log anterior).")
        sys.exit(1)

    analysis_results = results_wrapper.get("analysis_results", [])
    analysis_metadata = results_wrapper.get("metadata", {})
    
    # Combinar metadatos de CLI y del análisis
    final_metadata = analysis_metadata
    final_metadata.update(metadata_dict)

    if not analysis_results:
        logger.info("Análisis completado, sin IPs válidas encontradas.")
        if not args.output:
            logger.info("No se generará ningún archivo de salida (no se indicó -o y no hay resultados).")
    else:
        logger.info(f"Análisis completado. {len(analysis_results)} IPs procesadas.")
        print("\n--- Informe Resumido (Consola) ---")
        report_str = format_report(analysis_results, args.timezone, final_metadata)
        print(report_str)

    if args.output:
        base_path = args.output.resolve()
        logger.info(f"\nExportando informes a base: {base_path}...")
        try:
            base_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as dir_err:
            logger.critical(f"No se pudo crear dir salida: {base_path.parent}\n{dir_err}")
            sys.exit(1)

        export_errors = []
        for fmt, func in (
            ("TXT", export_to_txt),
            ("CSV", export_to_csv),
            ("JSON", export_to_json),
            ("PDF", export_to_pdf),
        ):
            try:
                func(_output_path(base_path, f".{fmt.lower()}"), analysis_results, final_metadata)
            except ImportError as imp_err:
                export_errors.append(f"{fmt}: {imp_err}")
            except Exception as e:
                export_errors.append(f"{fmt}: {e}")

        if not export_errors:
            logger.info("Exportación completada.")
        else:
            logger.warning("\nErrores durante la exportación:")
            for err in export_errors:
                logger.warning(f"  - {err}")

    logger.info("\n--- Fin del Script ---")

if __name__ == "__main__":
    main_cli()
