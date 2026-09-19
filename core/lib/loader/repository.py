# core/lib/loader/repository.py
# Валидация удалённых URL для установки модулей (как в MCUB).
from __future__ import annotations

from urllib.parse import urlparse

_ALLOWED_HOSTS = (
    "raw.githubusercontent.com",
    "github.com",
    "gist.githubusercontent.com",
    "gitlab.com",
)


def validate_remote_url(url: str) -> tuple[bool, str | None]:
    """Проверить URL модуля. Возвращает (ok, ошибка|None)."""
    if not isinstance(url, str) or not url.strip():
        return False, "пустой URL"
    try:
        parsed = urlparse(url.strip())
    except ValueError as e:
        return False, f"некорректный URL: {e}"
    if parsed.scheme not in ("http", "https"):
        return False, "только http(s)"
    host = (parsed.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS):
        return False, f"хост {host or '?'} не разрешён"
    if not parsed.path or parsed.path in ("/", ""):
        return False, "нет пути к файлу"
    return True, None
