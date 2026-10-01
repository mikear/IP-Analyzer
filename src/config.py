import os
import sys
import logging
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv, set_key
    _dotenv_available = True
except ImportError:
    _dotenv_available = False

logger = logging.getLogger(__name__)

IPINFO_URL = "https://ipinfo.io/{ip}/json?token={token}"
DEFAULT_TZ = "UTC"

def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))

def _installed_by_setup() -> bool:
    """True si la aplicación se instaló con el setup de Inno Setup (registro)."""
    if not _is_frozen():
        return False
    try:
        import winreg
    except ImportError:
        return False
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, r"Software\IP-Analyzer") as key:
                winreg.QueryValueEx(key, "InstalledBySetup")
            return True
        except OSError:
            continue
    return False


def _dir_writable(path: Path) -> bool:
    try:
        probe = path / f".write_test_{os.getpid()}"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False

def _user_dotenv_path() -> Path:
    """Ruta de configuración para la app instalada (%APPDATA%\\IP-Analyzer\\.env)."""
    base = os.environ.get("APPDATA") or tempfile.gettempdir()
    return Path(base) / "IP-Analyzer" / ".env"

def get_dotenv_path() -> Path:
    """Ruta al archivo .env.

    - Desarrollo (no congelado): busca desde src/ hacia arriba.
    - Congelado (exe): junto al ejecutable si el directorio es escribible
      (modo portable); si no (p. ej. Program Files), en %APPDATA% (instalado).
    """
    if _is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        if _installed_by_setup():
            user_path = _user_dotenv_path()
            try:
                user_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.warning(f"No se pudo crear {user_path.parent}; usando {exe_dir / '.env'}")
                return exe_dir / ".env"
            return user_path
        if _dir_writable(exe_dir):
            return exe_dir / ".env"
        user_path = _user_dotenv_path()
        try:
            user_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning(f"No se pudo crear {user_path.parent}; usando {exe_dir / '.env'}")
            return exe_dir / ".env"
        return user_path

    script_dir = Path(__file__).parent.resolve()
    for directory in [script_dir, *script_dir.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            logger.debug(f"Found .env at: {candidate}")
            return candidate
    logger.debug(
        f"No .env found, defaulting to path in script dir: {script_dir / '.env'}"
    )
    return script_dir / ".env"

def load_config() -> str:
    """Carga las claves API desde el archivo .env encontrado y devuelve el token IPINFO."""
    if not _dotenv_available:
        logger.error("Falta 'python-dotenv'. No se pueden cargar claves API.")
        return ""
    env_path = get_dotenv_path()
    load_dotenv(dotenv_path=env_path, override=True)
    ipinfo_token = os.getenv("IPINFO_TOKEN", "")
    if env_path.is_file():
        logger.info(f"Configuración cargada desde: {env_path}")
    else:
        logger.info(f"No se encontró archivo .env en {env_path} (modo sin token).")
    return ipinfo_token

def save_api_keys(ipinfo_token: str = "") -> bool:
    """Guarda o actualiza el token de API IPINFO en el archivo .env encontrado/designado.

    Un token vacío borra la clave guardada (revocación real, no un falso éxito).
    """
    if not _dotenv_available:
        logger.error("Falta 'python-dotenv'. No se pueden guardar claves API.")
        return False
    env_path = get_dotenv_path()
    if _save_to(env_path, ipinfo_token):
        if ipinfo_token.strip():
            logger.info(f"Claves API guardadas/actualizadas en: {env_path}")
        else:
            logger.info(f"Token IPINFO eliminado de: {env_path}")
        return True
    # Directorio no escribible (p. ej. Program Files): reintenta en datos de usuario.
    fallback = _user_dotenv_path()
    if env_path != fallback:
        logger.warning(f"Reintentando guardar el token en {fallback}")
        return _save_to(fallback, ipinfo_token)
    return False

def _save_to(env_path: Path, ipinfo_token: str) -> bool:
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        if not env_path.is_file():
            env_path.write_text("", encoding="utf-8")
        set_key(str(env_path), "IPINFO_TOKEN", ipinfo_token.strip(), quote_mode="never")
        return True
    except Exception as e:
        logger.error(f"No se pudieron guardar claves API en {env_path}: {e}", exc_info=True)
        return False
