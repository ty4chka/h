"""
Шим Hikka-style loader API (подмножество, покрывающее самые
распространённые модули): Module, command, tds, ModuleConfig,
ConfigValue, validators.
"""

import re


class Strings:
    """self.strings("key") — вызываемый доступ к локализованным строкам,
    как в настоящей Hikka."""

    def __init__(self, base: dict, lang: str = "ru"):
        self._base = dict(base or {})

    def __call__(self, key, *args, **kwargs):
        return self._base.get(key, key)

    def __getitem__(self, key):
        return self._base.get(key, key)


class ConfigValue:
    def __init__(self, key, default=None, doc="", validator=None, **kwargs):
        self.key = key
        self.default = default
        self.doc = doc
        self.validator = validator
        self.value = default


class ModuleConfig(dict):
    """Ведёт себя как dict (self.config["key"]), но строится из ConfigValue."""

    def __init__(self, *config_values):
        super().__init__()
        self._defs = {}
        for cv in config_values:
            if isinstance(cv, ConfigValue):
                self._defs[cv.key] = cv
                self[cv.key] = cv.default
            else:
                # на случай ModuleConfig("key", default, "doc") тройками
                pass

    def __getitem__(self, key):
        return dict.get(self, key, None)


class validators:
    class Integer:
        def __init__(self, minimum=None, maximum=None, **kwargs):
            self.minimum = minimum
            self.maximum = maximum

    class String:
        def __init__(self, length=None, **kwargs):
            self.length = length

    class Boolean:
        def __init__(self, **kwargs):
            pass

    class Series:
        def __init__(self, **kwargs):
            pass


class Module:
    """Базовый класс Hikka-модуля. Поддерживает подмножество реального API:
    self._client, self.strings("key"), self.config["key"], self.db.
    Реальная привязка к MCUB-ядру (кернел/бридж) происходит снаружи,
    в mcub_engine/loader.py при установке."""

    strings = {"name": "hikka_module"}

    def __init__(self):
        pass

    async def client_ready(self, *args, **kwargs):
        """Опциональный хук — если модуль его переопределяет, движок
        вызовет его после привязки клиента."""
        pass


def command(*, ru_doc=None, en_doc=None, command=None, **kwargs):
    """Декоратор @loader.command(...) — помечает метод как команду.
    Имя команды: явный аргумент command=, либо имя метода без суффикса
    'cmd' (конвенция Hikka: shakalcmd -> .shakal)."""

    def deco(func):
        func._hikka_command = True
        func._hikka_command_name = command
        func._hikka_ru_doc = ru_doc
        func._hikka_en_doc = en_doc
        return func

    return deco


def tds(cls):
    """@loader.tds — в реальной Hikka занимается автопереводом докстрок.
    Для нас достаточно no-op: просто возвращаем класс как есть."""
    return cls


def derive_command_name(method_name: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.lower()
    name = method_name
    if name.endswith("cmd"):
        name = name[:-3]
    return name.lower()
