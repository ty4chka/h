# mcub_engine/loader.py
"""
McubLoader — загрузка ОРИГИНАЛЬНЫХ (не модифицированных) модулей MCUB.

- class-style: class X(ModuleBase) с декораторами @command/@inline/@watcher/...
- functional-style: def register(kernel) с @kernel.register.command(...)

Модули исполняются как есть — вся совместимость обеспечивается
пакетами-шимами (core.*, core_inline.*, utils) и McubKernel.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("mcub_engine.loader")

MODULES_DIR = Path("modules/mcub_mods")

_loader_instance = None


def get_loader():
    global _loader_instance
    if _loader_instance is None:
        from . import get_kernel
        _loader_instance = McubLoader(get_kernel())
    return _loader_instance


class McubLoader:
    def __init__(self, kernel):
        self.kernel = kernel
        MODULES_DIR.mkdir(parents=True, exist_ok=True)

    # ========================================================
    # ОПРЕДЕЛЕНИЕ ТИПА МОДУЛЯ
    # ========================================================

    @staticmethod
    def is_mcub_code(code: str) -> bool:
        return bool(
            re.search(r"core\.lib\.loader", code)
            or re.search(r"class\s+\w+\s*\(\s*ModuleBase\s*\)", code)
            or re.search(r"def\s+register\s*\(\s*kernel\s*\)", code)
            or re.search(r"@kernel\.register\.", code)
        )

    @staticmethod
    def extract_name(code: str, fallback: str) -> str:
        m = re.search(r"^#\s*name:\s*(.+)$", code, re.MULTILINE)
        if m:
            name = m.group(1).strip()
            name = re.sub(r"-MCUB-repo$", "", name)
            if name:
                return name
        return fallback

    @staticmethod
    def extract_meta(code: str) -> dict:
        meta = {}
        for key in ("author", "version", "description"):
            m = re.search(rf"^#\s*{key}:\s*(.+)$", code, re.MULTILINE)
            if m:
                meta[key] = m.group(1).strip()
        return meta

    def _find_module_base_class(self, module):
        from core.lib.loader.module_base import ModuleBase
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, ModuleBase) and obj is not ModuleBase \
                    and obj.__module__ == module.__name__:
                return obj
        # fallback: любой наследник (на случай переэкспорта)
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, ModuleBase) and obj is not ModuleBase:
                return obj
        return None

    # ========================================================
    # ЗАГРУЗКА
    # ========================================================

    async def load_module_file(self, file_path, module_name=None, is_reload=False):
        """Загрузить модуль из файла. Возвращает (ok, message)."""
        from .proxies import (
            get_module_client, get_module_kernel, get_module_register,
        )

        file_path = Path(file_path)
        try:
            code = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Не удалось прочитать файл: {e}"

        if module_name is None:
            module_name = self.extract_name(code, file_path.stem)
        module_name = re.sub(r"[^\w\-.]", "_", module_name)

        sys_name = f"mcub_mod_{module_name}_{int(time.time() * 1000) % 10**7}"

        try:
            spec = importlib.util.spec_from_file_location(sys_name, str(file_path))
            if spec is None:
                return False, "Не удалось создать spec"
            module = importlib.util.module_from_spec(spec)
            sys.modules[sys_name] = module
            try:
                spec.loader.exec_module(module)
            except ImportError as e:
                return False, (
                    f"<b>Нет зависимости:</b> <code>{e}</code>\n"
                    f"<i>Установи: pip install {str(e).split()[-1].strip(chr(39))}</i>"
                )
            except SyntaxError as e:
                return False, f"<b>Синтаксическая ошибка:</b> {e.msg} (строка {e.lineno})"

            k = self.kernel
            cls = self._find_module_base_class(module)
            k.set_loading_module(module_name, "user")
            try:
                if cls is not None:
                    # ---------- class-style ----------
                    display_name = getattr(cls, "name", None)
                    if display_name and display_name != "Unnamed":
                        module_name = display_name

                    inst = cls(
                        get_module_kernel(k, module_name),
                        get_module_client(k, module_name),
                        get_module_register(k, module_name),
                    )
                    k._class_module_instances[module_name] = inst
                    module._class_instance = inst
                    mod_type = "class"
                elif hasattr(module, "register") and callable(module.register):
                    # ---------- functional-style ----------
                    sig = None
                    try:
                        sig = inspect.signature(module.register)
                    except (TypeError, ValueError):
                        pass
                    param = list(sig.parameters)[0] if sig and sig.parameters else "kernel"

                    if param == "kernel":
                        arg = get_module_kernel(k, module_name)
                    else:
                        arg = k._real_client  # old-style: register(client)
                    if inspect.iscoroutinefunction(module.register):
                        await module.register(arg)
                    else:
                        module.register(arg)
                    mod_type = "functional"
                else:
                    return False, (
                        "Не MCUB-модуль: нет ни ModuleBase-класса, "
                        "ни функции register(kernel)"
                    )

                k.loaded_modules[module_name] = module
            finally:
                k.clear_loading_module()

            await self._post_load(module, module_name, is_install=not is_reload,
                                  is_reload=is_reload)

            if hasattr(module, "init") and callable(module.init):
                try:
                    res = module.init()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    logger.error(f"init() failed for {module_name}: {e}")

            self._sync_help(module_name)

            cmds = [c for c, o in k.command_owners.items() if o == module_name]
            return True, (f"Модуль <code>{module_name}</code> загружен "
                          f"[{mod_type}], команд: {len(cmds)}")

        except Exception as e:
            logger.error(f"load {module_name} failed: {e}", exc_info=True)
            self.kernel.unload_module_resources(module_name)
            return False, f"<b>Ошибка загрузки:</b> <code>{e}</code>"

    async def _post_load(self, module, module_name, is_install=False, is_reload=False):
        """Autostart циклов, on_load, on_install, @method-функции."""
        k = self.kernel
        instance = getattr(module, "_class_instance", None)

        # циклы
        for lp in k._module_loops.get(module_name, []):
            lp._kernel = k
            if lp.autostart:
                try:
                    lp.start()
                except Exception as e:
                    logger.error(f"loop autostart failed ({module_name}): {e}")

        # @method функции (вызываются с kernel)
        for fn in k._module_methods.get(module_name, []):
            try:
                res = fn(getattr(instance, "kernel", k))
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(f"method {fn.__name__} failed ({module_name}): {e}")

        if instance is not None:
            # восстановление конфига из хранилища
            config = getattr(instance, "_config", None)
            if config is not None and hasattr(config, "from_dict"):
                try:
                    saved = await k.get_module_config(module_name)
                    if saved:
                        config.from_dict(saved)
                    k._live_module_configs[module_name] = config
                    k.store_module_config_schema(module_name, config)
                    saved_now = config.to_dict() if hasattr(config, "to_dict") else {}
                    to_save = {kk: vv for kk, vv in saved_now.items()
                               if vv is not None and kk != "__mcub_config__"}
                    if not saved and to_save:
                        await k.save_module_config(module_name, to_save)
                except Exception as e:
                    logger.debug(f"config restore failed ({module_name}): {e}")

            for meth_name in ("on_load",) + (("on_reload",) if is_reload else ()):
                meth = getattr(instance, meth_name, None)
                if callable(meth):
                    try:
                        res = meth()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.error(f"{meth_name} error ({module_name}): {e}")
            instance._loaded = True

            if is_install:
                for fn in getattr(instance, "_on_install_funcs", []):
                    try:
                        res = fn(instance)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.error(f"on_install error ({module_name}): {e}")

    # ========================================================
    # HELP-ИНТЕГРАЦИЯ С HYDRA
    # ========================================================

    def _sync_help(self, module_name):
        """Экспорт команд модуля в modules_help Hydra."""
        k = self.kernel
        lang = "ru"
        try:
            lang = k.config.get("language", "ru")
        except Exception:
            pass

        help_dict = {}
        for cmd, owner in k.command_owners.items():
            if owner != module_name:
                continue
            docs = k.command_docs.get(cmd, {})
            desc = docs.get(lang) or docs.get("ru") or docs.get("en") or f"Команда {cmd}"
            help_dict[cmd] = desc
        for name in k._inline_handlers:
            help_dict.setdefault(f"iq {name} <запрос>", f"Инлайн-поиск {name}")

        if not help_dict:
            return

        try:
            from utils.loader import modules_help as hydra_help
            hydra_help[module_name] = help_dict
        except Exception:
            pass
        # локальный запасной реестр
        self._local_help()[module_name] = help_dict

    @staticmethod
    def _local_help():
        from . import get_kernel
        k = get_kernel()
        if not hasattr(k, "_hydra_help_fallback"):
            k._hydra_help_fallback = {}
        return k._hydra_help_fallback

    # ========================================================
    # ВЫГРУЗКА
    # ========================================================

    async def unload_module(self, module_name, delete_file=False):
        k = self.kernel
        if module_name not in k.loaded_modules:
            return False, f"Модуль <code>{module_name}</code> не загружен"

        module = k.loaded_modules.get(module_name)
        instance = getattr(module, "_class_instance", None) if module else None

        if instance is not None:
            for meth_name in ("on_unload",):
                meth = getattr(instance, meth_name, None)
                if callable(meth):
                    try:
                        res = meth()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.error(f"on_unload error ({module_name}): {e}")
            for fn in getattr(instance, "_uninstall_funcs", []):
                try:
                    res = fn(instance)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    logger.error(f"on_uninstall error ({module_name}): {e}")

        k.unload_module_resources(module_name)
        k.loaded_modules.pop(module_name, None)
        k._class_module_instances.pop(module_name, None)
        self._local_help().pop(module_name, None)
        try:
            from utils.loader import modules_help as hydra_help
            hydra_help.pop(module_name, None)
        except Exception:
            pass

        if delete_file:
            for f in MODULES_DIR.glob(f"{module_name}*.py"):
                try:
                    f.unlink()
                except Exception:
                    pass
        return True, f"Модуль <code>{module_name}</code> выгружен"

    # ========================================================
    # УСТАНОВКА ИЗ КОДА / URL / АВТОЗАГРУЗКА
    # ========================================================

    async def install_module_code(self, code: str, name: str | None = None):
        """Сохранить код в modules/mcub_mods/ и загрузить."""
        if name:
            name = re.sub(r"[^\w\-.]", "_", name)
        name = self.extract_name(code, name or f"mod_{int(time.time())}")
        target = MODULES_DIR / f"{name}.py"
        target.write_text(code, encoding="utf-8")
        return await self.load_module_file(target, name)

    async def install_from_url(self, url: str):
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        return False, f"HTTP {r.status}"
                    code = await r.text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return False, f"Не удалось скачать: {e}"
        return await self.install_module_code(code)

    async def autoload_all(self):
        """Загрузить все модули из modules/mcub_mods/ (при старте Hydra)."""
        results = []
        for f in sorted(MODULES_DIR.glob("*.py")):
            if f.name.startswith("_"):
                continue
            ok, msg = await self.load_module_file(f)
            results.append((f.stem, ok, msg))
            logger.info(f"autoload {f.stem}: {'OK' if ok else msg}")
        return results

    def list_modules(self) -> list:
        """[(name, type, commands_count, meta)]"""
        k = self.kernel
        out = []
        for name, module in k.loaded_modules.items():
            inst = getattr(module, "_class_instance", None)
            mtype = "class" if inst is not None else "functional"
            cmds = [c for c, o in k.command_owners.items() if o == name]
            meta = {
                "version": getattr(inst, "version", "") if inst else "",
                "author": getattr(inst, "author", "") if inst else "",
            }
            out.append((name, mtype, len(cmds), meta))
        return out
