import logging
import re
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional, Union

from api_clients import extract_ip_data_deterministic, get_ip_info
from file_io import read_input_file

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
    _use_zoneinfo = True
except ImportError:
    _use_zoneinfo = False
    ZoneInfoNotFoundError = None  # type: ignore[assignment]

try:
    import pytz
    from pytz import UnknownTimeZoneError
except ImportError:
    pytz = None
    UnknownTimeZoneError = None  # type: ignore[assignment]

# Clases de error de zona horaria disponibles en esta instalación (evita NameError en except).
_TZ_ERRORS = tuple(
    exc for exc in (ZoneInfoNotFoundError, UnknownTimeZoneError) if isinstance(exc, type)
) or (Exception,)

try:
    from dateutil import parser as date_parser
    from dateutil.tz import UTC as dateutil_UTC
    _dateutil_available = True
except ImportError:
    _dateutil_available = False

logger = logging.getLogger(__name__)

VALID_TIMEZONES = {"UTC"}
_gmt_zones_incomplete_zi = False
try:
    if _use_zoneinfo:
        logger.info("Usando 'zoneinfo' para zonas horarias.")
        VALID_TIMEZONES.update(available_timezones())
        _gmt_zones_present_zi = True
        for i in range(-14, 15):
            try:
                ZoneInfo(f'Etc/GMT{"+" if i <= 0 else ""}{-i}')
            except ZoneInfoNotFoundError:
                _gmt_zones_present_zi = False
                break
        if not _gmt_zones_present_zi:
            _gmt_zones_incomplete_zi = True

except Exception:
    _use_zoneinfo = False

if not _use_zoneinfo:
    try:
        if pytz:
            logger.info("Usando 'pytz' para zonas horarias.")
            VALID_TIMEZONES.update(set(pytz.all_timezones))
            for i in range(-14, 15):
                VALID_TIMEZONES.add(f'Etc/GMT{"+" if i <= 0 else ""}{-i}')
    except Exception:
        pytz = None

SORTED_VALID_TIMEZONES = sorted(list(VALID_TIMEZONES))

# Apache/nginx Common Log Format: '21/Aug/2024:13:09:43 +0000' (dateutil exige espacio)
_CLF_TIMESTAMP_REGEX = re.compile(r'^(\d{2}/[A-Za-z]{3}/\d{4}):(\d{2}:\d{2}:\d{2})(.*)$')
# Fecha numérica DD/MM/YYYY o MM/DD/YYYY
_NUMERIC_DATE_REGEX = re.compile(r'^(\d{2})[-/.](\d{2})[-/.](\d{4})')

_warned_ambiguous_date = False
_warned_naive_timestamp = False


def validate_timezone(tz_str: str) -> bool:
    """Comprueba que la zona horaria existe en esta instalación (sin llamar a la API)."""
    if not tz_str or tz_str.isspace():
        return False
    if tz_str in VALID_TIMEZONES:
        return True
    if _use_zoneinfo:
        try:
            ZoneInfo(tz_str)
            return True
        except Exception:
            pass
    if pytz:
        try:
            pytz.timezone(tz_str)
            return True
        except Exception:
            return False
    return False

def _check_critical_dependencies() -> List[str]:
    """Verifica las dependencias mínimas para el funcionamiento básico."""
    missing = []
    if not _dateutil_available:
        missing.append("python-dateutil")
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
    global _warned_ambiguous_date, _warned_naive_timestamp

    ts_to_parse = timestamp_str.strip()
    dayfirst = False

    # 1) Apache/nginx CLF: 21/Aug/2024:13:09:43 +0000 -> 21/Aug/2024 13:09:43 +0000
    clf_match = _CLF_TIMESTAMP_REGEX.match(ts_to_parse)
    if clf_match:
        ts_to_parse = f"{clf_match.group(1)} {clf_match.group(2)}{clf_match.group(3)}"

    # 2) Fechas numéricas DD/MM/YYYY: se asume día primero (formato habitual en informes)
    num_match = _NUMERIC_DATE_REGEX.match(ts_to_parse)
    if num_match:
        dayfirst = True
        day, month = int(num_match.group(1)), int(num_match.group(2))
        if day <= 12 and month <= 12 and not _warned_ambiguous_date:
            _warned_ambiguous_date = True
            logger.warning(
                f"Fecha ambigua DD/MM vs MM/DD detectada ('{timestamp_str}'). "
                f"Se asume formato DD/MM (día primero)."
            )

    try:
        original_dt = date_parser.parse(ts_to_parse, ignoretz=False, fuzzy=False, dayfirst=dayfirst)
        if original_dt.tzinfo is None or original_dt.tzinfo.utcoffset(original_dt) is None:
            if not _warned_naive_timestamp:
                _warned_naive_timestamp = True
                logger.warning(
                    "Se encontraron timestamps sin offset de zona horaria: se interpretan como UTC. "
                    "Si el origen usa hora local, revise el resultado."
                )
            original_dt_aware_utc = original_dt.replace(tzinfo=dateutil_UTC)
        else:
            original_dt_aware_utc = original_dt.astimezone(dateutil_UTC)
    except (ValueError, OverflowError) as parse_err:
        logger.warning(f"No se pudo parsear timestamp '{timestamp_str}': {parse_err}")
        return None, "Error Parsing"
    except Exception as e:
        logger.error(f"Error inesperado parseando TS '{timestamp_str}': {e}", exc_info=True)
        return None, "Error Interno (Parseo)"

    formatted_converted = "Error TZ Conv."
    final_target_tz_str = target_tz_str

    try:
        target_tz_obj = None
        if _gmt_zones_incomplete_zi and final_target_tz_str.startswith('Etc/GMT') and pytz:
            target_tz_obj = pytz.timezone(final_target_tz_str)
        elif final_target_tz_str == "UTC":
            target_tz_obj = dateutil_UTC
        elif _use_zoneinfo:
            target_tz_obj = ZoneInfo(final_target_tz_str)
        elif pytz:
            target_tz_obj = pytz.timezone(final_target_tz_str)
        else:
            formatted_converted = original_dt_aware_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
            return original_dt_aware_utc, formatted_converted

        converted_dt = original_dt_aware_utc.astimezone(target_tz_obj)
        # Solo offset numerico: %Z produce abreviaturas ambiguas ('-03-0300').
        formatted_converted = converted_dt.strftime('%Y-%m-%d %H:%M:%S %z') or converted_dt.isoformat()
    except _TZ_ERRORS as tz_lookup_err:
        logger.critical(f"Error Interno: TZ '{final_target_tz_str}' no encontrada: {tz_lookup_err}")
        formatted_converted = "Error TZ Interno"
    except Exception as e:
        logger.error(f"Error inesperado convirtiendo a TZ '{final_target_tz_str}': {e}", exc_info=True)
        formatted_converted = "Error Interno (TZ Conv.)"

    return original_dt_aware_utc, formatted_converted

def process_ip_analysis(
    input_filepath: Union[str, Path],
    target_timezone: str,
    ipinfo_token: Optional[str] = None,
    progress_queue: Optional[Queue] = None,
    log_queue_handler: Optional[logging.Handler] = None,
    input_file_hash: Optional[str] = None,
    app_version: Optional[str] = None,
    cancel_event: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Orquesta el proceso completo con extracción determinista.

    Si se pasa ``cancel_event`` (threading.Event) y éste se activa, el análisis
    se detiene y devuelve parcialmente lo procesado hasta ese momento.
    """

    root_logger = logging.getLogger()
    if log_queue_handler:
        if not log_queue_handler.formatter:
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
            log_queue_handler.setFormatter(formatter)
        # Se adjunta al logger raíz para que api_clients/file_io también lleguen a la GUI.
        if log_queue_handler not in root_logger.handlers:
            root_logger.addHandler(log_queue_handler)
            if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
                root_logger.setLevel(logging.INFO)

    start_time = datetime.now()
    logger.info(f"[{start_time.strftime('%H:%M:%S')}] === INICIO Análisis ===")
    logger.info(f"Archivo entrada: {Path(input_filepath).resolve()}")
    logger.info(f"Zona horaria solicitada: '{target_timezone}'")
    if input_file_hash:
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
    analysis_cancelled = False

    try:
        crit_deps = _check_critical_dependencies()
        if crit_deps:
            logger.critical("Error Crítico: Faltan dependencias:")
            for d in crit_deps: logger.critical(f"  - {d}")
            _report_progress("Error", 100, "Faltan dependencias"); return None

        filepath = Path(input_filepath)
        if not filepath.is_file(): logger.critical(f"Archivo no encontrado: {filepath}"); _report_progress("Error", 100, "Archivo no encontrado"); return None

        if not validate_timezone(target_timezone):
            logger.critical(
                f"Zona horaria no válida o no disponible en esta instalación: '{target_timezone}'."
            )
            _report_progress("Error", 100, f"Zona horaria no válida: {target_timezone}")
            return None
        valid_target_tz = target_timezone

        _report_progress("Lectura", 5, f"Leyendo {filepath.name}...")
        text_content = read_input_file(filepath)
        if text_content is None: _report_progress("Error", 100, "Fallo lectura archivo"); return None
        if not text_content.strip():
            logger.warning("El archivo de entrada está vacío: no hay nada que analizar.")
            results_final = []
            _report_progress("Completado", 100, "Archivo vacío")
            return {"analysis_results": [], "metadata": {"input_file_sha256": input_file_hash, "app_version": app_version}}

        logger.info(f"Archivo leído ({len(text_content)} caracteres).")
        _report_progress("Extracción Determinista", 20, "Analizando patrones de IP y Timestamp...")

        extracted_data = extract_ip_data_deterministic(text_content)
        if not extracted_data:
            _report_progress("Completado", 100, "No se encontraron IPs válidas")
            return {"analysis_results": [], "metadata": {"input_file_sha256": input_file_hash, "app_version": app_version}}

        logger.info(f"Extractor local identificó {len(extracted_data)} IPs/timestamps.")
        _report_progress("Procesando IPs", 30, f"Procesando {len(extracted_data)} IPs...")

        processed_results: List[Dict[str, Any]] = []
        total_ips = len(extracted_data)
        base_prog = 30; processing_weight = 70
        ip_info_cache: Dict[str, Any] = {}
        cancelled = False

        for idx, item in enumerate(extracted_data):
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                logger.warning(
                    f"Análisis cancelado por el usuario: {len(processed_results)} de {total_ips} IPs procesadas."
                )
                _report_progress("Cancelado", 100, f"Análisis cancelado ({len(processed_results)} IPs)")
                break

            prog_share = int(((idx + 1) / total_ips) * processing_weight)
            current_perc = base_prog + prog_share
            ip = item.get('ip_address', 'ERROR'); ts_str = item.get('timestamp_str', "")
            _report_progress(f"Procesando IP {idx+1}/{total_ips}", current_perc, f"IP: {ip}")

            ip_info = get_ip_info(ip, ipinfo_token or "", ip_info_cache)
            if ip_info.get("error"):
                err_msg = ip_info['error']
                if "Privada" in err_msg or "Loopback" in err_msg or "Link-Local" in err_msg:
                    logger.debug(f"  IP {ip}: {err_msg} (ignorada)")
                else:
                    logger.warning(f"  -> Info IP Error para {ip}: {err_msg}")

            orig_dt_utc, conv_ts_fmt = parse_and_convert_timezone(ts_str, valid_target_tz)

            orig_ts_utc_str = "N/A"
            if orig_dt_utc:
                try: orig_ts_utc_str = orig_dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
                except ValueError: orig_ts_utc_str = "Error Formato UTC"

            processed_results.append({
                "ip_address": ip, "raw_timestamp_str": ts_str,
                "original_timestamp_utc": orig_dt_utc,
                "original_timestamp_utc_str": orig_ts_utc_str,
                "converted_timestamp": conv_ts_fmt,
                "ip_info": ip_info
            })
        results_final = processed_results
        analysis_cancelled = cancelled

    finally:
        # Los logs de cierre deben emitirse ANTES de quitar el handler (llegan a la GUI).
        end_time = datetime.now(); duration = end_time - start_time
        log_lvl = logging.INFO if results_final is not None else logging.ERROR
        logger.log(log_lvl, f"[{end_time.strftime('%H:%M:%S')}] === FIN Análisis ===")
        if results_final is not None:
            logger.log(log_lvl, f"Se procesaron {len(results_final)} IPs.")
        logger.log(log_lvl, f"Duración total: {duration.total_seconds():.2f} segundos.")
        if log_queue_handler and log_queue_handler in root_logger.handlers:
            root_logger.removeHandler(log_queue_handler)

        if results_final is not None:
            if analysis_cancelled:
                _report_progress("Cancelado", 100, f"Análisis cancelado ({len(results_final)} IPs).")
            else:
                _report_progress("Completado", 100, f"Análisis finalizado ({len(results_final)} IPs).")

    if results_final is not None:
        return {
            "analysis_results": results_final,
            "metadata": {
                "input_file_sha256": input_file_hash,
                "analysis_start_time": start_time.isoformat(),
                "analysis_duration_seconds": (datetime.now() - start_time).total_seconds(),
                "input_filepath": str(Path(input_filepath).resolve()),
                "target_timezone": target_timezone,
                "app_version": app_version,
                "cancelado": analysis_cancelled
            }
        }
    else:
        return None
