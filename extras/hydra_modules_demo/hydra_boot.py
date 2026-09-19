"""Hydra dispatcher: связывает hydra_kernel с боевым Telethon-клиентом.

m.py при старте вызывает setup(client). Ядро грузит свои модули из
hydra_modules/ (ping/help/info/settings/terminal/translations), а родные
модули HYDRA остаются в modules/ и работают через родной диспетчер MCUB.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

_HYDRA = None


def setup(client) -> None:
    """Точка входа для m.py (вызывается синхронно из async-контекста)."""
    asyncio.ensure_future(_boot(client))


async def _boot(client) -> None:
    global _HYDRA
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
        records, errors = await hydra.loader.load_dir(
            "hydra_modules", framework="hydra", exclude=("hydra_boot",)
        )
        for name, err in errors:
            logger.error("hydra: модуль %s не встал: %s", name, err)
        _HYDRA = hydra
        logger.info("hydra kernel online: %d модулей", len(records))
    except Exception as e:  # noqa: BLE001 — не роняем бота из-за ядра
        logger.error("hydra boot error: %s", e, exc_info=True)


def get_hydra():
    return _HYDRA
