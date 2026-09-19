# core/client.py
"""
Client Factory - sozdaniye UnifiedTelegramClient s nastroykami Hydra.
"""

import logging
from typing import Optional

from .lib.telethon_mcub import UnifiedTelegramClient
from hydra_kernel.mtproxy import connection_class_for_secret

logger = logging.getLogger(__name__)


def get_client(
    session_name: str,
    api_id: int,
    api_hash: str,
    proxy: dict = None,
    device_model: str = "Hydra Dragon X1",
    system_version: str = "Android 14",
    app_version: str = "Hydra 4.0 MCUB",
) -> UnifiedTelegramClient:
    """
    Factory dlya sozdaniya UnifiedTelegramClient s nastroykami Hydra.

    Args:
        session_name: Imya sessii
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        proxy: {'addr': str, 'port': int, 'secret': str}
        device_model: Model ustroystva
        system_version: Versiya OS
        app_version: Versiya prilozheniya

    Returns:
        UnifiedTelegramClient instance
    """
    kwargs = {
        "device_model": device_model,
        "system_version": system_version,
        "app_version": app_version,
    }

    if proxy:
        secret = proxy.get("secret", "")
        kwargs["proxy"] = (proxy["addr"], proxy["port"], secret)
        kwargs["connection"] = connection_class_for_secret(secret)

    client = UnifiedTelegramClient(
        session_name,
        api_id,
        api_hash,
        **kwargs
    )

    logger.info(f"Client created: {session_name}")
    return client
