"""utils.custom_placeholders — поверхность MCUB-fork поверх Hydra-реестра.

В MCUB-fork это отдельный модуль реестра плейсхолдеров. В Hydra единый
реестр живёт в ``utils.misc`` (его же использует ядро: man, cfg и прочие),
поэтому здесь тонкий реэкспорт, чтобы модули MCUB видели привычные имена
и работали с теми же данными.
"""

from utils.misc import (
    config_placeholders,
    format_placeholders,
    list_placeholder_keys,
    placeholders,
    register_decorated_placeholders,
    register_media_placeholder,
    register_placeholder,
    resolve_media_placeholders,
    resolve_placeholders,
    unregister_placeholder,
    unregister_scope,
)


def get_placeholders(scope: str) -> list:
    """Список строк «{scope.key}: описание» как в MCUB-fork helpers."""

    keys = list_placeholder_keys(scope)
    return [f"{{{scope}.{key}}}" for key in keys]


__all__ = [
    "config_placeholders",
    "format_placeholders",
    "get_placeholders",
    "list_placeholder_keys",
    "placeholders",
    "register_decorated_placeholders",
    "register_media_placeholder",
    "register_placeholder",
    "resolve_media_placeholders",
    "resolve_placeholders",
    "unregister_placeholder",
    "unregister_scope",
]
