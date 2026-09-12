import logging
import ipaddress
import re
from typing import Dict, List, Optional, Any, Tuple
import requests

from config import IPINFO_URL

logger = logging.getLogger(__name__)

# Pattern for IPv4
IPV4_REGEX = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

# Pattern for IPv6 (matches general hex group structure, validated via ipaddress)
IPV6_REGEX = re.compile(
    r'\b(?:[0-9a-fA-F]{1,4}:){1,7}:?|:(?::[0-9a-fA-F]{1,4}){1,7}\b|'
    r'\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b|'
    r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'
)

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

# Keywords that indicate VPN, Proxy, Datacenter, TOR or Hosting
VPN_PROXY_KEYWORDS = [
    "vpn", "proxy", "tor", "exit node", "m247", "nord", "expressvpn", "surfshark",
    "cyberghost", "private internet access", "proton", "ovh", "hetzner", "digitalocean",
    "linode", "aws", "amazon", "google cloud", "azure", "vultr", "choopa", "datacenter",
    "hosting", "server", "cloud", "clouder", "vps"
]

def validate_api_keys(ipinfo_token: Optional[str]) -> bool:
    """Valida el token API de ipinfo.io."""
    if not ipinfo_token:
        return False
    try:
        response = requests.get(f"https://ipinfo.io/8.8.8.8?token={ipinfo_token}", timeout=10)
        if response.status_code == 200:
            logger.info("Token de ipinfo.io validado exitosamente.")
            return True
        else:
            logger.error(f"Error al validar token de ipinfo.io: HTTP {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de red al validar token de ipinfo.io: {e}")
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

def extract_ip_data_deterministic(text_content: str) -> List[Dict[str, str]]:
    """Extrae direcciones IP y sus timestamps asociados mediante parsing determinista."""
    if not text_content:
        return []

    lines = text_content.splitlines()
    extracted_data: List[Dict[str, str]] = []
    seen_pairs = set()

    for line in lines:
        if not line.strip():
            continue

        # Find all IPs in line
        ipv4_matches = IPV4_REGEX.findall(line)
        ipv6_candidates = IPV6_REGEX.findall(line)

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

    logger.info(f"Extracción determinista completada: {len(extracted_data)} IPs/timestamps encontrados.")
    return extracted_data

def detect_privacy_type(data: Dict[str, Any], isp_name: str, hostname: str) -> Dict[str, Any]:
    """Detecta si la IP corresponde a una VPN, Proxy, TOR o Datacenter/Hosting."""
    privacy_info = {
        "is_vpn": False,
        "is_proxy": False,
        "is_tor": False,
        "is_hosting": False,
        "privacy_label": "Residencial / IP Real"
    }

    # 1. Check direct 'privacy' field if returned by ipinfo.io (standard on paid or standard plan)
    privacy_obj = data.get("privacy", {})
    if isinstance(privacy_obj, dict) and privacy_obj:
        if privacy_obj.get("vpn"): privacy_info["is_vpn"] = True
        if privacy_obj.get("proxy"): privacy_info["is_proxy"] = True
        if privacy_obj.get("tor"): privacy_info["is_tor"] = True
        if privacy_obj.get("hosting"): privacy_info["is_hosting"] = True

    # 2. Heuristic check based on ISP, Org, and Hostname
    combined_info = f"{isp_name} {hostname}".lower()

    if any(k in combined_info for k in ["vpn", "nordvpn", "expressvpn", "m247", "private internet access", "protonvpn", "surfshark", "cyberghost"]):
        privacy_info["is_vpn"] = True
    if any(k in combined_info for k in ["proxy", "exit node"]):
        privacy_info["is_proxy"] = True
    if "tor" in combined_info.split():
        privacy_info["is_tor"] = True
    if any(k in combined_info for k in ["hetzner", "ovh", "digitalocean", "linode", "aws", "amazon", "google cloud", "azure", "vultr", "datacenter", "hosting", "vps"]):
        privacy_info["is_hosting"] = True

    # Set summary label
    labels = []
    if privacy_info["is_tor"]: labels.append("TOR Exit Node")
    if privacy_info["is_vpn"]: labels.append("VPN Detectada")
    if privacy_info["is_proxy"]: labels.append("Proxy Detectado")
    if privacy_info["is_hosting"]: labels.append("Hosting / Datacenter")

    if labels:
        privacy_info["privacy_label"] = " / ".join(labels)

    return privacy_info

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
        "country": "N/A", "hostname": "N/A", "error": None,
        "privacy": {"is_vpn": False, "is_proxy": False, "is_tor": False, "is_hosting": False, "privacy_label": "Desconocido"}
    }
    if not is_valid_ip(ip_address):
        result["error"] = "IP Inválida (Formato)"
        logger.error(f"Intento de buscar IP inválida '{ip_address}' (formato).")
        return result
    if not token:
        result["error"] = "Token IPinfo Faltante"
        result["privacy"]["privacy_label"] = "Sin Token (Local)"
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
            result["privacy"]["privacy_label"] = f"Red {ip_type}"
            logger.info(f"IP '{ip_address}' es {ip_type}. No se consultará ipinfo.io.")
            cache[ip_address] = result
            return result
    except ValueError:
        result["error"] = "IP Inválida (Interno)"
        logger.error(f"Interno: Falló conversión ipaddress para IP ya validada: {ip_address}")
        return result

    url = IPINFO_URL.format(ip=ip_address, token=token)
    logger.debug(f"Consultando IPinfo para {ip_address}")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        logger.debug(f"Respuesta IPinfo para {ip_address}: {str(data)[:200]}...")

        org_field = data.get('org', ''); isp_val = 'N/A'
        if isinstance(org_field, str) and org_field:
            match = re.match(r"^(AS\d+)\s+(.*)", org_field, re.IGNORECASE)
            if match: isp_val = match.group(2).strip()
            else: isp_val = org_field
        if not isp_val or isp_val == 'N/A': isp_val = data.get('isp', 'N/A')

        hostname_val = data.get('hostname') or "N/A"
        privacy_details = detect_privacy_type(data, isp_val, hostname_val)

        result.update({
            "isp": isp_val if isp_val else "N/A",
            "city": data.get('city') or "N/A",
            "region": data.get('region') or "N/A",
            "country": data.get('country') or "N/A",
            "hostname": hostname_val,
            "privacy": privacy_details,
            "error": None
        })

    except requests.exceptions.Timeout:
        logger.error(f"Timeout (15s) contactando ipinfo.io para {ip_address}.")
        result["error"] = "Timeout IPinfo"
    except requests.exceptions.HTTPError as http_err:
        status = http_err.response.status_code
        err_msg = f"Error HTTP {status} de ipinfo.io para {ip_address}"
        try: details = http_err.response.json().get('error',{}).get('message',''); err_msg += f" ({details})" if details else ""
        except: pass
        if status in (401, 403): err_msg += " (Token inválido?)"; result["error"] = "Token Inválido/Prohibido"
        elif status == 404: err_msg += " (IP no encontrada?)"; result["error"] = "No Encontrado (ipinfo)"
        elif status == 429: err_msg += " (Límite API?)"; result["error"] = "Límite API Excedido"
        else: result["error"] = f"HTTP Error {status}"
        logger.error(err_msg)
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Error Conexión ipinfo.io ({ip_address}): {conn_err}")
        result["error"] = "Error de Conexión"
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Error Red Genérico ipinfo.io ({ip_address}): {req_err}")
        result["error"] = "Error de Red"
    except json.JSONDecodeError:
        body_preview = response.text[:200] if 'response' in locals() else "N/A"
        logger.error(f"Respuesta inválida (no JSON) ipinfo.io ({ip_address}). Body: {body_preview}...")
        result["error"] = "Respuesta Inválida"
    except Exception as e:
        logger.error(f"Error inesperado ipinfo ({ip_address}): {e}", exc_info=True)
        result["error"] = "Error Interno (IPinfo)"

    for key in ["isp", "city", "region", "country", "hostname"]: result.setdefault(key, "N/A")

    cache[ip_address] = result
    return result
