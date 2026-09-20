"""utils — поверхность MCUB-fork (utils/__init__.py) поверх Hydra-хелперов.

Сначала грузятся Hydra-хелперы (utils.misc), затем — автономные модули
MCUB-fork (helpers, arg_parser, platform, restart, strings и т.д.). Каждый
блок опционален: сломавшийся импорт одного не должен уронить весь пакет.
"""

from utils.misc import (
    register_placeholder,
    register_media_placeholder,
    register_decorated_placeholders,
    placeholders,
    unregister_placeholder,
    unregister_scope,
    list_placeholder_keys,
    format_placeholders,
    config_placeholders,
    resolve_placeholders,
    resolve_media_placeholders,
    edit_or_reply,
    answer,
    get_args_raw,
    rate_limit,
    get_start_time,
    set_start_time,
    get_uptime,
    format_size,
    clean_text,
    progress_callback,
    get_user_setting,
    set_user_setting,
    load_settings,
    save_settings,
)

__all__ = [
    "register_placeholder",
    "register_media_placeholder",
    "register_decorated_placeholders",
    "placeholders",
    "unregister_placeholder",
    "unregister_scope",
    "list_placeholder_keys",
    "format_placeholders",
    "config_placeholders",
    "resolve_placeholders",
    "resolve_media_placeholders",
    "edit_or_reply",
    "answer",
    "get_args_raw",
    "rate_limit",
    "get_start_time",
    "set_start_time",
    "get_uptime",
    "format_size",
    "clean_text",
    "progress_callback",
    "get_user_setting",
    "set_user_setting",
    "load_settings",
    "save_settings",
]

# --- платформа (utils.platform из MCUB-fork) ---
try:
    from . import platform as platform
    from .platform import (
        PlatformDetector,
        get_detailed_info,
        get_platform,
        get_platform_info,
        get_platform_name,
        is_desktop,
        is_docker,
        is_mobile,
        is_mobile_termux,
        is_termux,
        is_vds,
        is_virtualized,
        is_wsl,
    )

    __all__ += [
        "PlatformDetector",
        "get_detailed_info",
        "get_platform",
        "get_platform_info",
        "get_platform_name",
        "is_desktop",
        "is_docker",
        "is_mobile",
        "is_mobile_termux",
        "is_termux",
        "is_vds",
        "is_virtualized",
        "is_wsl",
        "platform",
    ]
except Exception:  # noqa: BLE001
    pass

# --- MCUB helpers (utils.helpers) ---
try:
    from .helpers import (
        answer_file,
        escape_html,
        escape_quotes,
        format_date,
        format_relative_time,
        format_time,
        get_admins,
        get_args,
        get_args_html,
        get_chat_id,
        get_lang,
        get_prefix,
        get_sender_info,
        get_thread_id,
        make_button,
        make_buttons,
        pipe_edit,
        relocate_entities,
        resolve_peer,
    )

    __all__ += [
        "answer_file",
        "escape_html",
        "escape_quotes",
        "format_date",
        "format_relative_time",
        "format_time",
        "get_admins",
        "get_args",
        "get_args_html",
        "get_chat_id",
        "get_lang",
        "get_prefix",
        "get_sender_info",
        "get_thread_id",
        "make_button",
        "make_buttons",
        "pipe_edit",
        "relocate_entities",
        "resolve_peer",
    ]
except Exception:  # noqa: BLE001
    pass

# --- парсер аргументов (utils.arg_parser) ---
try:
    from .arg_parser import (
        ArgumentParser,
        ArgumentValidator,
        extract_command,
        parse_arguments,
        parse_kwargs,
        split_args,
    )

    __all__ += [
        "ArgumentParser",
        "ArgumentValidator",
        "extract_command",
        "parse_arguments",
        "parse_kwargs",
        "split_args",
    ]
except Exception:  # noqa: BLE001
    pass

# --- HTML / message helpers ---
try:
    from . import html_parser as html_parser
    from .html_parser import parse_html, telegram_to_html

    __all__ += ["html_parser", "parse_html", "telegram_to_html"]
except Exception:  # noqa: BLE001
    pass

try:
    from .message_helpers import (
        edit_with_html,
        reply_with_html,
        send_file_with_html,
        send_with_html,
    )

    __all__ += [
        "edit_with_html",
        "reply_with_html",
        "send_file_with_html",
        "send_with_html",
    ]
except Exception:  # noqa: BLE001
    pass

# --- emoji parser ---
try:
    from . import emoji_parser as emoji_parser
    from .emoji_parser import EmojiParser, add_emoji, normalize

    __all__ += ["EmojiParser", "add_emoji", "emoji_parser", "normalize"]
except Exception:  # noqa: BLE001
    pass

# --- перезапуск (utils.restart) ---
try:
    from .restart import restart_kernel

    __all__ += ["restart_kernel"]
except Exception:  # noqa: BLE001
    pass

# --- i18n (utils.strings) ---
try:
    from .strings import Strings

    __all__ += ["Strings"]
except Exception:  # noqa: BLE001
    pass


def get_utils_status() -> dict:
    """Диагностика: какие подмодули utils поднялись (как в MCUB-fork)."""

    names = (
        "platform",
        "escape_html",
        "parse_arguments",
        "html_parser",
        "send_with_html",
        "emoji_parser",
        "restart_kernel",
        "Strings",
    )
    return {name: name in globals() for name in names}


__all__ += ["get_utils_status"]
