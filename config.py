"""Конфиг Hydra.

Источники (по приоритету): переменные окружения → data/config.json → дефолты.
В коде НЕТ секретов: api_id/api_hash/secret/owner приходят только из окружения
или локального файла. Старые имена (api_id, api_hash, prefix, PROXY, ...)
сохранены для обратной совместимости.

Переменные окружения:
    HYDRA_API_ID, HYDRA_API_HASH, HYDRA_OWNER_ID, HYDRA_PREFIX,
    HYDRA_LANGUAGE, HYDRA_PROXY_ENABLED, HYDRA_PROXY_ADDR,
    HYDRA_PROXY_PORT, HYDRA_PROXY_SECRET
"""

import json
import os
from pathlib import Path

DATA_DIR = Path("data")
CONFIG_FILE = DATA_DIR / "config.json"


def _file_cfg() -> dict:
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        pass
    return {}


_FILE = _file_cfg()


def _get(env: str, key: str, default: str = "") -> str:
    value = os.environ.get(env)
    if value in (None, ""):
        value = str(_FILE.get(key, default))
    return value


api_id = int(_get("HYDRA_API_ID", "api_id", "0") or 0)
api_hash = _get("HYDRA_API_HASH", "api_hash", "")
OWNER_ID = int(_get("HYDRA_OWNER_ID", "owner_id", "0") or 0)
language = _get("HYDRA_LANGUAGE", "language", "ru")

PROXY_ENABLED = _get("HYDRA_PROXY_ENABLED", "proxy_enabled", "") in ("1", "true", "yes", "on")
PROXY = {
    "addr": _get("HYDRA_PROXY_ADDR", "proxy_addr", ""),
    "port": int(_get("HYDRA_PROXY_PORT", "proxy_port", "0") or 0),
    "secret": _get("HYDRA_PROXY_SECRET", "proxy_secret", ""),
}


def get_prefix() -> str:
    """Префикс: env → data/config.json → legacy data/hydra_config.json → '.'."""
    env = os.environ.get("HYDRA_PREFIX")
    if env:
        return env
    if _FILE.get("prefix"):
        return str(_FILE["prefix"])
    try:  # старый формат конфига — обратная совместимость
        legacy = DATA_DIR / "hydra_config.json"
        if legacy.exists():
            return json.loads(legacy.read_text(encoding="utf-8")).get("core", {}).get("prefix", ".")
    except (ValueError, OSError):
        pass
    return "."


def reload_prefix() -> None:
    global prefix
    prefix = get_prefix()


def secrets_present() -> bool:
    """Минимум для боевого запуска: api_id + api_hash."""
    return bool(api_id and api_hash)


prefix = get_prefix()
