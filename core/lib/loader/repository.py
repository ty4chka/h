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


def parse_repo_modules_list(text: str) -> "list[str]":
    """Parse a repository module list file (как в MCUB-fork).

    ``modules.ini`` remains the legacy source, while ``full.txt`` can provide
    the same line-based format.  Entries may be plain module names or
    ``name.py`` filenames; comments and empty lines are ignored.
    """

    modules: list = []
    seen: set = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        for marker in (" #", " ;"):
            if marker in line:
                line = line.split(marker, maxsplit=1)[0].strip()
        if line.endswith(".py"):
            line = line[:-3]
        if not line or line in seen:
            continue
        seen.add(line)
        modules.append(line)
    return modules


def merge_repo_modules_lists(*lists: "list[str]") -> "list[str]":
    """Merge repository module lists with order-preserving de-duplication."""

    merged: list = []
    seen: set = set()
    for modules in lists:
        for module in modules:
            if module in seen:
                continue
            seen.add(module)
            merged.append(module)
    return merged


class RepositoryManager:
    """Менеджер репозиториев (совместимость с MCUB-fork core.lib.loader).

    В Hydra рабочие операции с репозиториями реализует адаптер
    McubKernelInterface (add/remove/list/download). Здесь — лёгкий
    façade поверх интерфейса ядра, чтобы модули могли импортировать
    привычное имя.
    """

    def __init__(self, kernel=None) -> None:
        self.kernel = kernel

    def get_repositories(self) -> dict:
        k = self.kernel
        if k is None:
            return {}
        repos = getattr(k, "repositories", {})
        return dict(repos) if isinstance(repos, dict) else {}

    async def get_modules_list(self, url: str):
        k = self.kernel
        if k is None:
            return []
        getter = getattr(k, "get_repo_modules_list", None)
        if callable(getter):
            return await getter(url)
        return []

    async def download_module(self, url: str, name: str):
        k = self.kernel
        if k is None:
            return None
        getter = getattr(k, "download_module_from_repo", None)
        if callable(getter):
            return await getter(url, name)
        return None


__all__ = [
    "RepositoryManager",
    "merge_repo_modules_lists",
    "parse_repo_modules_list",
    "validate_remote_url",
]
