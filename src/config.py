import os
import logging
from pathlib import Path
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv, set_key, find_dotenv
    _dotenv_available = True
except ImportError:
    _dotenv_available = False

logger = logging.getLogger(__name__)

IPINFO_URL = "https://ipinfo.io/{ip}/json?token={token}"
DEFAULT_TZ = "UTC"

def get_dotenv_path() -> Path:
    """Encuentra la ruta al archivo .env más cercano."""
    script_dir = Path(__file__).parent.resolve()
    env_path_script = script_dir / ".env"
    if env_path_script.is_file():
        logger.debug(f"Found .env in script dir: {env_path_script}")
        return env_path_script
    if _dotenv_available:
        found_path_str = find_dotenv(raise_error_if_not_found=False, usecwd=True)
        if found_path_str:
            found_path = Path(found_path_str)
            logger.debug(f"Found .env via find_dotenv: {found_path}")
            if found_path.is_file():
                return found_path
    logger.debug(
        f"No .env found elsewhere, defaulting to path in script dir: {env_path_script}"
    )
    return env_path_script

def load_config() -> Tuple[Optional[str], Optional[str]]:
    """Carga las claves API desde el archivo .env encontrado."""
    if not _dotenv_available:
        logger.error("Falta 'python-dotenv'. No se pueden cargar claves API.")
        return None, None
    env_path = get_dotenv_path()
    load_dotenv(dotenv_path=env_path, override=True)
    gemini_key = os.getenv("GEMINI_API_KEY")
    ipinfo_token = os.getenv("IPINFO_TOKEN")
    if env_path.is_file():
        logger.info(f"Configuración cargada desde: {env_path}")
    else:
        logger.warning(f"No se encontró archivo .env en {env_path} o directorios sup.")
    return gemini_key, ipinfo_token

def save_api_keys(gemini_key: str, ipinfo_token: str) -> bool:
    """Guarda o actualiza las claves API en el archivo .env encontrado/designado."""
    if not _dotenv_available:
        logger.error("Falta 'python-dotenv'. No se pueden guardar claves API.")
        return False
    env_path = get_dotenv_path()
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        set_key(str(env_path), "GEMINI_API_KEY", gemini_key, quote_mode="never")
        set_key(str(env_path), "IPINFO_TOKEN", ipinfo_token, quote_mode="never")
        logger.info(f"Claves API guardadas/actualizadas en: {env_path}")
        return True
    except Exception as e:
        logger.error(f"No se pudieron guardar claves API en {env_path}: {e}", exc_info=True)
        return False
