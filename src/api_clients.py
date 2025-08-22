import logging
import ipaddress
import json
import re
from typing import Dict, List, Optional, Any, Tuple

import requests
import google.generativeai as genai

from config import IPINFO_URL

logger = logging.getLogger(__name__)

def validate_api_keys(gemini_key: Optional[str], ipinfo_token: Optional[str]) -> Tuple[bool, bool]:
    """Valida las claves API de Gemini e ipinfo.io."""
    gemini_ok = False
    ipinfo_ok = False

    # Validar Gemini API Key
    if gemini_key:
        try:
            genai.configure(api_key=gemini_key)
            # Realizar una llamada de prueba para validar la clave
            model = genai.GenerativeModel("gemini-1.5-flash-latest")
            model.generate_content(
                "test", 
                generation_config=genai.types.GenerationConfig(max_output_tokens=1),
                request_options={"timeout": 10}
            )
            gemini_ok = True
            logger.info("Clave API de Gemini validada exitosamente.")
        except Exception as e:
            logger.error(f"Error al validar la clave API de Gemini: {e}")

    # Validar ipinfo.io Token
    if ipinfo_token:
        try:
            # Realizar una llamada a un endpoint de prueba o a una IP conocida
            response = requests.get(f"https://ipinfo.io/8.8.8.8?token={ipinfo_token}", timeout=10)
            if response.status_code == 200:
                ipinfo_ok = True
                logger.info("Token de ipinfo.io validado exitosamente.")
            else:
                logger.error(f"Error al validar el token de ipinfo.io. Código de estado: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de red al validar el token de ipinfo.io: {e}")

    return gemini_ok, ipinfo_ok

def is_valid_ip(ip_str: str) -> bool:
    """Verifica si una cadena es una dirección IP válida (IPv4 o IPv6)."""
    if not isinstance(ip_str, str) or not ip_str or ip_str.isspace():
        return False
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False

def extract_ip_data_with_gemini(
    text_content: str,
    api_key: str
) -> Optional[List[Dict[str, str]]]:
    """Extrae IPs y timestamps usando la API de Gemini."""
    if not api_key:
        logger.critical("Clave API Gemini no proporcionada o no cargada.")
        return None

    logger.info("Configurando cliente Gemini...")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        logger.info(f"Usando modelo Gemini: {model.model_name}")
    except Exception as config_err:
        logger.critical(
            f"Error al configurar la API Gemini: {config_err}", exc_info=True
        )
        logger.critical("Verifica clave API y conexión a internet.")
        return None

    prompt = f"""Analiza el siguiente texto y extrae todas las direcciones IP (IPv4 o IPv6 válidas) junto con la marca de tiempo (fecha y hora) más relevante y cercana asociada a cada IP.

Reglas estrictas para la respuesta:
1.  Responde ÚNICA Y EXCLUSIVAMENTE con una lista JSON válida.
2.  La respuesta DEBE comenzar con `[` y terminar con `]`.
3.  NO incluyas NINGÚN texto antes de `[` ni después de `]`, ni siquiera marcadores de formato como ```json.
4.  Cada objeto JSON en la lista debe tener exactamente dos claves:
    - "ip_address": string (La dirección IP válida encontrada).
    - "timestamp_str": string (La cadena de texto original de la fecha/hora asociada. Si no hay timestamp relevante cerca de la IP, usa una cadena vacía "").
5.  Ignora direcciones IP de rangos privados (ej. 192.168.x.x, 10.x.x.x, 172.16-31.x.x, fe80::) a menos que el contexto sugiera fuertemente que son relevantes.
6.  Si una IP aparece varias veces con el mismo timestamp cercano, inclúyela solo una vez. Si aparece con timestamps diferentes, incluye cada par único.
7.  Valida internamente que las IPs extraídas sean sintácticamente correctas.

Ejemplo de respuesta PERFECTA:
[
  {{"ip_address": "203.0.113.45", "timestamp_str": "2024-03-15 10:30:00 UTC"}},
  {{"ip_address": "8.8.4.4", "timestamp_str": "Mar 15 2024 08:15:22 -0500"}},
  {{"ip_address": "198.51.100.10", "timestamp_str": ""}},
  {{"ip_address": "2001:db8:abcd:0012::1", "timestamp_str": "2024/03/14 15:45:30.123"}}
]

Texto a analizar:
--------------------
{text_content}
--------------------
"""

    extracted_data: Optional[List[Dict[str, str]]] = None
    response = None
    raw_text = ""

    try:
        logger.info("Enviando solicitud a Gemini API (puede tardar)...")
        safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
        request_options = {"timeout": 120}
        response = model.generate_content(
            prompt, safety_settings=safety_settings, request_options=request_options
        )

        if response.parts:
            raw_text = "".join(
                part.text for part in response.parts if hasattr(part, "text")
            ).strip()
        elif hasattr(response, "text"):
            raw_text = response.text.strip()
        else:
            raw_text = ""

        if not raw_text and response.prompt_feedback and response.prompt_feedback.block_reason:
            block_reason = response.prompt_feedback.block_reason
            details = response.prompt_feedback.block_reason_message or "No details."
            logger.critical(f"Respuesta Gemini bloqueada. Razón: {block_reason}. {details}")
            if response.prompt_feedback.safety_ratings:
                logger.critical("Safety Ratings:")
                for r in response.prompt_feedback.safety_ratings: logger.critical(f" - {r.category}: {r.probability}")
            return None
        elif not raw_text:
            logger.critical("Respuesta de Gemini vacía o sin texto extraíble.")
            return None

        logger.info(f"Respuesta cruda de Gemini recibida ({len(raw_text)} caracteres).")
        log_limit = 500
        logger.debug(
            f"Inicio respuesta cruda Gemini:\n{raw_text[:log_limit]}{'...' if len(raw_text)>log_limit else ''}"
        )

        # --- CORRECCIÓN: Limpiar formato Markdown y validar ---
        potential_json_str = raw_text
        if potential_json_str.startswith("```json"):
            potential_json_str = potential_json_str[7:]
        if potential_json_str.endswith("```"):
            potential_json_str = potential_json_str[:-3]
        potential_json_str = potential_json_str.strip()

        if not (potential_json_str.startswith('[') and potential_json_str.endswith(']')):
            logger.critical("No se encontró bloque JSON válido [...] en la respuesta de la API.")
            logger.critical(f"Respuesta completa (cruda):\n{raw_text}")
            return None
        # --- FIN DE LA CORRECCIÓN ---

        try:
            extracted_data = json.loads(potential_json_str)
            logger.info("Parseo JSON inicial exitoso.")
        except json.JSONDecodeError as json_err:
            logger.critical(f"Error Crítico de Parseo JSON: {json_err}")
            context_len = 40
            start = max(0, json_err.pos - context_len)
            end = min(len(potential_json_str), json_err.pos + context_len)
            context = potential_json_str[start:end].replace("\n", " ")
            pointer = " " * (json_err.pos - start) + "^"
            logger.critical(f"  Contexto (aprox.): {context}")
            logger.critical(f"                     {pointer}")
            logger.critical(f"  Detalles: L{json_err.lineno}, C{json_err.colno}, Pos{json_err.pos}")
            return None

        if not isinstance(extracted_data, list):
            logger.critical(f"JSON parseado no es lista. Tipo: {type(extracted_data)}.")
            return None

        validated_data: List[Dict[str, str]] = []
        invalid_items_count = 0
        seen_pairs = set()
        for item in extracted_data:
            if not isinstance(item, dict) or "ip_address" not in item or "timestamp_str" not in item:
                logger.warning(f"Elemento JSON inválido omitido: {str(item)[:100]}...")
                invalid_items_count += 1
                continue

            ip_addr_raw = item.get("ip_address")
            ts_str = item.get("timestamp_str", "")

            if not isinstance(ip_addr_raw, str):
                logger.warning(f"'ip_address' no es cadena: {ip_addr_raw}. Omitiendo.")
                invalid_items_count += 1
                continue
            if ts_str is None: ts_str = ""
            elif not isinstance(ts_str, str): ts_str = str(ts_str)

            ip_addr_cleaned = ip_addr_raw.strip().replace(",", ".")
            ts_str_cleaned = ts_str.strip()

            if not is_valid_ip(ip_addr_cleaned):
                logger.warning(f"IP inválida '{ip_addr_raw}' omitida.")
                invalid_items_count += 1
                continue
            
            pair = (ip_addr_cleaned, ts_str_cleaned)
            if pair in seen_pairs: continue
            seen_pairs.add(pair)

            validated_data.append(
                {"ip_address": ip_addr_cleaned, "timestamp_str": ts_str_cleaned}
            )

        if invalid_items_count > 0:
            logger.warning(f"Se omitieron {invalid_items_count} elementos inválidos/duplicados.")
        if not validated_data and extracted_data:
            logger.warning("Gemini devolvió datos, pero ninguno pasó validación final.")
        elif not validated_data:
            logger.info("Gemini no extrajo ninguna IP/timestamp válido y único.")
            return []

        logger.info(f"Extracción Gemini completada. {len(validated_data)} IPs válidas.")
        return validated_data

    except requests.exceptions.Timeout:
        logger.critical("Timeout esperando respuesta de Gemini API.")
        logger.critical("Texto largo o API lenta? Considera aumentar timeout/reducir input.")
        return None
    except Exception as e:
        logger.critical(f"Error Inesperado Gemini: {e}", exc_info=True)
        feedback = "N/A"
        if response and hasattr(response, "prompt_feedback"): feedback = response.prompt_feedback
        logger.critical(f"  Feedback Gemini (si disponible): {feedback}")
        return None

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

        result.update({
            "isp": isp_val if isp_val else "N/A",
            "city": data.get('city') or "N/A",
            "region": data.get('region') or "N/A",
            "country": data.get('country') or "N/A",
            "hostname": data.get('hostname') or "N/A",
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
