import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional, Union

from api_clients import extract_ip_data_with_gemini, get_ip_info
from file_io import read_input_file

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
    _use_zoneinfo = True
except ImportError:
    _use_zoneinfo = False

try:
    import pytz
    from pytz import UnknownTimeZoneError
except ImportError:
    pytz = None

try:
    from dateutil import parser as date_parser
    from dateutil.tz import UTC as dateutil_UTC
    _dateutil_available = True
except ImportError:
    _dateutil_available = False

logger = logging.getLogger(__name__)

# --- Manejo de Zonas Horarias ---
VALID_TIMEZONES = {"UTC"}  # Fallback mínimo, siempre incluir UTC
_gmt_zones_incomplete_zi = False # Initialize globally
try:
    # Prefiere zoneinfo (Python >= 3.9)
    if _use_zoneinfo:
        logger.info("Usando 'zoneinfo' para zonas horarias.")
        VALID_TIMEZONES.update(available_timezones())
        # Validar si las zonas Etc/GMT están presentes en zoneinfo
        _gmt_zones_present_zi = True
        for i in range(-14, 15):
            try:
                ZoneInfo(f'Etc/GMT{"+ " if i <= 0 else ""}{-i}')
            except ZoneInfoNotFoundError:
                _gmt_zones_present_zi = False
                logger.warning(f"Zona Etc/GMT{-i} no encontrada en zoneinfo.")
                break
        if not _gmt_zones_present_zi:
            _gmt_zones_incomplete_zi = True # Set the global flag
            logger.warning(
                "Las zonas Etc/GMT no están completas en 'zoneinfo'. "
                "Se recomienda 'pytz' o actualizar data tz."
            )

except Exception: # Capturar cualquier error durante la importación o inicialización de zoneinfo
    _use_zoneinfo = False # Asegurarse de que no se use si hay problemas
    logger.warning("No se pudo inicializar 'zoneinfo'. Intentando con 'pytz'.", exc_info=True)

if not _use_zoneinfo:
    try:
        # Fallback a pytz
        if pytz:
            logger.info("Usando 'pytz' para zonas horarias.")
            VALID_TIMEZONES.update(set(pytz.all_timezones))
            # Añadir zonas Etc/GMT manualmente
            for i in range(-14, 15):
                VALID_TIMEZONES.add(f'Etc/GMT{"+ " if i <= 0 else ""}{-i}')  # Signo invertido
    except Exception: # Capturar cualquier error durante la importación o inicialización de pytz
        pytz = None # Asegurarse de que no se use si hay problemas
        logger.critical("No se pudo inicializar 'pytz'. La conversión de TZ será limitada.", exc_info=True)

SORTED_VALID_TIMEZONES = sorted(list(VALID_TIMEZONES))

def _check_critical_dependencies() -> List[str]:
    """Verifica las dependencias mínimas para el funcionamiento básico."""
    missing = []
    # These are checked dynamically in the functions that use them
    return missing

def parse_and_convert_timezone(
    timestamp_str: str, target_tz_str: str
) -> tuple[Optional[datetime], str]:
    """Parsea, convierte a UTC y luego a la zona horaria objetivo."""
    if not timestamp_str or not isinstance(timestamp_str, str) or timestamp_str.strip() in ['N/A', '']:
        return None, "N/A"
    if not _dateutil_available:
        logger.critical("Falta 'python-dateutil' para parsear timestamps.")
        return None, "Error: Falta Dep."

    original_dt_aware_utc: Optional[datetime] = None
    try:
        original_dt = date_parser.parse(timestamp_str, ignoretz=False, fuzzy=False)
        if original_dt.tzinfo is None or original_dt.tzinfo.utcoffset(original_dt) is None:
            original_dt_aware_utc = original_dt.replace(tzinfo=dateutil_UTC)
            logger.debug(f"TS '{timestamp_str}' naive. Asumiendo UTC -> {original_dt_aware_utc}")
        else:
            logger.info(f"TS '{timestamp_str}' con TZ ({original_dt.tzinfo}). Convirtiendo a UTC.")
            original_dt_aware_utc = original_dt.astimezone(dateutil_UTC)
    except (ValueError, OverflowError) as parse_err:
        logger.warning(f"No se pudo parsear timestamp '{timestamp_str}': {parse_err}")
        return None, "Error Parsing"
    except TypeError as type_err:
        logger.warning(f"Error tipo parseando TS '{timestamp_str}': {type_err}")
        return None, "Error Tipo Parsing"
    except Exception as e:
        logger.error(f"Error inesperado parseando TS '{timestamp_str}': {e}", exc_info=True)
        return None, "Error Interno (Parseo)"

    formatted_converted = "Error TZ Conv."
    final_target_tz_str = target_tz_str

    try:
        target_tz_obj = None
        # Prioritize pytz for Etc/GMT if zoneinfo is incomplete for them
        if _gmt_zones_incomplete_zi and final_target_tz_str.startswith('Etc/GMT') and pytz:
            logger.debug(f"Usando pytz para {final_target_tz_str} debido a zoneinfo incompleto.")
            target_tz_obj = pytz.timezone(final_target_tz_str)
        elif final_target_tz_str == "UTC":
            target_tz_obj = dateutil_UTC
        elif _use_zoneinfo:
            target_tz_obj = ZoneInfo(final_target_tz_str)
        elif pytz:
            target_tz_obj = pytz.timezone(final_target_tz_str)
        else:
            # Fallback if no timezone library is available
            logger.warning("No se puede convertir TZ sin 'zoneinfo'/'pytz'. Devolviendo UTC.")
            formatted_converted = original_dt_aware_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
            return original_dt_aware_utc, formatted_converted

        converted_dt = original_dt_aware_utc.astimezone(target_tz_obj)
        formatted_converted = converted_dt.strftime('%Y-%m-%d %H:%M:%S %Z%z')
    except (ZoneInfoNotFoundError, UnknownTimeZoneError) as tz_lookup_err:
        logger.critical(f"Error Interno: TZ '{final_target_tz_str}' no encontrada por biblioteca: {tz_lookup_err}")
        formatted_converted = "Error TZ Interno"
    except Exception as e:
        logger.error(f"Error inesperado convirtiendo a TZ '{final_target_tz_str}': {e}", exc_info=True)
        formatted_converted = "Error Interno (TZ Conv.)"

    return original_dt_aware_utc, formatted_converted

def process_ip_analysis(
    input_filepath: Union[str, Path],
    target_timezone: str,  # La TZ solicitada
    gemini_key: Optional[str],
    ipinfo_token: Optional[str],
    progress_queue: Optional[Queue] = None,
    log_queue_handler: Optional[logging.Handler] = None, # Handler para logs GUI
    input_file_hash: Optional[str] = None, # New parameter for file hash
    app_version: Optional[str] = None, # New parameter for app version
) -> Optional[Dict[str, Any]]:
    """Orquesta el proceso completo. Devuelve resultados o None si error crítico."""

    if log_queue_handler:
        if not log_queue_handler.formatter:
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
            log_queue_handler.setFormatter(formatter)
        if log_queue_handler not in logger.handlers:
            logger.addHandler(log_queue_handler)
            if logger.level == logging.NOTSET: logger.setLevel(logging.INFO) # Asegurar nivel

    start_time = datetime.now()
    logger.info(f"[{start_time.strftime('%H:%M:%S')}] === INICIO Análisis ===")
    logger.info(f"Archivo entrada: {Path(input_filepath).resolve()}")
    logger.info(f"Zona horaria solicitada: '{target_timezone}'")
    if input_file_hash: # Log the hash if provided
        logger.info(f"Hash SHA256 del archivo de entrada: {input_file_hash}")

    def _report_progress(step: str, perc: int, msg: Optional[str] = None):
        perc = max(0, min(100, perc))
        if progress_queue:
            m = msg or step
            progress_data = {"step": step, "percentage": perc, "message": f"[{perc}%] {m}"}
            try: progress_queue.put_nowait(progress_data)
            except Exception as q_err: logger.error(f"Error enviando progreso: {q_err}")
        logger.debug(f"Progreso: {step} - {perc}%")

    _report_progress("Inicio", 0, "Validando config...")
    results_final: Optional[List[Dict[str, Any]]] = None

    try:
        crit_deps = _check_critical_dependencies()
        if crit_deps:
            logger.critical("Error Crítico: Faltan dependencias:")
            for d in crit_deps: logger.critical(f"  - {d}")
            _report_progress("Error", 100, "Faltan dependencias"); return None

        if not gemini_key: logger.critical("Clave API Gemini no provista."); _report_progress("Error", 100, "Falta API Key Gemini"); return None
        if not ipinfo_token: logger.critical("Token API IPinfo no provisto."); _report_progress("Error", 100, "Falta Token IPinfo"); return None
        filepath = Path(input_filepath)
        if not filepath.is_file(): logger.critical(f"Archivo no encontrado: {filepath}"); _report_progress("Error", 100, "Archivo no encontrado"); return None

        valid_target_tz = target_timezone

        _report_progress("Lectura", 5, f"Leyendo {filepath.name}...")
        text_content = read_input_file(filepath)
        if text_content is None: _report_progress("Error", 100, "Fallo lectura archivo"); return None
        if not text_content.strip(): _report_progress("Completado", 100, "Archivo vacío"); return []

        logger.info(f"Archivo leído ({len(text_content)} caracteres).")
        _report_progress("Extracción IA", 15, "Enviando texto a Gemini API...")
        extracted_data = extract_ip_data_with_gemini(text_content, gemini_key)
        if extracted_data is None: _report_progress("Error", 100, "Fallo extracción Gemini"); return None
        if not extracted_data: _report_progress("Completado", 100, "No se extrajeron IPs"); return []

        logger.info(f"Gemini extrajo {len(extracted_data)} IPs/timestamps potenciales.")
        _report_progress("Procesando IPs", 30, f"Procesando {len(extracted_data)} IPs...")

        processed_results: List[Dict[str, Any]] = []
        total_ips = len(extracted_data)
        base_prog = 30; processing_weight = 70
        ip_info_cache: Dict[str, Any] = {}

        for idx, item in enumerate(extracted_data):
            prog_share = int(((idx + 1) / total_ips) * processing_weight)
            current_perc = base_prog + prog_share
            ip = item.get('ip_address', 'ERROR'); ts_str = item.get('timestamp_str', "")
            _report_progress(f"Procesando IP {idx+1}/{total_ips}", current_perc, f"IP: {ip}")
            logger.debug(f"--- Procesando IP {idx+1}: {ip} (TS Crudo: '{ts_str}') ---")

            time.sleep(0.1) # Pausa para evitar rate-limiting
            ip_info = get_ip_info(ip, ipinfo_token, ip_info_cache)
            if ip_info.get("error"): logger.warning(f"  -> Info IP Error para {ip}: {ip_info['error']}")

            orig_dt_utc, conv_ts_fmt = parse_and_convert_timezone(ts_str, valid_target_tz)
            if "Error" in conv_ts_fmt or conv_ts_fmt == "N/A" and ts_str:
                logger.warning(f"  -> Timestamp Info para IP {ip}: Crudo='{ts_str}', Conv='{conv_ts_fmt}'")

            orig_ts_utc_str = "N/A"
            if orig_dt_utc:
                try: orig_ts_utc_str = orig_dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
                except ValueError: logger.warning(f"No se pudo formatear datetime UTC '{orig_dt_utc}'"); orig_ts_utc_str = "Error Formato UTC"

            processed_results.append({
                "ip_address": ip, "raw_timestamp_str": ts_str,
                "original_timestamp_utc": orig_dt_utc,
                "original_timestamp_utc_str": orig_ts_utc_str,
                "converted_timestamp": conv_ts_fmt,
                "ip_info": ip_info
            })
        results_final = processed_results # Guardar resultado exitoso

    finally: # Asegurarse de quitar handler y loguear fin
        if log_queue_handler and log_queue_handler in logger.handlers:
            logger.removeHandler(log_queue_handler); logger.debug("Handler log GUI quitado.")

        end_time = datetime.now(); duration = end_time - start_time
        log_lvl = logging.INFO if results_final is not None else logging.ERROR
        logger.log(log_lvl, f"[{end_time.strftime('%H:%M:%S')}] === FIN Análisis ===")
        if results_final is not None: logger.log(log_lvl, f"Se procesaron {len(results_final)} IPs.")
        else: logger.log(log_lvl, "Análisis terminó con errores.")
        logger.log(log_lvl, f"Duración total: {duration.total_seconds():.2f} segundos.")
        if results_final is not None: _report_progress("Completado", 100, f"Análisis finalizado ({len(results_final)} IPs).")

    if results_final is not None:
        # Create a wrapper dictionary to include metadata like the hash
        final_report_data = {
            "analysis_results": results_final,
            "metadata": {
                "input_file_sha256": input_file_hash,
                "analysis_start_time": start_time.isoformat(),
                "analysis_duration_seconds": (datetime.now() - start_time).total_seconds(),
                "input_filepath": str(Path(input_filepath).resolve()),
                "target_timezone": target_timezone,
                "app_version": app_version # Use the passed app_version
            }
        }
        return final_report_data # Return the wrapped dictionary
    else:
        return None # Return None if analysis failed