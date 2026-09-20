# SPDX-License-Identifier: MIT
# meta: name=protect version=1.0.0 author=hydra-team framework=mcub
# Copyright (c) 2026 Шмэлькa | @hairpin01
# name: system
# description: API protection + system commands (restart, lockdown, analytics)
from __future__ import annotations

import asyncio
import datetime
import json
import math
import os
import sys
import time
from collections import defaultdict, deque

from telethon import Button
from telethon.tl import TLRequest

# ── Импорт утилит из misc.py с fallback ──────────────────────────────
try:
    from misc import edit_or_reply, fast_animation, rate_limit
except ImportError:
    async def edit_or_reply(event, text: str, **kwargs):
        try:
            if getattr(event, "out", False):
                return await event.edit(text, **kwargs)
            return await event.reply(text, **kwargs)
        except Exception:
            return await event.reply(text, **kwargs)

    async def fast_animation(message, emoji: str, final_text: str):
        try:
            await message.edit(emoji)
            await asyncio.sleep(0.05)
            await message.edit(final_text)
        except Exception:
            try:
                await message.edit(final_text)
            except:
                pass

    def rate_limit(limit: int = 20, period: int = 120):
        def decorator(func):
            return func
        return decorator

# ── Конфиг ядра (если доступен) ──────────────────────────────────────
try:
    from core.lib.loader.module_config import (
        Boolean, Choice, ConfigValue, Float, Integer, ModuleConfig,
    )
    from core.lib.loader.module_config import List as ListValidator
    from utils.strings import Strings
    _HAS_CORE = True
except ImportError:
    _HAS_CORE = False
    # Заглушки для автономного запуска
    class ModuleConfig:
        def __init__(self, *values): pass
        def get(self, k, d=None): return d
        def from_dict(self, d): pass
        def to_dict(self): return {}
    class ConfigValue:
        def __init__(self, name, default, **kw): self.name = name; self.default = default
    Boolean = Integer = Float = Choice = ListValidator = lambda **kw: None
    class Strings:
        def __init__(self, k, d): self._active = {}

# ── Константы ─────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "time_sample": 30,
    "limit_profile": "normal",
    "custom_threshold": 200,
    "local_floodwait": 30,
    "ignore_methods": ["GetMessagesRequest"],
    "enable_protection": True,
    "mcub_mode": "safe",
    "mcub_dry_run": False,
    "mcub_allowlist": [],
    "mcub_lockdown": False,
    "enable_analytics": True,
    "zscore_threshold": 3.0,
    "warn_percent": 90,
    "predict_window": 10,
    "baseline_window": 300,
    "profile_min_samples": 50,
    "predict_alert_cooldown": 10,
    "warn_alert_cooldown": 30,
}

LIMIT_PROFILES = {
    "conservative": 100,
    "normal": 200,
    "aggressive": 350,
}

LIST_CONFIG_KEYS = {"ignore_methods", "mcub_allowlist"}
RESTART_STATE_FILE = ".hydra_restart_state.json"

# ── Языковые строки (fallback) ───────────────────────────────────────
FALLBACK_LANG = {
    "api_analyze_report": (
        "📊 <b>API Analytics Report</b>\n\n"
        "<b>🪟 Window counts:</b>\n{windows}\n\n"
        "<b>📈 Z-score:</b> {zscore}\n"
        "<b>🎯 Threshold:</b> <code>{threshold}</code>\n"
        "<b>⏱ ETA to breach:</b> {eta}\n"
        "<b>🚀 Acceleration:</b> {accel}\n"
        "<b>🎭 Profile similarity:</b> {cosine}\n\n"
        "<b>🔀 Top transitions:</b>\n{transitions}\n\n"
        "<b>⚠️ Anomalous transitions:</b>\n{anomalous}\n\n"
        "<b>🔒 Backoff:</b> <code>{backoff}</code>"
    ),
    "analyze_eta_safe": "✅ Safe — no breach predicted",
    "analyze_eta_now": "🚨 <b>NOW</b>",
    "analyze_eta_in": "⚠️ ~{seconds}s",
    "analyze_profile_insufficient": "⏳ Insufficient data",
    "mcub_violation": "🛡 <b>MCUB violation</b> [<code>{mode}</code>]\n\n<code>{method}</code>\n<b>Reason:</b> <i>{reason}</i>",
    "api_warn_threshold": "⚠️ <b>API Warning:</b> {percent}% ({current}/{threshold} per {interval}s)",
    "api_predict_block": "🔮 <b>Predictive alert:</b> breach in ~{eta}s (accel {accel} req/s²)",
    "api_overload_notify": (
        "🚨 <b>API Overload triggered!</b>\n\n"
        "<b>Interval:</b> <code>{interval}s</code>\n"
        "<b>Total:</b> <code>{total}</code> / <code>{threshold}</code>\n"
        "<b>Trigger:</b> <code>{trigger}</code>\n"
        "<b>Block:</b> <code>{block_seconds}s</code> (attempt #{trigger_count})\n\n"
        "<b>Top methods:</b>\n{methods}"
    ),
    "are_you_sure": "🛡 <b>Configure API protection?</b>",
    "yes": "Yes",
    "no": "No",
    "api_protection_on": "API protection enabled",
    "api_protection_off": "API protection disabled",
    "mcub_choose_mode": "Choose MCUB protection mode:",
    "mcub_mode_default": "Default ({mode})",
    "mcub_mode_set": "MCUB mode: {mode}{dry}",
    "api_protection_enabled": "✅ <b>API protection enabled</b>",
    "api_protection_disabled": "❌ <b>API protection disabled</b>",
    "api_param_set": "✅ <b>{param}</b> set to <code>{value}</code>",
    "api_param_error": "❌ <b>Invalid parameter or value</b>",
    "api_protection_usage": (
        "<b>Usage:</b>\n"
        "  <code>.api_protection</code> — toggle menu\n"
        "  <code>.api_protection on/off</code>\n"
        "  <code>.api_protection &lt;param&gt; &lt;value&gt;</code>"
    ),
    "api_reset_done": "🗑 <b>API stats reset</b>",
    "api_suspend": "⏸ <b>Protection suspended</b> for {seconds}s",
    "restart_init": "🔄 <b>Restarting...</b>",
    "restart_done": (
        "<tg-emoji emoji-id=\"5368585403467048206\">🪬</tg-emoji> "
        "<b>Restart complete</b>\n\n"
        "⏱ <b>Uptime:</b> <code>{uptime}</code>\n"
        "🔄 <b>PID:</b> <code>{old_pid} → {new_pid}</code>"
    ),
    "restart_error": "❌ <b>Restart failed:</b> <code>{error}</code>",
}


def _coerce_method_list(value: object, default: list[str] | None = None) -> list[str]:
    fallback = list(default or [])
    parsed: object = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in text.split(",")]
    if isinstance(parsed, (list, tuple, set)):
        result: list[str] = []
        for item in parsed:
            if item is None:
                continue
            method = str(item).strip()
            if method:
                result.append(method)
        return result
    return fallback


# ═══════════════════════════════════════════════════════════════════════
#  RequestAnalyzer — полностью как в оригинале
# ═══════════════════════════════════════════════════════════════════════
class RequestAnalyzer:
    WINDOWS = [1, 5, 15, 60]

    def __init__(self, request_log: deque, ignore_set_fn, config: dict):
        self._log = request_log
        self._ignore_set = ignore_set_fn
        self._cfg = config
        self._sec_buckets: dict[int, int] = {}
        self._transitions: defaultdict = defaultdict(int)
        self._last_method: str | None = None
        self._hourly_profile: dict[int, defaultdict] = defaultdict(lambda: defaultdict(int))
        self._hourly_total: dict[int, int] = defaultdict(int)
        self.anomaly_log: deque = deque(maxlen=200)
        self.trigger_count: int = 0
        self.last_trigger_at: float = 0.0

    def record(self, method: str, ts: float) -> None:
        sec = int(ts)
        self._sec_buckets[sec] = self._sec_buckets.get(sec, 0) + 1
        cutoff_sec = sec - self._cfg.get("baseline_window", 300)
        for k in [k for k in self._sec_buckets if k < cutoff_sec]:
            del self._sec_buckets[k]
        if self._last_method is not None:
            self._transitions[(self._last_method, method)] += 1
        self._last_method = method
        hour = datetime.datetime.fromtimestamp(ts).hour
        self._hourly_profile[hour][method] += 1
        self._hourly_total[hour] += 1

    def window_counts(self, now: float) -> dict:
        ignore = self._ignore_set()
        result = {}
        for w in self.WINDOWS:
            cutoff = now - w
            total = relevant = 0
            for m, ts in self._log:
                if ts > cutoff:
                    total += 1
                    if m not in ignore:
                        relevant += 1
            result[w] = {"total": total, "relevant": relevant}
        return result

    def zscore(self, now: float) -> float:
        measure_window = 5
        baseline_sec = self._cfg.get("baseline_window", 300)
        cutoff_now = now - measure_window
        current_count = sum(1 for _, ts in self._log if ts > cutoff_now)
        current_rate = current_count / measure_window
        now_sec = int(now)
        baseline_floor = now_sec - baseline_sec
        baseline_vals = [
            v for k, v in self._sec_buckets.items()
            if baseline_floor <= k < now_sec - measure_window
        ]
        if len(baseline_vals) < 10:
            return 0.0
        mean = sum(baseline_vals) / len(baseline_vals)
        variance = sum((x - mean) ** 2 for x in baseline_vals) / len(baseline_vals)
        std = math.sqrt(variance)
        if std < 1e-6:
            return 0.0
        return (current_rate - mean) / std

    def acceleration(self, now: float) -> float:
        ignore = self._ignore_set()
        recent = sum(1 for m, ts in self._log if now - 5 < ts <= now and m not in ignore) / 5
        prior = sum(1 for m, ts in self._log if now - 10 < ts <= now - 5 and m not in ignore) / 5
        return recent - prior

    def predict_eta(self, now: float, threshold: int) -> float | None:
        ignore = self._ignore_set()
        pw = self._cfg.get("predict_window", 10)
        tw = self._cfg.get("time_sample", 15)
        current = sum(1 for m, ts in self._log if ts > now - tw and m not in ignore)
        if current >= threshold:
            return 0.0
        rate = sum(1 for m, ts in self._log if ts > now - pw and m not in ignore) / pw
        if rate <= 0:
            return None
        accel = self.acceleration(now)
        remaining = threshold - current
        if abs(accel) < 1e-6:
            return remaining / rate
        a_coef = 0.5 * accel
        b_coef = rate
        c_coef = -remaining
        discriminant = b_coef ** 2 - 4 * a_coef * c_coef
        if discriminant < 0 or a_coef == 0:
            return remaining / rate if rate > 0 else None
        t1 = (-b_coef + math.sqrt(discriminant)) / (2 * a_coef)
        t2 = (-b_coef - math.sqrt(discriminant)) / (2 * a_coef)
        candidates = [t for t in (t1, t2) if t > 0]
        return min(candidates) if candidates else None

    def top_transitions(self, limit: int = 5) -> list:
        return sorted(self._transitions.items(), key=lambda x: x[1], reverse=True)[:limit]

    def anomalous_transitions(self, z_thresh: float = 2.5) -> list:
        if len(self._transitions) < 3:
            return []
        vals = list(self._transitions.values())
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        if std < 1e-6:
            return []
        out = []
        for pair, count in self._transitions.items():
            z = (count - mean) / std
            if z > z_thresh:
                out.append((pair, count, round(z, 2)))
        return sorted(out, key=lambda x: x[2], reverse=True)[:5]

    def cosine_similarity(self, now: float) -> float | None:
        hour = datetime.datetime.fromtimestamp(now).hour
        profile = self._hourly_profile.get(hour)
        total_p = self._hourly_total.get(hour, 0)
        min_s = self._cfg.get("profile_min_samples", 50)
        if not profile or total_p < min_s:
            return None
        current: defaultdict = defaultdict(int)
        for m, ts in self._log:
            if ts > now - 60:
                current[m] += 1
        if not current:
            return None
        all_methods = set(profile.keys()) | set(current.keys())
        total_c = sum(current.values())
        vec_p = [profile.get(m, 0) / total_p for m in all_methods]
        vec_c = [current.get(m, 0) / total_c for m in all_methods]
        dot = sum(a * b for a, b in zip(vec_p, vec_c, strict=False))
        mag_p = math.sqrt(sum(a * a for a in vec_p))
        mag_c = math.sqrt(sum(b * b for b in vec_c))
        if mag_p < 1e-9 or mag_c < 1e-9:
            return None
        return dot / (mag_p * mag_c)

    def backoff_seconds(self) -> float:
        base = self._cfg.get("local_floodwait", 30)
        return min(base * (2 ** min(self.trigger_count, 5)), 600)

    def on_trigger(self, now: float) -> None:
        self.trigger_count += 1
        self.last_trigger_at = now

    def maybe_reset_backoff(self, now: float) -> None:
        quiet_threshold = self._cfg.get("local_floodwait", 30) * 4
        if self.trigger_count > 0 and now - self.last_trigger_at > quiet_threshold:
            self.trigger_count = 0

    def reset(self) -> None:
        self._sec_buckets.clear()
        self._transitions.clear()
        self._last_method = None
        self._hourly_profile.clear()
        self._hourly_total.clear()
        self.anomaly_log.clear()
        self.trigger_count = 0
        self.last_trigger_at = 0.0

    def full_report(self, now: float, threshold: int, lang: dict) -> str:
        self._ignore_set()
        windows = self.window_counts(now)
        z = self.zscore(now)
        eta = self.predict_eta(now, threshold)
        accel = self.acceleration(now)
        cosine = self.cosine_similarity(now)
        top_tr = self.top_transitions(5)
        anom_tr = self.anomalous_transitions()

        win_lines = []
        for w in self.WINDOWS:
            d = windows[w]
            win_lines.append(f"  `{w:>2}s` — all: **{d['total']}**  /  relevant: **{d['relevant']}**")

        z_str = f"**{z:+.2f}σ**"
        z_flag = " ⚠️" if abs(z) >= self._cfg.get("zscore_threshold", 3.0) else ""

        if eta is None:
            eta_str = lang.get("analyze_eta_safe", "Safe")
        elif eta == 0.0:
            eta_str = lang.get("analyze_eta_now", "NOW")
        else:
            eta_str = lang.get("analyze_eta_in", "~{seconds}s").format(seconds=round(eta, 1))

        accel_str = f"{accel:+.2f} req/s²"
        accel_flag = " 🚀" if accel > 2 else (" 🐢" if accel < -2 else "")

        if cosine is None:
            cosine_str = lang.get("analyze_profile_insufficient", "N/A")
        else:
            pct = round(cosine * 100, 1)
            flag = " ⚠️" if pct < 60 else ""
            cosine_str = f"**{pct}%**{flag}"

        tr_lines = "\n".join(f"  `{p}→{c}`: {n}x" for (p, c), n in top_tr) if top_tr else "  —"
        anom_lines = "\n".join(f"  `{p}→{c}`: {n}x  (z={z})" for (p, c), n, z in anom_tr) if anom_tr else "  —"
        backoff_str = f"{self.backoff_seconds():.0f}s (trigger #{self.trigger_count})"

        return lang.get("api_analyze_report", FALLBACK_LANG["api_analyze_report"]).format(
            windows="\n".join(win_lines),
            zscore=z_str + z_flag,
            threshold=threshold,
            eta=eta_str,
            accel=accel_str + accel_flag,
            cosine=cosine_str,
            transitions=tr_lines,
            anomalous=anom_lines,
            backoff=backoff_str,
        )


# ═══════════════════════════════════════════════════════════════════════
#  Restart helpers
# ═══════════════════════════════════════════════════════════════════════
async def _handle_restart_status(kernel, lang: dict):
    """При старте проверяем, не была ли это перезагрузка."""
    if not os.path.exists(RESTART_STATE_FILE):
        return
    try:
        with open(RESTART_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        chat_id = state.get("chat_id")
        message_id = state.get("message_id")
        old_pid = state.get("pid", "?")
        os.remove(RESTART_STATE_FILE)
        if chat_id and message_id:
            await asyncio.sleep(1.5)  # дать клиенту подключиться
            uptime = datetime.datetime.now().strftime("%H:%M:%S")
            text = lang.get("restart_done", FALLBACK_LANG["restart_done"]).format(
                uptime=uptime, old_pid=old_pid, new_pid=os.getpid()
            )
            try:
                await kernel.client.edit_message(chat_id, message_id, text, parse_mode="html")
            except Exception:
                await kernel.client.send_message(chat_id, text, parse_mode="html")
    except Exception as e:
        kernel.logger.warning(f"Restart status handler error: {e}")


# ═══════════════════════════════════════════════════════════════════════
#  Register
# ═══════════════════════════════════════════════════════════════════════
def register(kernel):
    client = kernel.client

    strings_data = {"name": "system"}
    strings = Strings(kernel, strings_data) if _HAS_CORE else type("S", (), {"_active": FALLBACK_LANG})()
    lang = strings._active if hasattr(strings, "_active") else FALLBACK_LANG

    # ── Config ─────────────────────────────────────────────────────────
    if _HAS_CORE:
        config = ModuleConfig(
            ConfigValue("time_sample", 30, description="Time window for sample (seconds)", validator=Integer(default=30, min=1)),
            ConfigValue("limit_profile", "normal", description="API limit profile", validator=Choice(choices=["conservative", "normal", "aggressive", "custom"], default="normal")),
            ConfigValue("custom_threshold", 200, description="Custom threshold (req/30s)", validator=Integer(default=200, min=1)),
            ConfigValue("local_floodwait", 30, description="Local floodwait duration (seconds)", validator=Integer(default=30, min=1)),
            ConfigValue("ignore_methods", ["GetMessagesRequest"], description="Methods to ignore", validator=ListValidator(default=["GetMessagesRequest"], item_type=str)),
            ConfigValue("enable_protection", True, description="Enable API protection", validator=Boolean(default=True)),
            ConfigValue("mcub_mode", "safe", description="MCUB protection mode", validator=Choice(choices=["off", "safe", "strict", "custom"], default="safe")),
            ConfigValue("mcub_dry_run", False, description="Observe violations without blocking", validator=Boolean(default=False)),
            ConfigValue("mcub_allowlist", [], description="Methods excluded in custom mode", validator=ListValidator(default=[], item_type=str)),
            ConfigValue("mcub_lockdown", False, description="Lockdown mode", validator=Boolean(default=False)),
            ConfigValue("enable_analytics", True, description="Enable analytics", validator=Boolean(default=True)),
            ConfigValue("zscore_threshold", 3.0, description="Z-score anomaly threshold", validator=Float(default=3.0, min=0.0)),
            ConfigValue("warn_percent", 90, description="Warning threshold percentage", validator=Integer(default=90, min=0, max=100)),
            ConfigValue("predict_window", 10, description="Prediction window", validator=Integer(default=10, min=1)),
            ConfigValue("baseline_window", 300, description="Baseline window (seconds)", validator=Integer(default=300, min=10)),
            ConfigValue("profile_min_samples", 50, description="Minimum samples for profile", validator=Integer(default=50, min=1)),
            ConfigValue("predict_alert_cooldown", 10, description="Predict alert cooldown (seconds)", validator=Integer(default=10, min=1)),
            ConfigValue("warn_alert_cooldown", 30, description="Warn alert cooldown (seconds)", validator=Integer(default=30, min=1)),
        )
    else:
        config = type("C", (), {"get": lambda self, k, d=None: DEFAULT_CONFIG.get(k, d), "from_dict": lambda self, d: None, "to_dict": lambda self: DEFAULT_CONFIG.copy()})()

    api_config = config
    protection_enabled = bool(api_config.get("enable_protection", True))

    def _normalize_list_config_values(target_config) -> None:
        for key in LIST_CONFIG_KEYS:
            target_config[key] = _coerce_method_list(target_config.get(key), DEFAULT_CONFIG.get(key, []))

    def get_config():
        live_cfg = getattr(kernel, "_live_module_configs", {}).get(__name__)
        if live_cfg:
            return live_cfg
        return config

    # ── Startup ────────────────────────────────────────────────────────
    async def startup():
        nonlocal protection_enabled
        config_dict = await kernel.get_module_config(__name__, DEFAULT_CONFIG.copy()) if hasattr(kernel, "get_module_config") else DEFAULT_CONFIG.copy()
        if isinstance(config_dict, dict):
            for key in LIST_CONFIG_KEYS:
                if key in config_dict and not isinstance(config_dict[key], list):
                    config_dict[key] = _coerce_method_list(config_dict[key], DEFAULT_CONFIG.get(key, []))
        if _HAS_CORE:
            config.from_dict(config_dict)
        _normalize_list_config_values(config if _HAS_CORE else config_dict)
        protection_enabled = bool(config.get("enable_protection", True) if _HAS_CORE else config_dict.get("enable_protection", True))
        if hasattr(kernel, "save_module_config"):
            cfg_clean = {k: v for k, v in (config.to_dict() if _HAS_CORE else config_dict).items() if v is not None}
            if cfg_clean:
                await kernel.save_module_config(__name__, cfg_clean)
        if hasattr(kernel, "store_module_config_schema"):
            kernel.store_module_config_schema(__name__, config)

        if _mcub_available:
            mode = config.get("mcub_mode", "safe")
            if _apply_mcub_mode(mode):
                try:
                    client.clear_blocked_request_handler()
                except Exception:
                    pass
                client.on_blocked_request(_mcub_violation_handler)
                kernel.logger.info(f"MCUB protection mode set to '{mode}' (lockdown={config.get('mcub_lockdown', False)})")

        # Проверяем статус перезагрузки
        await _handle_restart_status(kernel, lang)

    asyncio.create_task(startup())

    def persist_api_config():
        cfg = get_config()
        if cfg and hasattr(kernel, "save_module_config"):
            asyncio.create_task(kernel.save_module_config(__name__, cfg.to_dict() if hasattr(cfg, "to_dict") else dict(cfg)))

    # ── State ──────────────────────────────────────────────────────────
    blocked_until = 0.0
    original_call = None
    request_log = deque(maxlen=10000)
    last_predict_alert = 0.0
    last_warn_alert = 0.0

    analyzer = RequestAnalyzer(
        request_log=request_log,
        ignore_set_fn=lambda: set(_coerce_method_list(api_config.get("ignore_methods", []))),
        config=api_config if _HAS_CORE else DEFAULT_CONFIG,
    )

    _mcub_available = (
        hasattr(client, "set_protection_mode")
        and hasattr(client, "on_blocked_request")
        and hasattr(client, "set_protection_policy")
    )

    # ── MCUB helpers ───────────────────────────────────────────────────
    def _apply_mcub_mode(mode: str) -> bool:
        if not _mcub_available:
            return False
        try:
            if mode == "custom":
                from telethon.client.protection import STRICT_DANGEROUS_REQUESTS, build_protection_policy
                lockdown = api_config.get("mcub_lockdown", False)
                dry_run = api_config.get("mcub_dry_run", False)
                if lockdown:
                    from telethon.tl.functions.account import (
                        UpdateProfileRequest, UpdateUsernameRequest, UpdateStatusRequest,
                        UpdateColorRequest, UpdateEmojiStatusRequest, UpdateBirthdayRequest,
                        UpdatePersonalChannelRequest, DeleteSecureValueRequest,
                        ResetNotifySettingsRequest, SaveWallPaperRequest,
                    )
                    from telethon.tl.functions.channels import (
                        CreateChannelRequest, DeleteChannelRequest, EditAdminRequest,
                        EditBannedRequest, EditCreatorRequest, EditPhotoRequest,
                        EditTitleRequest, InviteToChannelRequest, JoinChannelRequest,
                        LeaveChannelRequest, ToggleAntiSpamRequest,
                    )
                    from telethon.tl.functions.contacts import DeleteContactsRequest, UnblockRequest
                    from telethon.tl.functions.messages import (
                        AddChatUserRequest, ClearAllDraftsRequest, CreateChatRequest,
                        DeleteChatRequest, DeleteHistoryRequest, DeleteMessagesRequest,
                        DeleteScheduledMessagesRequest, EditChatAboutRequest,
                        ImportChatInviteRequest, SaveDraftRequest, UpdateDialogFilterRequest,
                    )
                    from telethon.tl.functions.photos import (
                        DeletePhotosRequest, UploadProfilePhotoRequest,
                        UpdateProfilePhotoRequest as PhotosUpdateProfilePhotoRequest,
                    )
                    from telethon.tl.functions.stories import DeleteStoriesRequest

                    extra_blocked = (
                        UpdateProfileRequest, UpdateUsernameRequest, UpdateStatusRequest,
                        UpdateColorRequest, UpdateEmojiStatusRequest, UpdateBirthdayRequest,
                        UpdatePersonalChannelRequest, DeleteSecureValueRequest,
                        ResetNotifySettingsRequest, SaveWallPaperRequest,
                        CreateChatRequest, AddChatUserRequest, DeleteChatRequest,
                        EditChatAboutRequest, ImportChatInviteRequest, ClearAllDraftsRequest,
                        DeleteHistoryRequest, DeleteMessagesRequest, DeleteScheduledMessagesRequest,
                        SaveDraftRequest, UpdateDialogFilterRequest,
                        CreateChannelRequest, InviteToChannelRequest, EditAdminRequest,
                        EditBannedRequest, EditTitleRequest, EditPhotoRequest, EditCreatorRequest,
                        ToggleAntiSpamRequest, DeleteChannelRequest, JoinChannelRequest,
                        LeaveChannelRequest, DeleteContactsRequest, UnblockRequest,
                        PhotosUpdateProfilePhotoRequest, UploadProfilePhotoRequest,
                        DeletePhotosRequest, DeleteStoriesRequest,
                    )
                    policy = build_protection_policy(
                        "custom",
                        blocked_requests=STRICT_DANGEROUS_REQUESTS + extra_blocked,
                        dry_run=dry_run,
                    )
                else:
                    allowlist = set(_coerce_method_list(api_config.get("mcub_allowlist", [])))
                    policy = build_protection_policy(
                        "custom",
                        allowed_requests=tuple(allowlist) if allowlist else None,
                        dry_run=dry_run,
                    )
                client.set_protection_policy(policy)
            else:
                client.set_protection_mode(mode)
            return True
        except Exception as e:
            kernel.logger.error(f"Failed to apply MCUB mode '{mode}': {e}")
            return False

    async def _mcub_violation_handler(violation) -> None:
        try:
            method = getattr(violation, "method", None) or type(violation).__name__
            reason = getattr(violation, "reason", str(violation))
            mode = api_config.get("mcub_mode", "safe")
            kernel.logger.warning(f"MCUB violation [{mode}]: {method} — {reason}")
            now = time.time()
            request_log.append((method, now))
            if api_config.get("enable_analytics", True):
                analyzer.record(method, now)
            if not kernel.log_chat_id:
                return
            text = lang.get("mcub_violation", FALLBACK_LANG["mcub_violation"]).format(method=method, mode=mode, reason=reason)
            try:
                await kernel.client.send_message(kernel.log_chat_id, text, parse_mode="html")
            except Exception:
                try:
                    await kernel.client.send_message("me", text, parse_mode="html")
                except Exception:
                    pass
        except Exception as e:
            kernel.logger.error(f"MCUB violation handler error: {e}")

    # ── Interceptor ────────────────────────────────────────────────────
    async def api_call_interceptor(sender, request: TLRequest, ordered: bool = False, flood_sleep_threshold: int | None = None):
        nonlocal blocked_until, protection_enabled
        now = time.time()
        method = request.__class__.__name__

        if not protection_enabled:
            return await original_call(sender, request, ordered, flood_sleep_threshold)

        if now < blocked_until:
            await asyncio.sleep(blocked_until - now)
            now = time.time()

        request_log.append((method, now))
        if api_config.get("enable_analytics", True):
            analyzer.record(method, now)
            analyzer.maybe_reset_backoff(now)

        interval = api_config.get("time_sample", 30) if hasattr(api_config, "get") else DEFAULT_CONFIG["time_sample"]
        ignore_set = set(_coerce_method_list(api_config.get("ignore_methods", []) if hasattr(api_config, "get") else DEFAULT_CONFIG["ignore_methods"]))
        profile = api_config.get("limit_profile", "normal") if hasattr(api_config, "get") else DEFAULT_CONFIG["limit_profile"]
        threshold = api_config.get("custom_threshold", 200) if profile == "custom" else LIMIT_PROFILES.get(profile, 200)
        cutoff = now - interval
        total_relevant = sum(1 for m, ts in request_log if ts > cutoff and m not in ignore_set)

        if total_relevant > threshold and now >= blocked_until:
            analyzer.on_trigger(now)
            block_dur = analyzer.backoff_seconds()
            blocked_until = now + block_dur
            kernel.logger.warning(
                f"API protection triggered (attempt #{analyzer.trigger_count}): "
                f"{total_relevant} relevant requests in {interval}s — blocking for {block_dur:.0f}s"
            )
            asyncio.create_task(notify_overload(kernel, lang, method, total_relevant, interval, threshold, block_dur, analyzer.trigger_count))
            return await original_call(sender, request, ordered, flood_sleep_threshold)

        if not api_config.get("enable_analytics", True):
            return await original_call(sender, request, ordered, flood_sleep_threshold)

        warn_pct = api_config.get("warn_percent", 90)
        eta = analyzer.predict_eta(now, threshold)
        accel = analyzer.acceleration(now)
        predict_cooldown = api_config.get("predict_alert_cooldown", 10)
        warn_cooldown = api_config.get("warn_alert_cooldown", 30)

        nonlocal last_predict_alert, last_warn_alert

        if total_relevant >= threshold * warn_pct / 100 and total_relevant < threshold:
            if now - last_warn_alert >= warn_cooldown:
                last_warn_alert = now
                pct = round(total_relevant / threshold * 100)
                asyncio.create_task(send_warn(kernel, lang.get("api_warn_threshold", FALLBACK_LANG["api_warn_threshold"]).format(percent=pct, current=total_relevant, threshold=threshold, interval=interval)))

        elif eta is not None and 0 < eta < 5 and accel > 0:
            if now - last_predict_alert >= predict_cooldown:
                last_predict_alert = now
                asyncio.create_task(send_warn(kernel, lang.get("api_predict_block", FALLBACK_LANG["api_predict_block"]).format(eta=round(eta, 1), accel=round(accel, 2))))

        return await original_call(sender, request, ordered, flood_sleep_threshold)

    # ── Install / Uninstall ────────────────────────────────────────────
    @kernel.register.on_load()
    async def install_interceptor(kernel):
        nonlocal original_call
        if hasattr(client, "_original_call"):
            kernel.logger.debug("API interceptor already installed")
            return
        original_call = client._call
        client._call = api_call_interceptor
        client._original_call = original_call
        if not _mcub_available:
            kernel.logger.debug("Telethon-MCUB not detected, skipping native protection setup")

    @kernel.register.uninstall()
    async def uninstall_interceptor(kernel):
        nonlocal original_call
        if hasattr(client, "_original_call"):
            client._call = client._original_call
            delattr(client, "_original_call")
            kernel.logger.info("API call interceptor uninstalled")
        if _mcub_available:
            try:
                client.clear_blocked_request_handler()
                client.set_protection_mode("safe")
                kernel.logger.info("MCUB protection reset to 'safe' on uninstall")
            except Exception as e:
                kernel.logger.warning(f"MCUB cleanup error: {e}")

    # ── Notifications ──────────────────────────────────────────────────
    async def send_warn(kernel, text: str):
        if not kernel.log_chat_id:
            return
        try:
            await kernel.bot_client.send_message(kernel.log_chat_id, text, parse_mode="html")
        except (TypeError, AttributeError, ValueError):
            await kernel.client.send_message(kernel.log_chat_id, text, parse_mode="html")
        except Exception as e:
            kernel.logger.error(f"send warn error: {e}")

    async def notify_overload(kernel, lang, trigger_method, total_relevant, interval, threshold, block_seconds, trigger_count):
        if not kernel.log_chat_id:
            return
        now = time.time()
        cutoff = now - interval
        method_counts: defaultdict = defaultdict(int)
        for m, ts in request_log:
            if ts > cutoff:
                method_counts[m] += 1
        top_methods = sorted(method_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        methods_str = "\n".join(f"  `{m}`: {c}" for m, c in top_methods)
        text = lang.get("api_overload_notify", FALLBACK_LANG["api_overload_notify"]).format(
            interval=interval, total=total_relevant, threshold=threshold,
            trigger=trigger_method, block_seconds=int(block_seconds),
            trigger_count=trigger_count, methods=methods_str,
        )
        import csv, io
        filtered_log = [(ts, m) for m, ts in request_log if ts > cutoff]
        filtered_log.sort(key=lambda x: x[0])
        str_buf = io.StringIO()
        writer = csv.writer(str_buf)
        writer.writerow(["timestamp", "method"])
        for ts, m in filtered_log:
            writer.writerow([int(ts), m])
        file_name = f"api_requests_{int(now)}.csv"
        buf = io.BytesIO(str_buf.getvalue().encode("utf-8"))
        buf.name = file_name
        buf.seek(0)
        for sender in (getattr(kernel, "bot_client", None), kernel.client):
            if sender is None:
                continue
            try:
                await sender.send_file(kernel.log_chat_id, buf, caption=text, file_name=file_name, force_document=True, parse_mode="html")
                return
            except Exception:
                buf.seek(0)
        try:
            await kernel.client.send_message("me", text)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════
    #  COMMANDS
    # ═══════════════════════════════════════════════════════════════════

    @kernel.register.command("api_protection", doc_en="show/configure API protection", doc_ru="показать/настроить защиту API")
    @rate_limit(limit=10, period=60)
    async def api_protection_handler(event):
        nonlocal protection_enabled
        args = event.text.split()
        if len(args) == 1:
            yes_label = lang.get("yes", "Yes")
            no_label = lang.get("no", "No")
            buttons = [
                [Button.inline(yes_label, b"api_protection_yes", style="success"),
                 Button.inline(no_label, b"api_protection_no", style="danger")],
            ]
            await kernel.inline_form(event.chat_id, lang.get("are_you_sure", "Configure API protection?"), buttons=buttons, reply_to=getattr(event.message, "reply_to", None))
            await event.delete()
            return
        subcmd = args[1].lower()
        if subcmd in ("on", "enable", "true"):
            protection_enabled = api_config["enable_protection"] = True
            await edit_or_reply(event, lang.get("api_protection_enabled", "✅ Enabled"), parse_mode="html")
        elif subcmd in ("off", "disable", "false"):
            protection_enabled = api_config["enable_protection"] = False
            await edit_or_reply(event, lang.get("api_protection_disabled", "❌ Disabled"), parse_mode="html")
        elif len(args) >= 3:
            param = args[1]
            value = " ".join(args[2:])
            if param in (api_config.to_dict() if hasattr(api_config, "to_dict") else DEFAULT_CONFIG):
                try:
                    if param in LIST_CONFIG_KEYS:
                        api_config[param] = _coerce_method_list(value, DEFAULT_CONFIG.get(param, []))
                    elif isinstance(api_config.get(param) if hasattr(api_config, "get") else DEFAULT_CONFIG.get(param), bool):
                        api_config[param] = value.lower() in ("true", "yes", "1")
                    elif isinstance(api_config.get(param) if hasattr(api_config, "get") else DEFAULT_CONFIG.get(param), (int, float)):
                        api_config[param] = type(api_config.get(param) if hasattr(api_config, "get") else DEFAULT_CONFIG.get(param))(value)
                    else:
                        api_config[param] = value
                    if param == "enable_protection":
                        protection_enabled = bool(api_config[param])
                    await edit_or_reply(event, lang.get("api_param_set", "✅ Set {param} = {value}").format(param=param, value=api_config[param]))
                except Exception:
                    await edit_or_reply(event, lang.get("api_param_error", "❌ Error"), parse_mode="html")
                    return
            else:
                await edit_or_reply(event, lang.get("api_param_error", "❌ Error"), parse_mode="html")
                return
        else:
            await edit_or_reply(event, lang.get("api_protection_usage", FALLBACK_LANG["api_protection_usage"]), parse_mode="html")
            return
        persist_api_config()

    @kernel.register.command("api_reset", doc_en="reset API protection stats", doc_ru="сбросить статистику защиты API")
    @rate_limit(limit=5, period=60)
    async def api_reset_handler(event):
        nonlocal blocked_until
        request_log.clear()
        analyzer.reset()
        blocked_until = 0.0
        await edit_or_reply(event, lang.get("api_reset_done", "🗑 Reset done"), parse_mode="html")

    @kernel.register.command("api_suspend", doc_en="<seconds> — temporarily suspend API protection", doc_ru="<секунды> — приостановить защиту API")
    @rate_limit(limit=3, period=60)
    async def api_suspend_handler(event):
        nonlocal blocked_until
        args = event.text.split()
        if len(args) != 2 or not args[1].isdigit():
            await edit_or_reply(event, lang.get("api_protection_usage", FALLBACK_LANG["api_protection_usage"]), parse_mode="html")
            return
        seconds = int(args[1])
        blocked_until = time.time() + seconds
        await edit_or_reply(event, lang.get("api_suspend", "⏸ Suspended for {seconds}s").format(seconds=seconds), parse_mode="html")

    @kernel.register.command("lockdown", doc_en="toggle ultra-strict lockdown", doc_ru="вкл/выкл жёсткую блокировку")
    @rate_limit(limit=3, period=60)
    async def lockdown_handler(event):
        nonlocal protection_enabled
        cfg = api_config
        new_val = not cfg.get("mcub_lockdown", False)
        cfg["mcub_lockdown"] = new_val
        cfg["mcub_mode"] = "custom"
        protection_enabled = True
        _apply_mcub_mode("custom")
        # The extra protection hook exists only in the patched MCUB Telethon
        # client.  Hydra may run on stock Telethon, where the normal local
        # protection controls remain usable but this hook is unavailable.
        if _mcub_available:
            try:
                client.clear_blocked_request_handler()
            except Exception:
                pass
            client.on_blocked_request(_mcub_violation_handler)
        persist_api_config()
        ok_emoji = '<tg-emoji emoji-id="5368585403467048206">🪬</tg-emoji>'
        text = f"{ok_emoji} {'Lockdown enabled' if new_val else 'Lockdown disabled'}"
        await edit_or_reply(event, text, parse_mode="html")

    # ── RESTART (главное) ──────────────────────────────────────────────
    @kernel.register.command("restart", doc_en="Restart the bot cleanly", doc_ru="Перезагрузить бота")
    @rate_limit(limit=2, period=300)
    async def restart_handler(event):
        msg = await edit_or_reply(event, "🔄 <b>Сохранение состояния...</b>", parse_mode="html")
        state = {
            "chat_id": event.chat_id,
            "message_id": msg.id,
            "pid": os.getpid(),
            "time": time.time(),
        }
        try:
            with open(RESTART_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f)
            await msg.edit("🔄 <b>Отключение клиента...</b>", parse_mode="html")
            await asyncio.sleep(0.3)
            await kernel.client.disconnect()
            # Чистый перезапуск: заменяем текущий процесс, не оставляя зомби
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            await msg.edit(lang.get("restart_error", FALLBACK_LANG["restart_error"]).format(error=str(e)), parse_mode="html")

    # ── Callbacks ──────────────────────────────────────────────────────
    async def api_protection_callback_handler(event):
        nonlocal protection_enabled
        data = event.data
        on_label = lang.get("api_protection_on", "API protection enabled")
        off_label = lang.get("api_protection_off", "API protection disabled")
        choose_mode_label = lang.get("mcub_choose_mode", "Choose MCUB protection mode:")
        default_mode_tpl = lang.get("mcub_mode_default", "Default ({mode})")
        mode_set_tpl = lang.get("mcub_mode_set", "MCUB protection mode: {mode}{dry}")

        if data == b"api_protection_yes":
            if _mcub_available:
                current_mode = api_config.get("mcub_mode", "safe")
                buttons = [
                    [Button.inline("🥽 safe", b"api_prot_mode_safe", style="primary")],
                    [Button.inline("🔬 strict", b"api_prot_mode_strict", style="primary")],
                    [Button.inline("🤧 off", b"api_prot_mode_off", style="primary")],
                    [Button.inline(default_mode_tpl.format(mode=current_mode), b"api_prot_mode_default", style="primary")],
                ]
                await event.edit(choose_mode_label, buttons=buttons, parse_mode="html")
            else:
                protection_enabled = api_config["enable_protection"] = True
                await event.edit(f'<tg-emoji emoji-id="5368585403467048206">🪬</tg-emoji> {on_label}', parse_mode="html")
                persist_api_config()
        elif data == b"api_protection_no":
            protection_enabled = api_config["enable_protection"] = False
            await event.edit(f'<tg-emoji emoji-id="5368585403467048206">🪬</tg-emoji> {off_label}', parse_mode="html")
            persist_api_config()
        elif data.startswith(b"api_prot_mode_"):
            chosen = data[len(b"api_prot_mode_"):].decode()
            mode = api_config.get("mcub_mode", "safe") if chosen == "default" else chosen
            if chosen != "default":
                api_config["mcub_mode"] = mode
            protection_enabled = api_config["enable_protection"] = True
            _apply_mcub_mode(mode)
            if _mcub_available:
                try:
                    client.clear_blocked_request_handler()
                except Exception:
                    pass
                client.on_blocked_request(_mcub_violation_handler)
            persist_api_config()
            label = (f'<tg-emoji emoji-id="5368585403467048206">🪬</tg-emoji> {on_label} . '
                     f'{mode_set_tpl.format(mode=mode, dry="")}')
            await event.edit(label, parse_mode="html")

    kernel.register_callback_handler(b"api_protection_", api_protection_callback_handler)
    kernel.register_callback_handler(b"api_prot_mode_", api_protection_callback_handler)
