"""L1 — config: типизированные значения конфигурации модулей.

Эмуляторы совместимы по смыслу с MCUB module_config: ConfigValue, String,
Boolean, Choice, Integer, Float, Secret, ModuleConfig.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional


class ConfigValue:
    """База: значение + валидация при установке."""

    type_name = "any"

    def __init__(
        self,
        name: str,
        description: Any = "",
        default: Any = None,
        *,
        doc: Any = None,
        validator: Any = None,
        on_change: Any = None,
        **extra: Any,
    ):
        self.name = name
        # hikka зовёт ConfigValue(key, default, doc=..., validator=...) —
        # doc/doc-lambda принимаем как описание
        if doc is not None and not description:
            description = doc
        self.description = description
        self.default = default
        self.value = default
        self.validator_obj = validator
        self.on_change = on_change
        self.extra = extra

    def validate(self, value: Any) -> Any:
        return value

    def set(self, value: Any) -> None:
        self.value = self.validate(value)

    def __repr__(self) -> str:  # pragma: no cover
        shown = "***" if isinstance(self, Secret) else self.value
        return f"<{type(self).__name__} {self.name}={shown}>"


class String(ConfigValue):
    type_name = "str"

    def validate(self, value: Any) -> str:
        return str(value)


class Boolean(ConfigValue):
    type_name = "bool"

    def validate(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)


class Integer(ConfigValue):
    type_name = "int"

    def validate(self, value: Any) -> int:
        return int(value)


class Float(ConfigValue):
    type_name = "float"

    def validate(self, value: Any) -> float:
        return float(value)


class Choice(ConfigValue):
    type_name = "choice"

    def __init__(self, name: str, description: str, default: Any, possible: List[Any]):
        super().__init__(name, description, default)
        self.possible = list(possible)

    def validate(self, value: Any) -> Any:
        if value not in self.possible:
            raise ValueError(
                f"{self.name}: {value!r} не входит в {self.possible}"
            )
        return value


class Secret(ConfigValue):
    type_name = "secret"


class ModuleConfig:
    """Именованная коллекция ConfigValue с dict-подобным доступом."""

    def __init__(self, *values: ConfigValue):
        self._items: Dict[str, ConfigValue] = {v.name: v for v in values}

    def get(self, key: str, default: Any = None) -> Any:
        item = self._items.get(key)
        return item.value if item is not None else default

    def set(self, key: str, value: Any) -> None:
        item = self._items.get(key)
        if item is None:
            item = ConfigValue(key)
            self._items[key] = item
        item.set(value)

    def __getitem__(self, key: str) -> Any:
        return self._items[key].value

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def items(self):
        return {k: v.value for k, v in self._items.items()}.items()

    def to_dict(self) -> Dict[str, Any]:
        return {k: v.value for k, v in self._items.items()}

    def descriptors(self) -> Dict[str, ConfigValue]:
        return dict(self._items)
