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

_LOADER_INSTANCE = None
_LOADER_KERNEL = None


def set_loader_kernel(kernel):
    """Установить ядро для загрузчика"""
    global _LOADER_KERNEL
    _LOADER_KERNEL = kernel
    # Обновляем существующий инстанс
    if _LOADER_INSTANCE is not None:
        _LOADER_INSTANCE.kernel = kernel


def get_loader():
    """Получить экземпляр загрузчика"""
    global _LOADER_INSTANCE, _LOADER_KERNEL
    if _LOADER_INSTANCE is None:
        if _LOADER_KERNEL is None:
            from . import get_kernel
            _LOADER_KERNEL = get_kernel()
        _LOADER_INSTANCE = McubLoader(_LOADER_KERNEL)
    return _LOADER_INSTANCE


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

        if self._looks_like_hikka(code) and not is_reload:
            return await self.install_hikka_module(code, module_name)

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
                msg = str(e)
                if "relative import" in msg or "no known parent package" in msg:
                    return False, (
                        "<b>Модуль использует относительный импорт</b> "
                        "(<code>from . import ...</code>), а загружается как "
                        "отдельный файл — без родительского пакета это в принципе "
                        "не может сработать.\n"
                        "<i>Это не отсутствующая pip-зависимость, а структурная "
                        "проблема самого модуля.</i>"
                    )
                return False, (
                    f"<b>Нет зависимости:</b> <code>{e}</code>\n"
                    f"<i>Установи: pip install {str(e).split()[-1].strip(chr(39))}</i>"
                )
            except SyntaxError as e:
                return False, f"<b>Синтаксическая ошибка:</b> {e.msg} (строка {e.lineno})"

            # Получаем ядро
            k = self.kernel
            if k is None:
                from . import get_kernel
                k = get_kernel()
                self.kernel = k

            if k is None:
                return False, "Ядро MCUB не инициализировано"

            cls = self._find_module_base_class(module)

            # Устанавливаем загружаемый модуль
            if hasattr(k, 'set_loading_module'):
                k.set_loading_module(module_name, "user")
            else:
                k.current_loading_module = module_name

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
                    if not hasattr(k, '_class_module_instances'):
                        k._class_module_instances = {}
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

                if not hasattr(k, 'loaded_modules'):
                    k.loaded_modules = {}
                k.loaded_modules[module_name] = module
            finally:
                if hasattr(k, 'clear_loading_module'):
                    k.clear_loading_module()
                else:
                    k.current_loading_module = None

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

            if not hasattr(k, 'command_owners'):
                k.command_owners = {}
            cmds = [c for c, o in k.command_owners.items() if o == module_name]
            return True, (f"Модуль <code>{module_name}</code> загружен "
                          f"[{mod_type}], команд: {len(cmds)}")

        except Exception as e:
            logger.error(f"load {module_name} failed: {e}", exc_info=True)
            if self.kernel and hasattr(self.kernel, 'unload_module_resources'):
                self.kernel.unload_module_resources(module_name)
            return False, f"<b>Ошибка загрузки:</b> <code>{e}</code>"

    async def _post_load(self, module, module_name, is_install=False, is_reload=False):
        """Autostart циклов, on_load, on_install, @method-функции."""
        k = self.kernel
        if k is None:
            return
            
        instance = getattr(module, "_class_instance", None)

        # циклы
        if hasattr(k, '_module_loops'):
            for lp in k._module_loops.get(module_name, []):
                lp._kernel = k
                if lp.autostart:
                    try:
                        lp.start()
                    except Exception as e:
                        logger.error(f"loop autostart failed ({module_name}): {e}")

        # @method функции (вызываются с kernel)
        if hasattr(k, '_module_methods'):
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
                    if not hasattr(k, '_live_module_configs'):
                        k._live_module_configs = {}
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
        if k is None:
            return
            
        lang = "ru"
        try:
            if hasattr(k, 'config') and k.config:
                lang = k.config.get("language", "ru")
        except Exception:
            pass

        help_dict = {}
        if hasattr(k, 'command_owners') and hasattr(k, 'command_docs'):
            for cmd, owner in k.command_owners.items():
                if owner != module_name:
                    continue
                docs = k.command_docs.get(cmd, {})
                desc = docs.get(lang) or docs.get("ru") or docs.get("en") or f"Команда {cmd}"
                help_dict[cmd] = desc
        if hasattr(k, '_inline_handlers'):
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
        if k is None:
            return {}
        if not hasattr(k, "_hydra_help_fallback"):
            k._hydra_help_fallback = {}
        return k._hydra_help_fallback

    def get_module_commands(self, module_name: str, lang: str = "ru") -> tuple:
        """(commands, aliases_info, docs) конкретного модуля.
        commands — list[str] имён команд, aliases_info — dict[cmd -> list[alias]].
        Нужен man.py и любому другому модулю, который строит список команд
        по владельцу через command_owners/aliases."""
        k = self.kernel
        commands: list = []
        aliases_info: dict = {}
        docs: dict = {}
        if k is None:
            return commands, aliases_info, docs

        if hasattr(k, "command_owners"):
            commands = [c for c, o in k.command_owners.items() if o == module_name]

        if hasattr(k, "aliases"):
            # k.aliases хранится как alias -> cmd, разворачиваем в cmd -> [alias, ...]
            for alias, cmd in k.aliases.items():
                if cmd in commands:
                    aliases_info.setdefault(cmd, []).append(alias)

        if hasattr(k, "command_docs"):
            for cmd in commands:
                cmd_docs = k.command_docs.get(cmd, {})
                docs[cmd] = cmd_docs.get(lang) or cmd_docs.get("ru") or cmd_docs.get("en") or ""

        return commands, aliases_info, docs

    @staticmethod
    def pick_localized_text(value, lang: str = "ru", fallback: str = "") -> str:
        """Достаёт строку для нужного языка из dict {"ru": ..., "en": ...}
        либо возвращает value как есть, если это уже строка."""
        if isinstance(value, dict):
            return value.get(lang) or value.get("ru") or value.get("en") or fallback
        if isinstance(value, str) and value.strip():
            return value
        return fallback

    # ========================================================
    # ВЫГРУЗКА
    # ========================================================

    async def unload_module(self, module_name, delete_file=False):
        k = self.kernel
        if k is None:
            return False, "Ядро MCUB не инициализировано"
            
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

        if hasattr(k, 'unload_module_resources'):
            k.unload_module_resources(module_name)
        k.loaded_modules.pop(module_name, None)
        if hasattr(k, '_class_module_instances'):
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

    @staticmethod
    def _looks_like_hikka(code: str) -> bool:
        """Эвристика: это модуль под Hikka/Heroku, а не под MCUB."""
        markers = (
            "from .. import loader",
            "from ..loader import",
            "import loader, utils",
            "loader.Module",
            "@loader.command",
            "herokutl",
            "scope: hikka_only",
            "scope: hikka_min",
        )
        return any(m in code for m in markers) and "ModuleBase" not in code and "def register(kernel" not in code

    async def install_module_code(self, code: str, name: str | None = None):
        """Сохранить код в modules/mcub_mods/ и загрузить."""
        if self._looks_like_hikka(code):
            return await self.install_hikka_module(code, name)
        if name:
            name = re.sub(r"[^\w\-.]", "_", name)
        name = self.extract_name(code, name or f"mod_{int(time.time())}")
        target = MODULES_DIR / f"{name}.py"
        target.write_text(code, encoding="utf-8")
        return await self.load_module_file(target, name)

    async def install_hikka_module(self, code: str, module_name: str | None = None):
        """Установить Hikka/Heroku-модуль через прослойку hikka_compat
        (экспериментально — как и в оригинальном MCUB-fork, работают не все
        модули, только те, что используют распространённое подмножество API)."""
        import importlib
        import inspect as _inspect

        name = module_name or self.extract_name(code, f"hikka_{int(time.time())}")
        name = re.sub(r"[^\w\-.]", "_", name).lower()

        pkg_root = Path("hikka_compat")
        target = pkg_root / "modules" / f"{name}.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")

        mod_full_name = f"hikka_compat.modules.{name}"
        sys.modules.pop(mod_full_name, None)

        try:
            module = importlib.import_module(mod_full_name)
            importlib.reload(module)
        except ImportError as e:
            return False, (
                f"<b>Hikka-модуль не смог импортироваться:</b> <code>{e}</code>\n"
                f"<i>Модули на чужом API (Hikka/Heroku) поддерживаются частично — "
                f"как и в оригинальном MCUB-fork.</i>"
            )
        except SyntaxError as e:
            return False, f"<b>Синтаксическая ошибка:</b> {e.msg} (строка {e.lineno})"
        except Exception as e:
            logger.error(f"install_hikka_module({name}) import failed: {e}", exc_info=True)
            return False, f"<b>Ошибка импорта Hikka-модуля:</b> {e}"

        from hikka_compat.loader import Module as HikkaModuleBase, Strings, derive_command_name

        hikka_cls = None
        for _, obj in _inspect.getmembers(module, _inspect.isclass):
            if issubclass(obj, HikkaModuleBase) and obj is not HikkaModuleBase:
                hikka_cls = obj
                break
        if hikka_cls is None:
            return False, "В файле не найден класс-наследник loader.Module — это не Hikka-модуль"

        try:
            inst = hikka_cls()
        except Exception as e:
            logger.error(f"hikka module {name} __init__ failed: {e}", exc_info=True)
            return False, f"<b>Ошибка инициализации модуля:</b> {e}"

        k = self.kernel
        if k is None:
            from . import get_kernel
            k = get_kernel()
            self.kernel = k
        if k is None:
            return False, "Ядро MCUB не инициализировано"

        real_client = getattr(k, "_real_client", None) or getattr(k, "client", None)
        inst._client = real_client
        inst.client = real_client

        base_strings = dict(getattr(hikka_cls, "strings", {}) or {})
        ru_strings = dict(getattr(hikka_cls, "strings_ru", {}) or {})
        merged = {**base_strings, **ru_strings}
        inst.strings = Strings(merged)

        client_ready = getattr(inst, "client_ready", None)
        if client_ready and _inspect.iscoroutinefunction(client_ready):
            try:
                await client_ready(real_client, k)
            except TypeError:
                try:
                    await client_ready()
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"hikka {name}.client_ready() failed: {e}")

        if not hasattr(k, "command_handlers"):
            k.command_handlers = {}
        if not hasattr(k, "command_owners"):
            k.command_owners = {}
        if not hasattr(k, "command_docs"):
            k.command_docs = {}

        registered = 0
        for meth_name, meth in _inspect.getmembers(inst, _inspect.ismethod):
            if not getattr(meth, "_hikka_command", False):
                continue
            cmd = derive_command_name(meth_name, getattr(meth, "_hikka_command_name", None))
            existing_owner = k.command_owners.get(cmd)
            if existing_owner and existing_owner != name:
                logger.warning(f"hikka {name}: команда '{cmd}' уже занята модулем {existing_owner}, пропускаю")
                continue
            k.command_handlers[cmd] = meth
            k.command_owners[cmd] = name
            ru_doc = getattr(meth, "_hikka_ru_doc", None)
            en_doc = getattr(meth, "_hikka_en_doc", None)
            k.command_docs[cmd] = {"ru": ru_doc or en_doc or "", "en": en_doc or ru_doc or ""}
            registered += 1

        if registered == 0:
            return False, (
                "В модуле не нашлось ни одной команды с <code>@loader.command</code> — "
                "устанавливать нечего"
            )

        module._class_instance = inst
        if not hasattr(k, "loaded_modules"):
            k.loaded_modules = {}
        k.loaded_modules[name] = module

        return True, (
            f"Hikka-модуль <code>{name}</code> установлен "
            f"[совместимость экспериментальная], команд: {registered}"
        )

    async def install_from_archive(self, data: bytes, module_name: str | None = None):
        """Установить модуль из ZIP-архива как настоящий пакет — в отличие
        от одиночного .py, здесь относительные импорты (`from . import x`)
        внутри модуля реально работают, т.к. пакет грузится с правильным
        __package__/submodule_search_locations."""
        import zipfile
        import io
        import shutil

        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except Exception as e:
            return False, f"<b>Битый архив:</b> <code>{e}</code>"

        names = [n for n in zf.namelist() if not n.endswith("/")]
        if not names:
            return False, "Архив пуст"

        # Определяем корень пакета: либо всё лежит в одной общей папке
        # внутри архива, либо файлы прямо в корне архива.
        top_level = {n.split("/")[0] for n in names if "/" in n}
        if len(top_level) == 1:
            root_prefix = next(iter(top_level)) + "/"
        else:
            root_prefix = ""

        pkg_name = module_name or (root_prefix.rstrip("/") if root_prefix else f"mod_{int(time.time())}")
        pkg_name = re.sub(r"[^\w\-.]", "_", pkg_name)

        pkg_dir = MODULES_DIR / pkg_name
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir, ignore_errors=True)
        pkg_dir.mkdir(parents=True, exist_ok=True)

        for n in names:
            rel = n[len(root_prefix):] if root_prefix and n.startswith(root_prefix) else n
            if not rel:
                continue
            dest = pkg_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_bytes(zf.read(n))
            except Exception as e:
                return False, f"<b>Не удалось распаковать</b> <code>{rel}</code>: {e}"

        if not (pkg_dir / "__init__.py").exists():
            entry = None
            for candidate in (f"{pkg_name}.py", "__main__.py", "main.py"):
                if (pkg_dir / candidate).exists():
                    entry = candidate
                    break
            if entry:
                (pkg_dir / "__init__.py").write_text(
                    (pkg_dir / entry).read_text(encoding="utf-8", errors="ignore"),
                    encoding="utf-8",
                )
            else:
                (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

        return await self._load_package(pkg_dir, pkg_name)

    async def _load_package(self, pkg_dir: Path, pkg_name: str):
        """Загрузить каталог как настоящий Python-пакет (submodule_search_locations
        выставлены правильно — относительные импорты внутри пакета работают)."""
        from .proxies import (
            get_module_client, get_module_kernel, get_module_register,
        )

        sys_name = f"mcub_pkg_{pkg_name}_{int(time.time() * 1000) % 10**7}"
        init_file = pkg_dir / "__init__.py"

        try:
            spec = importlib.util.spec_from_file_location(
                sys_name, str(init_file),
                submodule_search_locations=[str(pkg_dir)],
            )
            if spec is None:
                return False, "Не удалось создать spec для пакета"
            module = importlib.util.module_from_spec(spec)
            sys.modules[sys_name] = module
            try:
                spec.loader.exec_module(module)
            except ImportError as e:
                msg = str(e)
                if "relative import" in msg or "no known parent package" in msg:
                    return False, (
                        "<b>Даже пакетом не завелось:</b> относительный импорт "
                        f"внутри модуля ссылается на несуществующий файл.\n<code>{e}</code>"
                    )
                return False, (
                    f"<b>Нет зависимости:</b> <code>{e}</code>\n"
                    f"<i>Установи: pip install {str(e).split()[-1].strip(chr(39))}</i>"
                )
            except SyntaxError as e:
                return False, f"<b>Синтаксическая ошибка:</b> {e.msg} (строка {e.lineno})"

            k = self.kernel
            if k is None:
                from . import get_kernel
                k = get_kernel()
                self.kernel = k
            if k is None:
                return False, "Ядро MCUB не инициализировано"

            cls = self._find_module_base_class(module)
            if hasattr(k, "set_loading_module"):
                k.set_loading_module(pkg_name, "user")
            else:
                k.current_loading_module = pkg_name

            mod_type = "class"
            try:
                if cls is not None:
                    display_name = getattr(cls, "name", None)
                    if display_name and display_name != "Unnamed":
                        pkg_name = display_name
                    inst = cls(
                        get_module_kernel(k, pkg_name),
                        get_module_client(k, pkg_name),
                        get_module_register(k, pkg_name),
                    )
                    if not hasattr(k, "_class_module_instances"):
                        k._class_module_instances = {}
                    k._class_module_instances[pkg_name] = inst
                    module._class_instance = inst
                elif hasattr(module, "register") and callable(module.register):
                    mod_type = "functional"
                    sig = None
                    try:
                        sig = inspect.signature(module.register)
                    except (TypeError, ValueError):
                        pass
                    param = list(sig.parameters)[0] if sig and sig.parameters else "kernel"
                    arg = get_module_kernel(k, pkg_name) if param == "kernel" else k._real_client
                    if inspect.iscoroutinefunction(module.register):
                        await module.register(arg)
                    else:
                        module.register(arg)
                else:
                    return False, f"В <code>{pkg_name}</code> не найден класс модуля или register()"

                if not hasattr(k, "loaded_modules"):
                    k.loaded_modules = {}
                k.loaded_modules[pkg_name] = module
            finally:
                if hasattr(k, "clear_loading_module"):
                    k.clear_loading_module()
                else:
                    k.current_loading_module = None

            await self._post_load(module, pkg_name, is_install=True, is_reload=False)
            self._sync_help(pkg_name)

            if not hasattr(k, "command_owners"):
                k.command_owners = {}
            cmds = [c for c, o in k.command_owners.items() if o == pkg_name]
            return True, (f"Пакет <code>{pkg_name}</code> установлен "
                          f"[{mod_type}], команд: {len(cmds)}")
        except Exception as e:
            logger.error(f"_load_package({pkg_name}) failed: {e}", exc_info=True)
            if self.kernel and hasattr(self.kernel, "unload_module_resources"):
                self.kernel.unload_module_resources(pkg_name)
            return False, f"<b>Ошибка загрузки пакета:</b> {e}"

    async def install_from_url(self, url: str, module_name: str | None = None, auto_dependencies: bool = True):
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        return False, f"HTTP {r.status}"
                    raw = await r.read()
        except Exception as e:
            return False, f"Не удалось скачать: {e}"

        # ZIP-архив (magic bytes "PK\x03\x04") -> ставим как пакет,
        # иначе — как одиночный .py файл, как и раньше.
        if raw[:4] == b"PK\x03\x04":
            return await self.install_from_archive(raw, module_name)

        code = raw.decode("utf-8", errors="ignore")
        # auto_dependencies пока не реализован (нет системы разрешения
        # зависимостей) — принимаем параметр, чтобы не падать на реальной
        # сигнатуре MCUB-fork, но пока не используем его.
        return await self.install_module_code(code, name=module_name)

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
        if k is None:
            return []
        out = []
        for name, module in k.loaded_modules.items():
            inst = getattr(module, "_class_instance", None)
            mtype = "class" if inst is not None else "functional"
            if not hasattr(k, 'command_owners'):
                k.command_owners = {}
            cmds = [c for c, o in k.command_owners.items() if o == name]
            meta = {
                "version": getattr(inst, "version", "") if inst else "",
                "author": getattr(inst, "author", "") if inst else "",
            }
            out.append((name, mtype, len(cmds), meta))
        return out

