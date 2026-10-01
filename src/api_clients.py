import logging
import ipaddress
import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import quote
import requests

from config import IPINFO_URL

logger = logging.getLogger(__name__)

# Pattern for IPv4
IPV4_REGEX = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

# IPv6: permissive candidate token, then longest-valid-prefix reduction via ipaddress.
# A fixed alternation regex truncates addresses (fe80::1 -> fe80::) so it is not used here.
IPV6_CANDIDATE_REGEX = re.compile(r'[0-9a-fA-F:]+(?:\.\d{1,3}){0,3}')

_TOKEN_IN_MSG_REGEX = re.compile(r'token=[^&\s]+')

# Deterministic errors worth caching (a retry would return the same answer).
_DETERMINISTIC_ERRORS = (
    "IP Inválida (Formato)", "IP Inválida (Interno)", "Token IPinfo Faltante",
    "Token Inválido/Prohibido", "No Encontrado (ipinfo)",
)


def _sanitize(msg: Any) -> str:
    """Strip API tokens from anything logged (requests embeds the full URL in exceptions)."""
    return _TOKEN_IN_MSG_REGEX.sub('token=***', str(msg))


_session = requests.Session()

# Broad timestamp regex patterns
TIMESTAMP_PATTERNS = [
    # ISO / Standard YYYY-MM-DD HH:MM:SS (optional tz/fraction)
    re.compile(r'\b\d{4}[-/.]\d{2}[-/.]\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*(?:Z|UTC|[+-]\d{2}:?\d{2}))?\b', re.IGNORECASE),
    # DD/MM/YYYY or MM/DD/YYYY HH:MM:SS
    re.compile(r'\b\d{2}[-/.]\d{2}[-/.]\d{4}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*(?:Z|UTC|[+-]\d{2}:?\d{2}))?\b', re.IGNORECASE),
    # Apache / Common Log Format: [21/Aug/2024:13:09:43 +0000]
    re.compile(r'\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s*[\+\-]\d{4}'),
    # Syslog format: Aug 21 13:09:43 or Mar 15 2024 08:15:22 -0500
    re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:\s+\d{4})?\s+\d{2}:\d{2}:\d{2}(?:\s*[\+\-]\d{4}|\s*UTC|\s*GMT)?\b', re.IGNORECASE),
]

def validate_api_keys(ipinfo_token: Optional[str]) -> bool:
    """Valida el token API de ipinfo.io."""
    if not ipinfo_token:
        return False
    try:
        response = _session.get(
            f"https://ipinfo.io/8.8.8.8?token={quote(ipinfo_token.strip(), safe='')}", timeout=10
        )
        if response.status_code == 200:
            logger.info("Token de ipinfo.io validado exitosamente.")
            return True
        else:
            logger.error(f"Error al validar token de ipinfo.io: HTTP {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de red al validar token de ipinfo.io: {_sanitize(e)}")
        return False

def is_valid_ip(ip_str: str) -> bool:
    """Verifica si una cadena es una dirección IP válida (IPv4 o IPv6)."""
    if not isinstance(ip_str, str) or not ip_str or ip_str.isspace():
        return False
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except ValueError:
        return False


def extract_ipv6_candidates(text: str) -> List[str]:
    """Extrae direcciones IPv6 válidas de un texto (prefijo válido más largo por token)."""
    found: List[str] = []
    for match in IPV6_CANDIDATE_REGEX.finditer(text):
        token = match.group(0)
        if ':' not in token:
            continue
        candidate = token
        while candidate:
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                candidate = candidate[:-1]
                continue
            found.append(candidate)
            break
    return found

def extract_ip_data_deterministic(text_content: str) -> List[Dict[str, str]]:
    """Extrae direcciones IP y sus timestamps asociados mediante parsing determinista."""
    if not text_content:
        return []

    lines = text_content.splitlines()
    extracted_data: List[Dict[str, str]] = []
    seen_pairs = set()
    duplicate_count = 0

    for line in lines:
        if not line.strip():
            continue

        # Find all IPs in line
        ipv4_matches = IPV4_REGEX.findall(line)
        ipv6_candidates = extract_ipv6_candidates(line)

        ips_in_line = []
        for candidate in ipv4_matches + ipv6_candidates:
            candidate_clean = candidate.strip().strip("[](),;\"'")
            if is_valid_ip(candidate_clean):
                if candidate_clean not in ips_in_line:
                    ips_in_line.append(candidate_clean)

        if not ips_in_line:
            continue

        # Find timestamp in line
        found_ts = ""
        for pattern in TIMESTAMP_PATTERNS:
            ts_match = pattern.search(line)
            if ts_match:
                found_ts = ts_match.group(0).strip().strip("[]")
                break

        for ip in ips_in_line:
            pair = (ip, found_ts)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                extracted_data.append({"ip_address": ip, "timestamp_str": found_ts})
            else:
                duplicate_count += 1

    if duplicate_count:
        logger.info(
            f"Pares (IP, timestamp) duplicados omitidos: {duplicate_count} "
            f"(eventos repetidos con la misma IP y timestamp)."
        )
    logger.info(f"Extracción determinista completada: {len(extracted_data)} IPs/timestamps encontrados.")
    return extracted_data

_token_ipinfo_missing_logged = False
def get_ip_info(ip_address: str, token: str, cache: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene información de geolocalización e ISP desde ipinfo.io."""
    global _token_ipinfo_missing_logged
    
    if ip_address in cache:
        logger.debug(f"Cache HIT para IP: {ip_address}")
        return cache[ip_address]
    
    logger.debug(f"Cache MISS para IP: {ip_address}")
    result = {
        "isp": "N/A", "city": "N/A", "region": "N/A",
        "country": "N/A", "hostname": "N/A", "error": None
    }
    if not is_valid_ip(ip_address):
        result["error"] = "IP Inválida (Formato)"
        logger.error(f"Intento de buscar IP inválida '{ip_address}' (formato).")
        return result
    if not token:
        result["error"] = "Token IPinfo Faltante"
        if not _token_ipinfo_missing_logged:
            logger.critical("Token API ipinfo.io no configurado en .env.")
            _token_ipinfo_missing_logged = True
        return result

    try:
        ip_obj = ipaddress.ip_address(ip_address)
        ip_type = None
        if ip_obj.is_private: ip_type = "Privada"
        elif ip_obj.is_loopback: ip_type = "Loopback"
        elif ip_obj.is_link_local: ip_type = "Link-Local"
        elif ip_obj.is_multicast: ip_type = "Multicast"
        elif ip_obj.is_reserved: ip_type = "Reservada"
        if ip_type:
            result["error"] = f"IP {ip_type}"
            result["isp"] = f"Red {ip_type}"
            logger.info(f"IP '{ip_address}' es {ip_type}. No se consultará ipinfo.io.")
            cache[ip_address] = result
            return result
    except ValueError:
        result["error"] = "IP Inválida (Interno)"
        logger.error(f"Interno: Falló conversión ipaddress para IP ya validada: {ip_address}")
        return result

    url = IPINFO_URL.format(ip=quote(ip_address, safe=''), token=quote(token.strip(), safe=''))
    logger.debug(f"Consultando IPinfo para {ip_address}")

    max_attempts = 3
    response = None
    for attempt in range(max_attempts):
        retryable = False
        try:
            response = _session.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout (15s) contactando ipinfo.io para {ip_address}.")
            result["error"] = "Timeout IPinfo"
            retryable = True
        except requests.exceptions.HTTPError as http_err:
            status = http_err.response.status_code if http_err.response is not None else 0
            err_msg = f"Error HTTP {status} de ipinfo.io para {ip_address}"
            try:
                details = http_err.response.json().get('error', {}).get('message', '')
                if details:
                    err_msg += f" ({details})"
            except Exception:
                pass
            if status in (401, 403):
                err_msg += " (Token inválido?)"
                result["error"] = "Token Inválido/Prohibido"
            elif status == 404:
                err_msg += " (IP no encontrada?)"
                result["error"] = "No Encontrado (ipinfo)"
            elif status == 429:
                err_msg += " (Límite API?)"
                result["error"] = "Límite API Excedido"
                retryable = True
            else:
                result["error"] = f"HTTP Error {status}"
            logger.error(_sanitize(err_msg))
        except ValueError:
            # JSON inválido: requests.exceptions.JSONDecodeError subclasea ValueError
            body_preview = response.text[:200] if response is not None else "N/A"
            logger.error(f"Respuesta inválida (no JSON) ipinfo.io ({ip_address}). Body: {body_preview}...")
            result["error"] = "Respuesta Inválida"
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Error Conexión ipinfo.io ({ip_address}): {_sanitize(conn_err)}")
            result["error"] = "Error de Conexión"
            retryable = True
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Error Red Genérico ipinfo.io ({ip_address}): {_sanitize(req_err)}")
            result["error"] = "Error de Red"
        except Exception as e:
            logger.error(f"Error inesperado ipinfo ({ip_address}): {_sanitize(e)}", exc_info=True)
            result["error"] = "Error Interno (IPinfo)"
        else:
            org_field = data.get('org', ''); isp_val = 'N/A'
            if isinstance(org_field, str) and org_field:
                match = re.match(r"^(AS\d+)\s+(.*)", org_field, re.IGNORECASE)
                if match: isp_val = match.group(2).strip()
                else: isp_val = org_field
            if not isp_val or isp_val == 'N/A': isp_val = data.get('isp', 'N/A')

            result.update({
                "isp": isp_val if isp_val else "N/A",
                "city": data.get('city') or "N/A",
                "region": data.get('region') or "N/A",
                "country": data.get('country') or "N/A",
                "hostname": data.get('hostname') or "N/A",
                "error": None
            })
            break

        if retryable and attempt < max_attempts - 1:
            wait_s = 1.0 * (2 ** attempt)
            logger.warning(
                f"Reintentando consulta a ipinfo.io para {ip_address} en {wait_s:.0f}s "
                f"(intento {attempt + 2} de {max_attempts})..."
            )
            time.sleep(wait_s)
            continue
        break

    for key in ["isp", "city", "region", "country", "hostname"]: result.setdefault(key, "N/A")

    # Solo se cachean éxitos y errores deterministas: un timeout/429 no debe marcar la IP como fallida.
    final_error = result.get("error")
    if final_error is None or final_error in _DETERMINISTIC_ERRORS:
        cache[ip_address] = result
    return result
