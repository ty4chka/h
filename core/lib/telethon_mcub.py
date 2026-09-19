# core/lib/telethon_mcub.py
"""
Telethon-MCUB Bridge - Ob'yedinennyy klient dlya Hydra UserBot
Nasleduyet obychnyy Telethon + dobavlyayet MCUB-spetsificheskiye fichi.
Import ostayetsya `from telethon import TelegramClient` - polnaya sovmestimost'.
"""

import asyncio
import json
import logging
import re
import sys
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from telethon import TelegramClient, events
from telethon.tl.types import (
    InputBotInlineResult,
    InputBotInlineMessageText,
)
from telethon.tl.functions.messages import SetInlineBotResultsRequest

logger = logging.getLogger(__name__)

# ============================================
# SESSION COMPATIBILITY PATCH
# Fixes sessions created by different Telethon versions
# ============================================

def _patch_sqlite_session():
    """Patch SQLiteSession to handle sessions with extra columns."""
    from telethon.sessions import sqlite
    original_init = sqlite.SQLiteSession.__init__

    def patched_init(self, session_id):
        try:
            original_init(self, session_id)
        except ValueError as e:
            if "too many values to unpack" in str(e):
                import sqlite3
                import os
                session_path = str(session_id)
                if not session_path.endswith('.session'):
                    session_path += '.session'
                if os.path.exists(session_path):
                    conn = sqlite3.connect(session_path)
                    cursor = conn.cursor()
                    cursor.execute('PRAGMA table_info(sessions)')
                    columns = cursor.fetchall()
                    if len(columns) == 6:
                        cursor.execute('''
                            CREATE TABLE sessions_new (
                                dc_id INTEGER PRIMARY KEY,
                                server_address TEXT,
                                port INTEGER,
                                auth_key BLOB,
                                takeout_id INTEGER
                            )
                        ''')
                        cursor.execute('SELECT dc_id, server_address, port, auth_key, takeout_id FROM sessions')
                        for row in cursor.fetchall():
                            cursor.execute(
                                'INSERT INTO sessions_new VALUES (?, ?, ?, ?, ?)',
                                row[:5]
                            )
                        cursor.execute('DROP TABLE sessions')
                        cursor.execute('ALTER TABLE sessions_new RENAME TO sessions')
                        conn.commit()
                        conn.close()
                        original_init(self, session_id)
                    else:
                        raise
                else:
                    raise
            else:
                raise

    sqlite.SQLiteSession.__init__ = patched_init
    logger.info("SQLiteSession patched for compatibility")

_patch_sqlite_session()

# ============================================
# MCUB EVENT OBJECTS
# ============================================

class InlineQueryEvent:
    """Emulyatsiya MCUB InlineQueryEvent s builder i answer()."""
    def __init__(self, telethon_event, query_name: str = ''):
        self._event = telethon_event
        self._query_name = query_name
        self.text = getattr(telethon_event, 'text', '')
        self.query = self.text
        self.from_user = getattr(telethon_event, 'sender', None)
        self.sender_id = getattr(telethon_event, 'sender_id', 0)
        self.chat_instance = getattr(telethon_event, 'chat_instance', '')
        parts = self.text.split(maxsplit=1)
        if query_name and len(parts) > 1:
            self.text = f"{query_name} {parts[1]}"
        self.builder = InlineResultBuilder(self)
        self.client = getattr(telethon_event, 'client', None)

    async def answer(self, results: list, **kwargs):
        if not results:
            return
        if hasattr(self._event, 'answer'):
            try:
                return await self._event.answer(results, **kwargs)
            except Exception as e:
                logger.warning(f"Native inline answer failed: {e}")
        out = "<b>Results (inline):</b>\n\n"
        for art in results[:5]:
            title = getattr(art, 'title', '')
            desc = getattr(art, 'description', '')
            text = getattr(art, 'text', '')
            out += f"<b>{title}</b>\n"
            if desc:
                out += f"<i>{desc}</i>\n"
            out += f"{text.replace(chr(8288), chr(32))}\n\n"
        if self.client:
            await self.client.send_message(self.sender_id, out, parse_mode='html')

class InlineResultBuilder:
    """Builder dlya inline rezultatov kak v MCUB."""
    def article(self, title: str, description: str = '', text: str = '', parse_mode: str = 'html', **kwargs):
        return InlineArticleResult(title, description, text, parse_mode)
    def photo(self, url: str, title: str = '', description: str = '', **kwargs):
        return InlinePhotoResult(url, title, description)

class InlineArticleResult:
    def __init__(self, title: str, description: str = '', text: str = '', parse_mode: str = 'html'):
        self.title = title
        self.description = description
        self.text = text
        self.parse_mode = parse_mode
        self.id = f"article_{hash(title) & 0x7FFFFFFF}"
    def to_telethon(self):
        return InputBotInlineResult(
            id=self.id,
            type='article',
            title=self.title,
            description=self.description,
            send_message=InputBotInlineMessageText(
                message=self.text,
                parse_mode=self.parse_mode
            )
        )

class InlinePhotoResult:
    def __init__(self, url: str, title: str = '', description: str = ''):
        self.url = url
        self.title = title
        self.description = description
        self.id = f"photo_{hash(url) & 0x7FFFFFFF}"

class CallbackQueryEvent:
    """Emulyatsiya MCUB CallbackQueryEvent."""
    def __init__(self, telethon_event):
        self._event = telethon_event
        self.data = getattr(telethon_event, 'data', b'')
        self.query = self.data.decode() if isinstance(self.data, bytes) else str(self.data)
        self.from_user = getattr(telethon_event, 'sender', None)
        self.sender_id = getattr(telethon_event, 'sender_id', 0)
        self.message_id = getattr(telethon_event, 'message_id', 0)
        self.chat_instance = getattr(telethon_event, 'chat_instance', '')
        self.client = getattr(telethon_event, 'client', None)
    async def answer(self, text: str = None, alert: bool = False, **kwargs):
        if hasattr(self._event, 'answer'):
            try:
                return await self._event.answer(text, alert=alert, **kwargs)
            except Exception as e:
                logger.warning(f"Native callback answer failed: {e}")
        if text and self.client:
            await self.client.send_message(self.sender_id, text)
    async def edit(self, text: str, **kwargs):
        if hasattr(self._event, 'edit'):
            try:
                return await self._event.edit(text, **kwargs)
            except Exception as e:
                if 'not modified' not in str(e).lower():
                    raise

class ConversationMock:
    """Emulyatsiya MCUB conversation."""
    def __init__(self, client, chat_id):
        self._client = client
        self._chat_id = chat_id
        self._messages = []
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def send_message(self, text: str, **kwargs):
        msg = await self._client.send_message(self._chat_id, text, **kwargs)
        self._messages.append(msg)
        return msg
    async def get_response(self, timeout: int = 60, **kwargs):
        if not self._client:
            class _Resp:
                text = ''
            return _Resp()
        future = asyncio.Future()
        @self._client.on(events.NewMessage(chats=self._chat_id, incoming=True))
        async def handler(event):
            if not future.done():
                future.set_result(event)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            class _Resp:
                text = ''
            return _Resp()
        finally:
            self._client.remove_event_handler(handler)

# ============================================
# MCUB KERNEL INTERFACE
# ============================================

class MCUBKernelInterface:
    """Interfeys yadra MCUB - proksi v Hydra API."""
    def __init__(self, client: TelegramClient, parent_module=None):
        self.client = client
        self.parent_module = parent_module
        self.custom_prefix = '.'
        self.config = {'language': 'ru', 'inline_bot_username': 'bot'}
        self.logger = logging.getLogger('mcub_kernel')
        self._inline_handlers: Dict[str, Callable] = {}
        self._callback_handlers: Dict[str, Callable] = {}
        self._inline_bot_username = None
        self._live_module_configs: Dict[str, Any] = {}

    def register_inline_handler(self, name: str, func: Callable):
        self._inline_handlers[name] = func
        logger.debug(f"Registered inline handler: {name}")

    def register_callback_handler(self, prefix: str, func: Callable):
        self._callback_handlers[prefix] = func
        logger.debug(f"Registered callback handler: {prefix}")

    async def inline_query_and_click(self, chat_id, query: str, *args, **kwargs):
        parts = query.split(maxsplit=1)
        name = parts[0] if parts else ''
        if name in self._inline_handlers:
            mock_event = InlineQueryEvent(
                type('Mock', (), {
                    'text': query,
                    'sender_id': chat_id,
                    'client': self.client,
                })(),
                query_name=name
            )
            await self._inline_handlers[name](mock_event)
            return True, None
        return False, f"Inline handler '{name}' not found"

    async def inline_form(self, chat_id, text: str, buttons=None, **kwargs):
        try:
            await self.client.send_message(chat_id, text, parse_mode='html', **kwargs)
            return True, None
        except Exception as e:
            return False, str(e)

    async def conversation(self, chat_id, *args, **kwargs):
        return ConversationMock(self.client, chat_id)

    async def get_module_config(self, name: str, default=None):
        p = Path("data/module_configs.json")
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f).get(name, default or {})
            except Exception as e:
                logger.warning(f"Config read error: {e}")
        return default or {}

    def store_module_config_schema(self, name: str, config: dict):
        try:
            from modules.cfg import register_module_schema
            register_module_schema(name, config)
        except ImportError:
            logger.warning("cfg.py not available for schema registration")

    async def save_module_config(self, name: str, cfg_dict: dict):
        p = Path("data/module_configs.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        all_cfg = {}
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    all_cfg = json.load(f)
            except Exception:
                pass
        all_cfg[name] = cfg_dict
        with open(p, "w", encoding="utf-8") as f:
            json.dump(all_cfg, f, ensure_ascii=False, indent=2)

    async def db_get(self, module: str, key: str):
        p = Path(f"data/db/{module}.json")
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f).get(key)
            except Exception:
                pass
        return None

    async def db_set(self, module: str, key: str, value):
        p = Path(f"data/db/{module}.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data[key] = value
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def is_bot_available(self):
        return self._inline_bot_username is not None

    def is_admin(self, user_id: int):
        try:
            from config import OWNER_ID
            return user_id == OWNER_ID
        except ImportError:
            return True

    def cprint(self, *args, **kwargs):
        print(*args, **kwargs)

    def log_error(self, *args, **kwargs):
        self.logger.error(*args, **kwargs)

    def log_warning(self, *args, **kwargs):
        self.logger.warning(*args, **kwargs)

    def log_debug(self, *args, **kwargs):
        self.logger.debug(*args, **kwargs)

    async def install_from_url(self, url: str):
        return False, "Ispolzuyte .lm dlya ustanovki moduley"


    # ═══════════════════════════════════════════════════════════════
    # OPENAGENT / MODULE BASE COMPATIBILITY
    # ═══════════════════════════════════════════════════════════════

    class Button:
        """MCUB-style Button factory для инлайн-кнопок."""
        @staticmethod
        def inline(text, callback, args=(), style=None, **kwargs):
            from telethon import Button as TButton
            import json, base64
            payload = {"cb": getattr(callback, '__name__', str(callback)), "args": list(args)}
            data = base64.b64encode(json.dumps(payload).encode()).decode()[:64]
            return TButton.inline(text, data=data)

        @staticmethod
        def input(text, callback, placeholder="", allow_user=None, data=""):
            from telethon import Button as TButton
            # Input button - запрашивает текст от пользователя
            # Input button fallback: используем inline button
            return TButton.inline(text, data=b"input_" + str(data or "").encode()[:60])

        @staticmethod
        def url(text, url):
            from telethon import Button as TButton
            return TButton.url(text, url)

    async def save_module_config(self, name: str, cfg_dict: dict):
        """Сохранить конфиг модуля в JSON."""
        p = Path("data/module_configs.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        all_cfg = {}
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    all_cfg = json.load(f)
            except Exception:
                pass
        all_cfg[name] = dict(cfg_dict)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(all_cfg, f, ensure_ascii=False, indent=2)

    def store_module_config_schema(self, name: str, config):
        """Сохранить схему конфига (для совместимости с ModuleBase)."""
        self._live_module_configs[name] = {"_schema": True}

    def is_admin(self, user_id: int):
        try:
            from config import OWNER_ID
            return user_id == OWNER_ID
        except ImportError:
            return True

    async def handle_error(self, exc: Exception, *args, **kwargs):
        source = kwargs.get("source", "")
        event = kwargs.get("event")
        self.logger.error(f"{source}: {exc}" if source else f"Module error: {exc}", exc_info=exc)
        if event and hasattr(event, 'reply'):
            try:
                await event.reply(f"<b>Error:</b> <code>{str(exc)[:200]}</code>", parse_mode='html')
            except Exception:
                pass

# ============================================
# UNIFIED TELEGRAM CLIENT
# ============================================

class UnifiedTelegramClient(TelegramClient):
    """
    Ob'yedinennyy klient: obychnyy Telethon + MCUB-fichi.
    Usage:
        from core.lib.telethon_mcub import UnifiedTelegramClient
        client = UnifiedTelegramClient('session', api_id, api_hash)
        kernel = client.mcub_kernel
        kernel.register_inline_handler('search', my_handler)
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mcub_kernel = None
        self._mcub_modules = {}

    @property
    def mcub_kernel(self):
        if self._mcub_kernel is None:
            self._mcub_kernel = MCUBKernelInterface(self)
        return self._mcub_kernel

    def register_mcub_module(self, name, module_instance):
        self._mcub_modules[name] = module_instance
        if hasattr(module_instance, 'client'):
            module_instance.client = self
        if hasattr(module_instance, 'kernel') and hasattr(module_instance.kernel, 'client'):
            module_instance.kernel.client = self
        logger.info(f"MCUB module registered: {name}")

    def unregister_mcub_module(self, name):
        if name in self._mcub_modules:
            del self._mcub_modules[name]
            logger.info(f"MCUB module unregistered: {name}")

    def mcub_command(self, name, *args, **kwargs):
        pattern = rf"(?i)^\.{re.escape(name)}(?:\s|$)"
        def decorator(func):
            @self.on(events.NewMessage(pattern=pattern, outgoing=True))
            async def handler(event):
                _safe_edit_patch(event)
                await func(event)
            func._handler = handler
            func._is_mcub_cmd = True
            func._cmd_name = name
            return func
        return decorator

    def mcub_watcher(self, *args, **kwargs):
        def decorator(func):
            @self.on(events.NewMessage(incoming=True))
            async def handler(event):
                _safe_edit_patch(event)
                await func(event)
            func._handler = handler
            func._is_mcub_watcher = True
            return func
        return decorator

    def mcub_inline(self, name, *args, **kwargs):
        def decorator(func):
            self.mcub_kernel.register_inline_handler(name, func)
            func._is_mcub_inline = True
            func._cmd_name = name
            return func
        return decorator

    def mcub_callback(self, prefix, *args, **kwargs):
        def decorator(func):
            self.mcub_kernel.register_callback_handler(prefix, func)
            func._is_mcub_callback = True
            return func
        return decorator

def _safe_edit_patch(event):
    """Patch event.edit dlya bezopasnogo redaktirovaniya."""
    orig_edit = getattr(event, 'edit', None)
    if not orig_edit:
        return
    async def safe_edit(*args, **kwargs):
        try:
            return await orig_edit(*args, **kwargs)
        except Exception as e:
            if 'not modified' not in str(e).lower():
                raise e
    event.edit = safe_edit

# ============================================
# MODULE AUTO-REGISTRATION
# ============================================

def auto_register_mcub_module(client, module_class, module_name=None):
    """Avtomaticheskaya registratsiya MCUB-modulya v UnifiedTelegramClient."""
    if module_name is None:
        module_name = getattr(module_class, 'name', module_class.__name__.lower())
    instance = module_class()
    instance.client = client
    instance.kernel = client.mcub_kernel

    # ═══════════════════════════════════════════════════════════
    # MODULE BASE COMPATIBILITY MIXIN
    # ═══════════════════════════════════════════════════════════
    instance.Button = client.mcub_kernel.Button

    async def _oa_edit(event, text, as_html=False, **kwargs):
        try:
            if hasattr(event, 'edit'):
                return await event.edit(text, parse_mode='html' if as_html else None, **kwargs)
        except Exception as e:
            if 'not modified' not in str(e).lower():
                logging.getLogger('mcub_compat').warning(f"edit error: {e}")
        try:
            if hasattr(event, 'reply'):
                return await event.reply(text, parse_mode='html' if as_html else None)
        except:
            pass
        try:
            chat_id = getattr(event, 'chat_id', None)
            if chat_id and client:
                return await client.send_message(chat_id, text, parse_mode='html' if as_html else None)
        except:
            pass
    instance.edit = _oa_edit

    async def _oa_reply(event, text, as_html=False, **kwargs):
        try:
            if hasattr(event, 'reply'):
                return await event.reply(text, parse_mode='html' if as_html else None, **kwargs)
        except:
            pass
        return await _oa_edit(event, text, as_html=as_html, **kwargs)
    instance.reply = _oa_reply

    async def _oa_inline(chat_id, text, buttons=None, ttl=900, parse_mode='html'):
        try:
            flat_buttons = []
            if buttons:
                from telethon import Button as TButton
                for row in buttons:
                    flat_row = []
                    for btn in row:
                        if hasattr(btn, 'button'):
                            flat_row.append(btn.button)
                        elif hasattr(btn, 'data'):
                            flat_row.append(TButton.inline(getattr(btn, 'text', '?'), data=btn.data))
                        else:
                            flat_row.append(btn)
                    flat_buttons.append(flat_row)
            msg = await client.send_message(chat_id, text, buttons=flat_buttons, parse_mode=parse_mode)
            return None, msg
        except Exception as e:
            logging.getLogger('mcub_compat').warning(f"inline error: {e}")
            try:
                msg = await client.send_message(chat_id, text, parse_mode=parse_mode)
                return None, msg
            except:
                pass
        return None, None
    instance.inline = _oa_inline

    def _oa_strings(key, **kwargs):
        _strings = {
            'need_text': 'Usage: .oa <request>',
            'thinking': 'Thinking...',
            'no_key': 'API key not configured',
            'error': 'Error: {error}',
            'new_session_name': 'New chat',
            'chat_empty': 'No messages',
            'chat_today': 'today',
            'chat_yesterday': 'yesterday',
            'chat_days_ago': '{days} days ago',
            'new_chat_button': '+ New chat',
            'rename_chat_button': 'Rename',
            'delete_chat_button': 'Delete',
            'remember_chat_button': 'Remember',
            'chat_choice_saved': 'Choice saved',
            'chat_switched': 'Active: {name}',
            'chat_created': 'Created: {name}',
            'chat_renamed': 'Renamed: {name}',
            'chat_deleted': 'Deleted',
            'chat_delete_last': 'Cannot delete last chat',
            'new_chat_placeholder': 'Name...',
            'rename_chat_placeholder': 'New name...',
            'oa_choose_chat': 'Choose a chat',
            'fallback_thinking_note': 'Starting execution...',
            'tools_no_final': 'Done.',
            'tool_call_bad_json': 'Bad JSON: {error}',
            'tool_call_not_object': 'Not an object',
            'tool_call_unknown': 'Unknown tool: {tool_name}',
            'tool_call_nearest': 'Nearest: {nearest}',
            'tool_call_args_not_object': 'Bad args',
            'answer_file_request': 'Request',
            'answer_file_answer': 'Answer',
            'answer_file_too_long': 'Answer too long, sending as file.',
            'answer_file_attach_failed': 'Failed to attach file.',
            'continued': 'continued',
            'cancelled': 'Cancelled',
            'context_cleared': 'Context cleared',
            'clear_button': 'Clear',
            'regenerate_button': 'Regenerate',
            'cancel_button': 'Cancel',
            'reply_analyze_prompt': 'Analyze reply.',
            'skills_empty': 'No skills installed',
            'skillinstall_usage': 'Usage: .skillinstall <name>',
            'sendss_usage': 'Usage: .sendss <name>',
            'skill_not_found': 'Skill not found',
            'skill_name_required': 'Skill name required',
            'skill_not_found_repo': 'Skill not in repo: {query}',
            'skill_saved': 'Skill saved: {name}',
            'unknown_skills_tool': 'Unknown skill tool: {tool}',
            'imss_need_reply': 'Reply to a .md file',
            'skill_empty': 'Skill is empty',
            'delss_usage': 'Usage: .delss <name>',
            'skill_installed': 'Skill installed: <code>{name}</code>',
            'skill_imported': 'Skill imported: <code>{name}</code>',
            'skill_deleted': 'Skill deleted: <code>{name}</code>',
            'plugin_install_failed': 'Plugin install failed: <code>{error}</code>',
            'plugin_installed': 'Plugin installed: <code>{name}</code>',
            'plugins_enabled_title': '<b>Enabled plugins:</b>\n',
            'plugins_none_installed': '\nNo plugins\n',
            'plugins_total': '\n<b>Total:</b> {count}',
            'plugin_catalog_btn': 'Catalog',
            'plugin_manager_btn': 'Manager',
            'close_btn': 'Close',
            'plugin_repo_empty': 'No plugins in repo',
            'plugin_no_description': 'No description',
            'plugin_more_tools': ' ...and {count} more',
            'plugin_tools_label': 'Tools',
            'plugin_installed_btn': 'Installed',
            'plugin_install_btn': 'Install',
            'plugin_code_btn': 'Code',
            'back_btn': 'Back',
            'plugin_installing': 'Installing...',
            'plugin_installed_alert': '{name} installed!',
            'generic_error': 'Error: {error}',
            'plugin_manager_no_installed': 'No installed plugins',
            'plugin_version_label': 'Version',
            'plugin_actions_title': '<b>Actions:</b>',
            'plugin_delete_btn': 'Delete',
            'plugin_deleted_alert': '{name} deleted',
            'thinking_empty_text': 'Thinking...',
            'thinking_template_default': 'Thinking...',
            'request_label_default': 'Prompt:',
            'response_label_default': 'Answer:',
            'status_thinking': 'Thinking',
            'status_terminal': 'Running command',
            'status_web': 'Web search',
            'status_file': 'File',
            'status_mcub': 'MCUB',
            'status_message': 'Message',
            'status_chat': 'Chat',
            'status_dialog': 'Dialogs',
            'status_code': 'Code',
            'status_todo': 'TODO',
            'status_default': 'Running {tool}',
            'tool_confirmation_approved': 'Running',
            'tool_confirmation_yes_text': 'Run',
            'tool_confirmation_no_text': 'Cancel',
            'tool_validation_retry_prompt': 'Fix the tool call and retry.',
            'follow_up_button': 'Continue',
            'follow_up_placeholder': 'Enter request...',
            'regen_stale': 'Request expired',
            'regenerating': 'Regenerating...',
            'auto_name_prompt': 'Create a short title. Request: {prompt}',
        }
        text = _strings.get(key, key)
        try:
            return text.format(**kwargs)
        except:
            return text
    instance.strings = _oa_strings

    def _oa_args_raw(event):
        text = getattr(event, 'raw_text', '') or getattr(event, 'text', '') or ''
        parts = text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ''
    instance.args_raw = _oa_args_raw

    def _oa_callback(ttl=900):
        def decorator(func):
            func._is_mcub_callback = True
            func._ttl = ttl
            return func
        return decorator
    instance.callback = _oa_callback

    def _oa_command(name, alias=None, doc_ru="", doc_en=""):
        def decorator(func):
            func._is_mcub_cmd = True
            func._cmd_name = name
            func._aliases = alias if isinstance(alias, list) else ([alias] if alias else [])
            return func
        return decorator
    instance.command = _oa_command

    client.register_mcub_module(module_name, instance)
    for attr_name in dir(instance):
        attr = getattr(instance, attr_name)
        if not callable(attr):
            continue
        if getattr(attr, '_is_mcub_cmd', False):
            cmd_name = getattr(attr, '_cmd_name', attr_name)
            client.mcub_command(cmd_name)(attr)
        if getattr(attr, '_is_mcub_inline', False):
            inline_name = getattr(attr, '_cmd_name', attr_name)
            client.mcub_kernel.register_inline_handler(inline_name, attr)
        if getattr(attr, '_is_mcub_callback', False):
            prefix = attr_name.replace('_callback', '').replace('_handler', '')
            client.mcub_kernel.register_callback_handler(prefix, attr)
        if getattr(attr, '_is_mcub_watcher', False):
            client.mcub_watcher()(attr)
    if hasattr(instance, 'on_load'):
        asyncio.create_task(_safe_on_load(instance))
    return instance

async def _safe_on_load(instance):
    try:
        await instance.on_load()
    except Exception as e:
        logging.getLogger("mcub_auto_reg").error(f"on_load error: {e}")


# ============================================
# ADAPTER PATCH FOR UNIFIED CLIENT
# ============================================

def patch_adapter_for_unified_client():
    """Patch adapter.py imports to use UnifiedTelegramClient."""
    # Эта функция вызывается из kernel.py для совместимости
    # Реальная работа делается через auto_register_mcub_module
    pass

# ============================================
# ADAPTER COMPATIBILITY LAYER
# ============================================

def create_mcub_kernel_for_adapter(client):
    """Sozdat kernel dlya adapter.py sovmestimosti."""
    kernel = client.mcub_kernel if hasattr(client, 'mcub_kernel') else MCUBKernelInterface(client)
    class KernelRegister:
        def command(self, name, *args, **kwargs):
            def dec(func):
                async def wrapper(event):
                    _safe_edit_patch(event)
                    await func(event)
                pattern = rf"(?i)^\.{re.escape(name)}(?:\s|$)"
                client.on(events.NewMessage(pattern=pattern, outgoing=True))(wrapper)
                return func
            return dec
        def watcher(self, *args, **kwargs):
            def dec(func):
                async def wrapper(event):
                    _safe_edit_patch(event)
                    await func(event)
                client.on(events.NewMessage(incoming=True))(wrapper)
                return func
            return dec
    kernel.register = KernelRegister()
    return kernel

# ============================================
# EXPORTS
# ============================================

__all__ = [
    'UnifiedTelegramClient',
    'MCUBKernelInterface',
    'InlineQueryEvent',
    'InlineResultBuilder',
    'InlineArticleResult',
    'InlinePhotoResult',
    'CallbackQueryEvent',
    'ConversationMock',
    'auto_register_mcub_module',
    'create_mcub_kernel_for_adapter',
    '_safe_edit_patch',
]
