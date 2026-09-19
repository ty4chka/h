# core/kernel.py
"""
HydraKernel - Glavnoe yadro UserBot.
Ob'yedinyayet TelegramClient, MCUB interfeys, event dispatcher i module registry.
"""

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Union

from telethon import TelegramClient, events
from telethon.tl.types import User

from .lib.telethon_mcub import (
    UnifiedTelegramClient,
    MCUBKernelInterface,
    auto_register_mcub_module,
    patch_adapter_for_unified_client,
    _safe_edit_patch,
)
from .events.dispatcher import EventDispatcher
from .modules import register as register_module, get as get_module

logger = logging.getLogger(__name__)


class HydraKernel:
    """
    Glavnoe yadro Hydra UserBot.

    Otvetstvennost':
    - Upravleniye TelegramClient (UnifiedTelegramClient)
    - Registratsiya i upravleniye modulyami
    - Event dispatching
    - MCUB sovmestimost'
    - Konfiguratsiya i DB

    Usage:
        kernel = HydraKernel(session_name, api_id, api_hash)
        await kernel.start()
        kernel.register_command('ping', ping_handler)
        kernel.register_module(MyModuleClass)
        await kernel.run()
    """

    def __init__(
        self,
        session_name: str,
        api_id: int,
        api_hash: str,
        proxy: dict = None,
        device_model: str = "Hydra Dragon X1",
        system_version: str = "Android 14",
        app_version: str = "Hydra 4.0 MCUB",
    ):
        self.session_name = session_name
        self.api_id = api_id
        self.api_hash = api_hash
        self.proxy = proxy

        # Client kwargs
        client_kwargs = {
            "device_model": device_model,
            "system_version": system_version,
            "app_version": app_version,
        }
        if proxy:
            from telethon import connection
            client_kwargs["proxy"] = (proxy["addr"], proxy["port"], proxy.get("secret", ""))
            client_kwargs["connection"] = connection.ConnectionTcpMTProxyRandomizedIntermediate

        # Unified Telegram Client
        self.client = UnifiedTelegramClient(
            session_name, api_id, api_hash, **client_kwargs
        )

        # MCUB Kernel Interface (shortcut)
        self.mcub = self.client.mcub_kernel

        # Event Dispatcher
        self.dispatcher = EventDispatcher(self.client)

        # Module Registry
        self._modules: Dict[str, Any] = {}
        self._handlers: List[Any] = []
        self._commands: Dict[str, Callable] = {}

        # State
        self._started = False
        self._me: Optional[User] = None

        logger.info(f"HydraKernel initialized: {session_name}")

    # ============================================
    # LIFECYCLE
    # ============================================

    async def start(self) -> User:
        """Zapusk client i polucheniye info o polzovatele."""
        await self.client.start()
        self._me = await self.client.get_me()
        self._started = True

        # Patch adapter.py dlya sovmestimosti
        patch_adapter_for_unified_client()

        logger.info(f"Kernel started: {self._me.first_name} (@{self._me.username})")
        return self._me

    async def stop(self):
        """Ostanovka client."""
        await self.client.disconnect()
        self._started = False
        logger.info("Kernel stopped")

    async def run(self):
        """Blokiruyushchiy zapusk do otklyucheniya."""
        try:
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        finally:
            await self.stop()

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def me(self) -> Optional[User]:
        return self._me

    # ============================================
    # COMMAND REGISTRATION
    # ============================================

    def register_command(
        self,
        name: str,
        handler: Callable,
        aliases: List[str] = None,
        description: str = "",
        outgoing_only: bool = True,
    ):
        """
        Registratsiya komandy Hydra.

        Args:
            name: Imya komandy (bez prefixa)
            handler: async def handler(event)
            aliases: Spisok aliasov
            description: Opisaniye komandy
            outgoing_only: Tol'ko iskhodyashchiye soobshcheniya
        """
        aliases = aliases or []
        prefix = getattr(sys.modules.get('config'), 'prefix', '.')

        # Osnovnoy pattern
        pattern = rf"(?i)^{re.escape(prefix)}{re.escape(name)}(?:\s|$)"

        async def wrapper(event):
            _safe_edit_patch(event)
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Command '{name}' error: {e}", exc_info=True)
                await self._handle_command_error(event, e)

        # Registratsiya osnovnoy komandy
        self.client.on(events.NewMessage(pattern=pattern, outgoing=outgoing_only))(wrapper)
        self._commands[name] = {
            'handler': handler,
            'description': description,
            'aliases': aliases,
        }

        # Registratsiya aliasov
        for alias in aliases:
            alias_pattern = rf"(?i)^{re.escape(prefix)}{re.escape(alias)}(?:\s|$)"
            self.client.on(events.NewMessage(pattern=alias_pattern, outgoing=outgoing_only))(wrapper)

        logger.debug(f"Command registered: {prefix}{name}")

    def unregister_command(self, name: str):
        """Udaleniye komandy."""
        if name in self._commands:
            del self._commands[name]
            logger.debug(f"Command unregistered: {name}")

    def get_commands(self) -> Dict[str, Dict]:
        """Polucheniye spiska vsekh komand."""
        return dict(self._commands)

    # ============================================
    # WATCHER REGISTRATION
    # ============================================

    def register_watcher(
        self,
        handler: Callable,
        incoming_only: bool = True,
        outgoing_only: bool = False,
        pattern: str = None,
        chats = None,
    ):
        """
        Registratsiya watcher (nablyudatel).

        Args:
            handler: async def handler(event)
            incoming_only: Tol'ko vkhodyashchiye
            outgoing_only: Tol'ko iskhodyashchiye
            pattern: Regex pattern
            chats: Spisok chat ID
        """
        async def wrapper(event):
            _safe_edit_patch(event)
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Watcher error: {e}", exc_info=True)

        kwargs = {}
        if pattern:
            kwargs['pattern'] = pattern
        if incoming_only and not outgoing_only:
            kwargs['incoming'] = True
        if outgoing_only:
            kwargs['outgoing'] = True
        if chats:
            kwargs['chats'] = chats

        handler_obj = self.client.on(events.NewMessage(**kwargs))(wrapper)
        self._handlers.append(handler_obj)
        logger.debug("Watcher registered")

    # ============================================
    # MODULE REGISTRATION
    # ============================================

    def register_module(self, module_class, name: str = None):
        """
        Registratsiya modulya (Hydra ili MCUB).

        Avtomaticheski opredelyayet tip modulya i registreruyet pravilno.
        """
        if name is None:
            name = getattr(module_class, 'name', module_class.__name__.lower())

        # Proveryayem, eto MCUB modul'?
        if hasattr(module_class, '__bases__') and any(
            'ModuleBase' in str(base) for base in module_class.__bases__
        ):
            # MCUB modul' - ispol'zuyem auto_register
            instance = auto_register_mcub_module(self.client, module_class, name)
            self._modules[name] = {
                'instance': instance,
                'type': 'mcub',
                'class': module_class,
            }
            logger.info(f"MCUB module registered: {name}")
        else:
            # Hydra modul' - obychnaya registratsiya
            instance = module_class()
            if hasattr(instance, 'setup'):
                instance.setup(self.client)
            self._modules[name] = {
                'instance': instance,
                'type': 'hydra',
                'class': module_class,
            }
            logger.info(f"Hydra module registered: {name}")

        # Registreruem v global'nom registry
        register_module(name, self._modules[name])
        return instance

    def unregister_module(self, name: str):
        """Udaleniye modulya."""
        if name in self._modules:
            module = self._modules[name]
            if hasattr(module['instance'], 'on_unload'):
                asyncio.create_task(self._safe_unload(module['instance']))
            self.client.unregister_mcub_module(name)
            del self._modules[name]
            logger.info(f"Module unregistered: {name}")

    async def _safe_unload(self, instance):
        try:
            await instance.on_unload()
        except Exception as e:
            logger.error(f"on_unload error: {e}")

    def get_modules(self) -> Dict[str, Dict]:
        """Spisok vsekh moduley."""
        return dict(self._modules)

    def get_module(self, name: str) -> Any:
        """Polucheniye modulya po imeni."""
        mod = self._modules.get(name)
        return mod['instance'] if mod else None

    # ============================================
    # INLINE / CALLBACK REGISTRATION
    # ============================================

    def register_inline(self, name: str, handler: Callable):
        """Registratsiya inline handler (cherez MCUB interface)."""
        self.mcub.register_inline_handler(name, handler)
        logger.debug(f"Inline handler registered: {name}")

    def register_callback(self, prefix: str, handler: Callable):
        """Registratsiya callback handler."""
        self.mcub.register_callback_handler(prefix, handler)
        logger.debug(f"Callback handler registered: {prefix}")

    # ============================================
    # CONFIG & DB
    # ============================================

    async def get_config(self, module: str, key: str = None, default=None):
        """Polucheniye konfiga modulya."""
        cfg = await self.mcub.get_module_config(module, {})
        if key is None:
            return cfg
        return cfg.get(key, default)

    async def set_config(self, module: str, key: str, value):
        """Ustanovka konfiga modulya."""
        cfg = await self.mcub.get_module_config(module, {})
        cfg[key] = value
        await self.mcub.save_module_config(module, cfg)

    async def db_get(self, module: str, key: str):
        """Polucheniye iz DB."""
        return await self.mcub.db_get(module, key)

    async def db_set(self, module: str, key: str, value):
        """Sokhraneniye v DB."""
        await self.mcub.db_set(module, key, value)

    # ============================================
    # CONVERSATION
    # ============================================

    async def conversation(self, chat_id: int):
        """Sozdaniye conversation s chatom."""
        return await self.mcub.conversation(chat_id)

    # ============================================
    # UTILITIES
    # ============================================

    def is_admin(self, user_id: int) -> bool:
        return self.mcub.is_admin(user_id)

    def log(self, level: str, message: str):
        getattr(logger, level, logger.info)(message)

    async def send_message(self, entity, message: str, **kwargs):
        return await self.client.send_message(entity, message, **kwargs)

    async def edit_message(self, entity, message, text: str, **kwargs):
        return await self.client.edit_message(entity, message, text, **kwargs)

    # ============================================
    # INTERNAL
    # ============================================

    async def _handle_command_error(self, event, error: Exception):
        """Obrabotka oshibok komand."""
        try:
            from utils.misc import edit_or_reply
            await edit_or_reply(event, f"<b>Error:</b> <code>{str(error)[:100]}</code>")
        except Exception:
            pass

    def __repr__(self):
        status = "running" if self._started else "stopped"
        return f"<HydraKernel {self.session_name} {status}>"
