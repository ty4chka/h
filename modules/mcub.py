"""Единый диспетчер Hydra: поднимает hydra_kernel поверх боевого клиента
и грузит ВСЕ родные модули через compat-слой (один движок для всех
совместимостей: hydra / MCUB class-style / register(kernel) / setup(client) /
<cmd>_handler).

m.py вызывает setup(client); дальше await wait_ready() даёт записи для таблицы.
Официальная версия этого файла (под MCUB-движок) лежит в extras/official_mcub.py.
"""

import asyncio
import hashlib
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_HYDRA = None
_BOOT_TASK = None
_RESULT = None
BOOT_TIME = 0.0  # секунды на загрузку модулей (для строки boot: X.XXs)
MODULES_DIR = Path(__file__).resolve().parent


async def _load_owned_modules(hydra):
    """Загрузить родные модули и сохранённые пользователем MCUB-модули.

    ``Loader.load_dir`` намеренно не обходит каталоги рекурсивно. Поэтому
    modules/mcub_mods раньше отображался в TUI, но не попадал в единый runtime.
    Загружаем его отдельной волной тем же MCUB adapter'ом.
    """

    records, errors = await hydra.loader.load_dir(
        MODULES_DIR,
        framework="auto",
        exclude=("mcub", "__init__"),
        allow_unsafe=True,
    )
    mcub_dir = MODULES_DIR / "mcub_mods"
    if mcub_dir.is_dir():
        # Репозитории модулей нередко оставляют рядом старое имя файла. Не
        # запускаем байт-в-байт копию второй раз: она зарегистрирует одинаковые
        # команды и может отправить два ответа на одно сообщение.
        seen_sources = {}
        duplicate_stems = []
        for source in sorted(mcub_dir.glob("*.py")):
            if source.stem == "__init__":
                continue
            digest = hashlib.sha256(source.read_bytes()).digest()
            original = seen_sources.setdefault(digest, source)
            if original is not source:
                duplicate_stems.append(source.stem)
                logger.debug("skipping duplicate MCUB module %s (same as %s)", source.name, original.name)

        mcub_records, mcub_errors = await hydra.loader.load_dir(
            mcub_dir,
            framework="mcub",
            exclude=("__init__", *duplicate_stems),
            allow_unsafe=True,
        )
        records.extend(mcub_records)
        errors.extend(mcub_errors)
    return records, errors


async def reload_all():
    """Горячая перезагрузка всех модулей (хоткей r в менеджере запуска)."""
    global _RESULT
    hydra = _HYDRA
    if hydra is None:
        return [], [("engine", Exception("движок не запущен"))]
    for name in list(getattr(hydra.registry, "_records", {}).keys()):
        try:
            await hydra.loader.unload(name)
        except Exception as e:  # noqa: BLE001
            logger.error("unload %s: %s", name, e)
    t0 = time.monotonic()
    records, errors = await _load_owned_modules(hydra)
    global BOOT_TIME
    BOOT_TIME = time.monotonic() - t0
    _RESULT = (records, errors)
    return records, errors


def setup(client) -> None:
    """Точка входа для m.py (вызывается синхронно из async-контекста)."""
    global _BOOT_TASK
    _BOOT_TASK = asyncio.ensure_future(_boot(client))


async def _boot(client) -> None:
    global _HYDRA, _RESULT
    try:
        import config  # конфиг m.py: prefix и т.п.
        from hydra_kernel.app import Hydra
        from hydra_kernel.kernel.transport import TelethonTransport

        me = await client.get_me()
        transport = TelethonTransport(client=client)
        hydra = Hydra(
            transport=transport,
            owner_id=me.id,
            prefix=getattr(config, "prefix", ".") or ".",
        )
        await hydra.start()
        # allow_unsafe: это СОБСТВЕННЫЕ модули пользователя (subprocess в
        # terminal и т.п. — легально); сканер остаётся строгим для .mload
        global BOOT_TIME
        t0 = time.monotonic()
        records, errors = await _load_owned_modules(hydra)
        BOOT_TIME = time.monotonic() - t0
        for name, err in errors:
            logger.error("engine: модуль %s не встал: %s", name, err)
        _HYDRA = hydra
        _RESULT = (records, errors)
        logger.info("single engine online: %d модулей", len(records))
    except Exception as e:  # noqa: BLE001 — не роняем бота из-за ядра
        logger.error("engine boot error: %s", e, exc_info=True)
        _RESULT = ([], [(type(e).__name__, e)])


async def wait_ready(timeout: float = 30.0):
    """Ждёт завершения загрузки; возвращает (records, errors)."""
    if _BOOT_TASK is not None:
        try:
            await asyncio.wait_for(asyncio.shield(_BOOT_TASK), timeout)
        except asyncio.TimeoutError:
            logger.error("engine: boot timeout %ss", timeout)
    return _RESULT or ([], [])


def get_hydra():
    return _HYDRA
