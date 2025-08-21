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

from config import load_config, get_dotenv_path
from file_io import export_to_csv, export_to_json, export_to_pdf, export_to_txt, format_report
from processing import process_ip_analysis, _check_critical_dependencies


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
        logger.critical(f"   pip install {' '.join(d for d in missing_deps if not d.startswith('pytz'))}")
        if any(d.startswith('pytz') for d in missing_deps): logger.critical("   pip install pytz")
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

    logger.info("Cargando configuración desde .env...")
    gemini_key, ipinfo_token = load_config()
    if not gemini_key or not ipinfo_token:
        logger.critical("Error Crítico: Faltan claves API en .env.")
        logger.critical(f"Asegúrate de que existan en: {get_dotenv_path()}")
        sys.exit(1)
    logger.info("Claves API cargadas.")

    metadata_dict = {}
    if args.meta:
        logger.info("Parseando metadatos...")
        for meta_list in args.meta:
            item_str = ' '.join(meta_list)
            match = re.match(r'^(.+?)\s*=\s*["\\](.+?)["\\]$', item_str)
            if match:
                key = match.group(1).strip().replace(" ", "_").lower()
                value = match.group(2).strip()
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
        args.input_file, args.timezone, gemini_key, ipinfo_token, progress_queue=None
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
            try:
                export_to_txt(base_path.with_suffix(".txt"), analysis_results, final_metadata)
            except Exception as e:
                export_errors.append(f"TXT: {e}")
            try:
                export_to_csv(base_path.with_suffix(".csv"), analysis_results, final_metadata)
            except Exception as e:
                export_errors.append(f"CSV: {e}")
            try:
                export_to_json(base_path.with_suffix(".json"), analysis_results, final_metadata)
            except Exception as e:
                export_errors.append(f"JSON: {e}")
            try:
                export_to_pdf(base_path.with_suffix(".pdf"), analysis_results, final_metadata)
            except ImportError as imp_err:
                export_errors.append(f"PDF: {imp_err}")
            except Exception as e:
                export_errors.append(f"PDF: {e}")

            if not export_errors:
                logger.info("Exportación completada.")
            else:
                logger.warning("\nErrores durante la exportación:")
                for err in export_errors:
                    logger.warning(f"  - {err}")

    logger.info("\n--- Fin del Script ---")

if __name__ == "__main__":
    main_cli()