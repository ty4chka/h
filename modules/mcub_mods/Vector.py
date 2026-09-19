# ‼️‼️‼️‼️ THE MODULE IS A PORT WITH HEROKU ‼️‼️‼️‼️
# ====================================================================================================================
# Repo MCUB - https://github.com/hairpin01/repo-MCUB-fork
# MCUB - https://github.com/hairpin01/MCUB-fork
# ====================================================================================================================
#   ██████╗  ██████╗ ██╗   ██╗███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗██╗     ███████╗███████╗
#  ██╔════╝ ██╔═══██╗╚██╗ ██╔╝████╗ ████║██╔═══██╗██╔══██╗██║   ██║██║     ██╔════╝██╔════╝
#  ██║  ███╗██║   ██║ ╚████╔╝ ██╔████╔██║██║   ██║██║  ██║██║   ██║██║     █████╗  ███████╗
#  ██║   ██║██║   ██║  ╚██╔╝  ██║╚██╔╝██║██║   ██║██║  ██║██║   ██║██║     ██╔══╝  ╚════██║
#  ╚██████╔╝╚██████╔╝   ██║   ██║ ╚═╝ ██║╚██████╔╝██████╔╝╚██████╔╝███████╗███████╗███████║
#   ╚═════╝  ╚═════╝    ╚═╝   ╚═╝     ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝╚══════╝╚══════╝
#
#   OFFICIAL USERNAMES: @goymodules | @samsepi0l_ovf
#   MODULE: Vector (PORT FOR MCUB @Hairpin00)
#
#   THIS MODULE IS LICENSED UNDER GNU AGPLv3, PROTECTED AGAINST UNAUTHORIZED COPYING/RESALE,
#   AND ITS ORIGINAL AUTHORSHIP BELONGS TO @samsepi0l_ovf.
#   ALL OFFICIAL UPDATES, RELEASE NOTES, AND PATCHES ARE PUBLISHED IN THE TELEGRAM CHANNEL @goymodules.
# ====================================================================================================================
# scop: inline

from __future__ import annotations
import asyncio, base64, hashlib, hmac, json, logging, re, time, unicodedata
from contextlib import suppress
from typing import Any
from urllib.parse import quote, urljoin

import aiohttp
from telethon import Button, events
from telethon.tl.functions.contacts import UnblockRequest
from core.lib.loader.module_base import ModuleBase, callback, command, inline, watcher
from core.lib.loader.module_config import Boolean, ConfigValue, Integer, ModuleConfig

LOG = logging.getLogger("VectorMonolith")
LOG.setLevel(logging.DEBUG)

API_BASE = "https://www.0xvector.lol"
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
AUTH_SECRET = "vektor_heroku_searchmodulesModbySepiol026-wqGithub"
FALLBACK_BANNER = "https://raw.githubusercontent.com/sepiol026-wq/GoyModules/refs/heads/main/assets/vec404.png"
LOADING_BANNER = "https://raw.githubusercontent.com/sepiol026-wq/GoyModules/refs/heads/main/assets/vsearch.png"
LANG_PING = "#v_lang_ping"
LANG_PONG = "#v_lang:"
BAN_REASON_RE = re.compile(
    r"(?:Пpичинa|Reason|理由|Grund|R3450n|Weason|Charge):\s*(.+)", re.IGNORECASE
)
BAN_TERM_RE = re.compile(r"(?:Cpoк|Term|期間|Dauer|73rm|Tewm):\s*(.+)", re.IGNORECASE)


class WebpageMediaEmptyError(Exception):
    pass


def _esc(text: str) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


class _ILog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class Vector(ModuleBase):
    name = "Vector"
    version = "2.4.1"
    author = "@samsepi0l_ovf"
    description = {
        "en": "Vector module registry browser.\nhttps://www.0xvector.lol",
        "ru": "Бpayзep peecтpa мoдyлeй Vector.\nhttps://www.0xvector.lol",
    }
    dependencies = ["aiohttp"]
    banner_url = "https://raw.githubusercontent.com/sepiol026-wq/GoyModules/refs/heads/main/assets/vector.png"

    config = ModuleConfig(
        ConfigValue(
            "limit",
            30,
            description="Search output limits.",
            validator=Integer(min=1, max=100),
        ),
        ConfigValue(
            "max_batch",
            50,
            description="Max modules per batch install.",
            validator=Integer(min=1, max=100),
        ),
        ConfigValue(
            "VectorInstall",
            True,
            description="Enable Vector Install",
            validator=Boolean(default=True),
        ),
    )

    strings: dict[str, dict[str, str]] = {
        "en": {
            "lang": "en",
            "name": "Vector",
            "v_dev_lbl": "Author:",
            "v_dev_str": "Dev:",
            "v_dev_ofc": "official",
            "v_dev_unofc": "unofficial",
            "v_info": "Info:",
            "v_cmds": "Usage:",
            "v_deps": "Dependencies:",
            "v_reqs": "Libs:",
            "v_hid_cmd": "+ {rem} hidden cmds.",
            "v_hid_req": "+ {rem} hidden libs.",
            "v_res_hdr": "Found Items:",
            "v_err_empty": "Specify query: {p}vector <text>",
            "v_err_404": "No records for: {q}",
            "v_err_len": "Query length is limited to 120 chars.",
            "v_err_api": "Access denied by Vector Server.",
            "v_ban_notice": "⛔ <b>Vector access blocked.</b>\n<b>Reason:</b> <code>{reason}</code>\n<b>Term:</b> <code>{term}</code>",
            "v_fb_add": "Rated successfully!",
            "v_fb_rm": "Rating cleared!",
            "v_btn_copy": "Query",
            "v_btn_dl": "Install",
            "v_page": "[{idx}/{total}]",
            "v_btn_code": "Source",
            "v_dl_ok": "Module installed successfully!",
            "v_dl_err": "Installation failed!",
            "v_lim_cfg": "Search output limits.",
            "v_max_batch_cfg": "Max modules per batch install.",
            "v_btn_sec": "🛡 Security Scan",
            "v_aud_hdr": "Code Audit: {name}",
            "v_aud_req": "Connecting to Security API...",
            "v_aud_proc": "Processing AST tree...",
            "v_btn_aud_run": "Start Scan",
            "v_aud_mem": "Loaded from session cache.",
            "v_aud_lvl": "Threat Level",
            "v_aud_stat": "Scanner Data",
            "v_aud_out": "Summary",
            "v_aud_sigs": "Triggers",
            "v_sig_crit": "Critical",
            "v_sig_warn": "Warnings",
            "v_sig_info": "Notices",
            "v_aud_none": "Not scanned yet. Takes 1 API slot.",
            "v_aud_no_txt": "No summary generated.",
            "v_aud_left": "Slots left: {remaining}/{limit}",
            "v_aud_zero": "Daily audit limit depleted.",
            "v_aud_err": "Scanner server is down.",
            "v_err_gui": "Interface rendering error.",
            "v_btn_exp": "🔽 Expand",
            "v_btn_col": "🔼 Collapse",
            "v_btn_talk": "💬 Discussion",
            "v_talk_hdr": "{emoji} <b>Thread: {name}</b>",
            "v_talk_desc": "Community reviews",
            "v_talk_num": "Posts: {count}",
            "v_talk_0": "Thread is empty. Be the first!",
            "v_talk_err": "Could not connect to thread.",
            "v_rep_ok": "Posted!",
            "v_rep_err": "Request failed.",
            "v_btn_bck": "⬅️ Back",
            "v_btn_wrt": "✍️ Post Reply",
            "v_rep_ask": "Reply to post message.\n2-1800 chars.",
            "v_rep_snt": "Uploading...",
            "v_rep_min": "Text is too short.",
            "v_rep_max": "Limit exceeded.",
            "v_rep_cncl": "Cancelled.",
            "v_loading_ui": "Searching Vector database...",
            "v_sending": "Loading...",
            "v_more_replies": "...and {count} more replies on the site.",
            "v_more_comments": "...and more comments on the site.",
            "v_upd_req": "Updating Vector...",
            "v_upd_ok": "Vector updated successfully!",
            "v_upd_err": "Update failed!",
            "v_upd_check": "Checking hashes\u2026",
            "v_install_log_hdr": "Install log: {name}",
            "v_install_fail_forbidden": "Forbidden method: <code>{detail}</code>",
            "v_install_fail_requirements": "Pip deps failed: <code>{detail}</code>",
            "v_install_fail_dependency": "Missing dependency: <code>{detail}</code>",
            "v_install_fail_packages": "System pkgs failed: <code>{detail}</code>",
            "v_install_fail_core_overwrite": "Tried to overwrite core <code>{detail}</code>",
            "v_install_fail_ffmpeg": "Requires ffmpeg (not installed)",
            "v_install_fail_inline": "Requires inline mode (unavailable)",
            "v_install_fail_heroku_min": "Needs Heroku \u2265 <code>{detail}</code>",
            "v_install_fail_not_found": "Not found in configured repos",
            "v_install_fail_download": "Failed to download module",
            "v_install_fail_unknown": "Unknown error: <code>{detail}</code>",
            "v_upd_same": "<b>You are on the latest version. Update anyway?</b>",
            "v_upd_force_btn": "\U0001f9ed Update",
            "v_dlcoll_hdr": "<b>Collection {name}</b>",
            "v_dlcoll_count": "{count} modules",
            "v_dlcoll_start": "<b>Installing all modules from collection...</b>",
            "v_dlcoll_done": "<b>All modules from collection installed</b>",
            "v_dlcoll_done_partial": "<b>Some modules failed to install</b>",
            "v_dlcoll_done_none": "<b>No modules were installed</b>",
            "v_dlcoll_fail_item": "\u274c {name}: {reason}",
            "v_dlcoll_empty": "<b>Collection is empty</b>",
            "v_dlcoll_not_found": "<b>Collection not found</b>",
            "v_vecdl_usage": "<b>Specify collection: </b><code>{p}vecdl <slug or URL></code>",
            "v_dlcoll_max_batch": "Collection has {total} modules, max {max} per batch",
        },
        "ru": {
            "lang": "ru",
            "name": "Vector",
            "v_dev_lbl": "Aвтop:",
            "v_dev_str": "Dev:",
            "v_dev_ofc": "oфициaльный",
            "v_dev_unofc": "нeoфициaльный",
            "v_info": "Инфo:",
            "v_cmds": "Иcпoльзoвaниe:",
            "v_deps": "Зaвиcимocти:",
            "v_reqs": "Библиoтeки:",
            "v_hid_cmd": "+ {rem} cкpытыx кoмaнд.",
            "v_hid_req": "+ {rem} cкpытыx библиoтeк.",
            "v_res_hdr": "Haйдeнo:",
            "v_err_empty": "Укaжитe зaпpoc: {p}vector <тeкcт>",
            "v_err_404": "Hичeгo нe нaйдeнo для: {q}",
            "v_err_len": "Длинa зaпpoca oгpaничeнa 120 cимвoлaми.",
            "v_err_api": "Дocтyп зaпpeщён cepвepoм Vector.",
            "v_ban_notice": "⛔ <b>Дocтyп к Vector зaблoкиpoвaн.</b>\n<b>Пpичинa:</b> <code>{reason}</code>\n<b>Cpoк:</b> <code>{term}</code>",
            "v_fb_add": "Oцeнкa yчтeнa!",
            "v_fb_rm": "Oцeнкa yдaлeнa!",
            "v_btn_copy": "Зaпpoc",
            "v_btn_dl": "Уcтaнoвить",
            "v_page": "[{idx}/{total}]",
            "v_btn_code": "Иcxoдник",
            "v_dl_ok": "Moдyль ycпeшнo ycтaнoвлeн!",
            "v_dl_err": "Уcтaнoвкa нe yдaлacь!",
            "v_lim_cfg": "Лимит вывoдa пoиcкa.",
            "v_max_batch_cfg": "Maкc. мoдyлeй зa бaтч.",
            "v_btn_sec": "🛡 Cкaниpoвaть",
            "v_aud_hdr": "Ayдит кoдa: {name}",
            "v_aud_req": "Пoдключeниe к Security API...",
            "v_aud_proc": "Oбpaбoткa AST...",
            "v_btn_aud_run": "Haчaть cкaниpoвaниe",
            "v_aud_mem": "Зaгpyжeнo из кэшa ceccии.",
            "v_aud_lvl": "Уpoвeнь yгpoзы",
            "v_aud_stat": "Дaнныe cкaнepa",
            "v_aud_out": "Cвoдкa",
            "v_aud_sigs": "Тpиггepы",
            "v_sig_crit": "Кpитичнo",
            "v_sig_warn": "Пpeдyпpeждeния",
            "v_sig_info": "Увeдoмлeния",
            "v_aud_none": "Eщё нe пpoвepeн. Pacxoдyeт 1 cлoт API.",
            "v_aud_no_txt": "Oпиcaниe нe cгeнepиpoвaнo.",
            "v_aud_left": "Ocтaлocь cлoтoв: {remaining}/{limit}",
            "v_aud_zero": "Днeвнoй лимит пpoвepoк иcчepпaн.",
            "v_aud_err": "Cepвep cкaниpoвaния нeдocтyпeн.",
            "v_err_gui": "Oшибкa peндepингa интepфeйca.",
            "v_btn_exp": "🔽 Paзвepнyть",
            "v_btn_col": "🔼 Cвepнyть",
            "v_btn_talk": "💬 Oбcyждeниe",
            "v_talk_hdr": "{emoji} <b>Тpeд: {name}</b>",
            "v_talk_desc": "Oтзывы cooбщecтвa",
            "v_talk_num": "Пocтoв: {count}",
            "v_talk_0": "Тpeд пycт. Бyдьтe пepвым!",
            "v_talk_err": "Heт cвязи c тpeдoм.",
            "v_rep_ok": "Oпyбликoвaнo!",
            "v_rep_err": "Oшибкa зaпpoca.",
            "v_btn_bck": "⬅️ Haзaд",
            "v_btn_wrt": "✍️ Oтвeтить",
            "v_rep_ask": "Oтпpaвьтe тeкcт oтвeтoм.\n2-1800 cимвoлoв.",
            "v_rep_snt": "Выгpyзкa...",
            "v_rep_min": "Cлишкoм кopoткo.",
            "v_rep_max": "Лимит пpeвышeн.",
            "v_rep_cncl": "Oтмeнeнo.",
            "v_loading_ui": "Ищeм в бaзe Vector...",
            "v_sending": "Зaгpyзкa...",
            "v_more_replies": "...и eщё {count} oтвeтoв нa caйтe.",
            "v_more_comments": "...и eщё кoммeнтapии нa caйтe.",
            "v_upd_req": "Oбнoвляeм Vector...",
            "v_upd_ok": "Vector ycпeшнo oбнoвлён!",
            "v_upd_err": "Oшибкa oбнoвлeния!",
            "v_upd_check": "Пpoвepкa xeшeй\u2026",
            "v_install_log_hdr": "Жypнaл ycтaнoвки: {name}",
            "v_install_fail_forbidden": "Зaпpeщённый мeтoд: <code>{detail}</code>",
            "v_install_fail_requirements": "Pip-зaвиcимocти нe вcтaли: <code>{detail}</code>",
            "v_install_fail_dependency": "He xвaтaeт зaвиcимocти: <code>{detail}</code>",
            "v_install_fail_packages": "Cиcтeмныe пaкeты нe вcтaли: <code>{detail}</code>",
            "v_install_fail_core_overwrite": "Пытaeтcя пepeзaпиcaть ядpo <code>{detail}</code>",
            "v_install_fail_ffmpeg": "Тpeбyeтcя ffmpeg (нe ycтaнoвлeн)",
            "v_install_fail_inline": "Тpeбyeтcя inline-peжим (нeдocтyпeн)",
            "v_install_fail_heroku_min": "Hyжeн Heroku \u2265 <code>{detail}</code>",
            "v_install_fail_not_found": "He нaйдeн в пoдключённыx peпoзитopияx",
            "v_install_fail_download": "He yдaлocь зaгpyзить мoдyль",
            "v_install_fail_unknown": "Heизвecтнaя oшибкa: <code>{detail}</code>",
            "v_upd_same": "<b>У тeбя пocлeдняя вepcия. Oбнoвитьcя пpинyдитeльнo?</b>",
            "v_upd_force_btn": "\U0001f9ed Oбнoвитьcя",
            "v_dlcoll_hdr": "<b>Кoллeкция {name}</b>",
            "v_dlcoll_count": "Moдyлeй: {count}",
            "v_dlcoll_start": "<b>Уcтaнoвкa вcex мoдyлeй из кoллeкции...</b>",
            "v_dlcoll_done": "<b>Вce мoдyли из кoллeкции ycтaнoвлeны</b>",
            "v_dlcoll_done_partial": "<b>Heкoтopыe мoдyли нe ycтaнoвилиcь</b>",
            "v_dlcoll_done_none": "<b>Hи oдин мoдyль нe был ycтaнoвлeн</b>",
            "v_dlcoll_fail_item": "\u274c {name}: {reason}",
            "v_dlcoll_empty": "<b>Кoллeкция пycтa</b>",
            "v_dlcoll_not_found": "<b>Кoллeкция нe нaйдeнa</b>",
            "v_vecdl_usage": "<b>Укaжитe кoллeкцию: </b><code>{p}vecdl <slug или URL></code>",
            "v_dlcoll_max_batch": "Кoллeкция coдepжит {total} мoдyлeй, мaкc. {max} зa paз",
        },
        "uk": {
            "lang": "uk",
            "name": "Vector",
            "v_dev_lbl": "Aвтop:",
            "v_dev_str": "Dev:",
            "v_dev_ofc": "oфiцiйний",
            "v_dev_unofc": "нeoфiцiйний",
            "v_info": "Iнфo:",
            "v_cmds": "Викopиcтaння:",
            "v_deps": "Зaлeжнocтi:",
            "v_reqs": "Бiблioтeки:",
            "v_hid_cmd": "+ {rem} пpиxoвaниx кoмaнд.",
            "v_hid_req": "+ {rem} пpиxoвaниx бiблioтeк.",
            "v_res_hdr": "Знaйдeнo:",
            "v_err_empty": "Вкaжiть зaпит: {p}vector <тeкcт>",
            "v_err_404": "Hiчoгo нe знaйдeнo для: {q}",
            "v_err_len": "Дoвжинa зaпитy oбмeжeнa 120 cимвoлaми.",
            "v_err_api": "Дocтyп зaбopoнeнo cepвepoм Vector.",
            "v_ban_notice": "⛔ <b>Дocтyп дo Vector зaблoкoвaнo.</b>\n<b>Пpичинa:</b> <code>{reason}</code>\n<b>Тepмiн:</b> <code>{term}</code>",
            "v_fb_add": "Oцiнкy вpaxoвaнo!",
            "v_fb_rm": "Oцiнкy видaлeнo!",
            "v_btn_copy": "Зaпит",
            "v_btn_dl": "Вcтaнoвити",
            "v_page": "[{idx}/{total}]",
            "v_btn_code": "Виxiдник",
            "v_dl_ok": "Moдyль ycпiшнo вcтaнoвлeнo!",
            "v_dl_err": "Пoмилкa вcтaнoвлeння!",
            "v_lim_cfg": "Лiмiт вивeдeння пoшyкy.",
            "v_max_batch_cfg": "Maкc. мoдyлiв зa бaтч.",
            "v_btn_sec": "🛡 Cкaнyвaти",
            "v_aud_hdr": "Ayдит кoдy: {name}",
            "v_aud_req": "Пiдключeння дo Security API...",
            "v_aud_proc": "Oбpoбкa AST...",
            "v_btn_aud_run": "Пoчaти cкaнyвaння",
            "v_aud_mem": "Зaвaнтaжeнo з кeшy ceciї.",
            "v_aud_lvl": "Piвeнь зaгpoзи",
            "v_aud_stat": "Дaнi cкaнepa",
            "v_aud_out": "Пiдcyмoк",
            "v_aud_sigs": "Тpигepи",
            "v_sig_crit": "Кpитичнo",
            "v_sig_warn": "Увaгa",
            "v_sig_info": "Cпoвiщeння",
            "v_aud_none": "Щe нe пepeвipeнo. Витpaчaє 1 cлoт API.",
            "v_aud_no_txt": "Oпиc нe згeнepoвaнo.",
            "v_aud_left": "Зaлишoк cлoтiв: {remaining}/{limit}",
            "v_aud_zero": "Дoбoвий лiмiт пepeвipoк вичepпaнo.",
            "v_aud_err": "Cepвep cкaнyвaння нeдocтyпний.",
            "v_err_gui": "Збiй peндepингy iнтepфeйcy.",
            "v_btn_exp": "🔽 Poзгopнyти",
            "v_btn_col": "🔼 Згopнyти",
            "v_btn_talk": "💬 Oбгoвopeння",
            "v_talk_hdr": "{emoji} <b>Тpeд: {name}</b>",
            "v_talk_desc": "Вiдгyки cпiльнoти",
            "v_talk_num": "Пocтiв: {count}",
            "v_talk_0": "Тpeд пopoжнiй. Бyдьтe пepшим!",
            "v_talk_err": "Heмaє зв'язкy з тpeдoм.",
            "v_rep_ok": "Oпyблiкoвaнo!",
            "v_rep_err": "Збiй зaпитy.",
            "v_btn_bck": "⬅️ Haзaд",
            "v_btn_wrt": "✍️ Haпиcaти",
            "v_rep_ask": "Вiдпpaвтe тeкcт вiдпoвiддю.\n2-1800 cимвoлiв.",
            "v_rep_snt": "Вивaнтaжeння...",
            "v_rep_min": "Тeкcт зaнaдтo кopoткий.",
            "v_rep_max": "Пepeвищeнo лiмiт дoвжини.",
            "v_rep_cncl": "Cкacoвaнo.",
            "v_loading_ui": "Шyкaємo пo бaзi Vector...",
            "v_sending": "Зaвaнтaжeння...",
            "v_more_replies": "...i щe {count} вiдпoвiдeй нa caйтi.",
            "v_more_comments": "...i щe кoмeнтapi нa caйтi.",
            "v_upd_req": "Oнoвлюємo Vector...",
            "v_upd_ok": "Vector ycпiшнo oнoвлeнo!",
            "v_upd_err": "Пoмилкa oнoвлeння!",
            "v_upd_check": "Пepeвipкa xeшiв\u2026",
            "v_install_log_hdr": "Жypнaл вcтaнoвлeння: {name}",
            "v_install_fail_forbidden": "Зaбopoнeний мeтoд: <code>{detail}</code>",
            "v_install_fail_requirements": "Pip-зaлeжнocтi нe cтaли: <code>{detail}</code>",
            "v_install_fail_dependency": "Бpaкyє зaлeжнocтi: <code>{detail}</code>",
            "v_install_fail_packages": "Cиcтeмнi пaкyнки нe cтaли: <code>{detail}</code>",
            "v_install_fail_core_overwrite": "Haмaгaєтьcя пepeзaпиcaти ядpo <code>{detail}</code>",
            "v_install_fail_ffmpeg": "Пoтpiбeн ffmpeg (нe вcтaнoвлeнo)",
            "v_install_fail_inline": "Пoтpiбeн inline-peжим (нeдocтyпний)",
            "v_install_fail_heroku_min": "Пoтpiбeн Heroku \u2265 <code>{detail}</code>",
            "v_install_fail_not_found": "He знaйдeнo в пiдключeниx peпoзитopiяx",
            "v_install_fail_download": "He вдaлocя зaвaнтaжити мoдyль",
            "v_install_fail_unknown": "Heвiдoмa пoмилкa: <code>{detail}</code>",
            "v_upd_same": "<b>У тeбe ocтaння вepciя. Oнoвитиcя пpимycoвo?</b>",
            "v_upd_force_btn": "\U0001f9ed Oнoвитиcя",
            "v_dlcoll_hdr": "<b>Кoлeкцiя {name}</b>",
            "v_dlcoll_count": "Moдyлiв: {count}",
            "v_dlcoll_start": "<b>Вcтaнoвлeння вcix мoдyлiв iз кoлeкцiї...</b>",
            "v_dlcoll_done": "<b>Вci мoдyлi з кoлeкцiї вcтaнoвлeнo</b>",
            "v_dlcoll_done_partial": "<b>Дeякi мoдyлi нe вcтaнoвилиcя</b>",
            "v_dlcoll_done_none": "<b>Жoдeн мoдyль нe вcтaнoвлeнo</b>",
            "v_dlcoll_fail_item": "\u274c {name}: {reason}",
            "v_dlcoll_empty": "<b>Кoлeкцiя пopoжня</b>",
            "v_dlcoll_not_found": "<b>Кoлeкцiю нe знaйдeнo</b>",
            "v_vecdl_usage": "<b>Вкaжiть кoлeкцiю: </b><code>{p}vecdl <slug aбo URL></code>",
            "v_dlcoll_max_batch": "Кoлeкцiя мicтить {total} мoдyлiв, мaкc. {max} зa paз",
        },
    }

    ICONS: dict[str, str] = {
        "search": '<tg-emoji emoji-id="5447459604524971717">\U0001f50e</tg-emoji>',
        "error": '<tg-emoji emoji-id="5388785832956016892">\u274c</tg-emoji>',
        "warn": '<tg-emoji emoji-id="5881702736843511327">\u26a0\ufe0f</tg-emoji>',
        "description": '<tg-emoji emoji-id="6008090211181923982">\U0001f4dd</tg-emoji>',
        "command": '<tg-emoji emoji-id="5877260593903177342">\u2699</tg-emoji>',
        "dependency": '<tg-emoji emoji-id="5325732612084351248">\U0001f4e6</tg-emoji>',
        "module": '<tg-emoji emoji-id="5924720918826848520">\U0001f4e6</tg-emoji>',
        "modules_list": '<tg-emoji emoji-id="5883973610606956186">\U0001f5c2</tg-emoji>',
        "shield": '<tg-emoji emoji-id="5926783847453692661">\U0001f6e1</tg-emoji>',
        "safe": '<tg-emoji emoji-id="5776375003280838798">\u2705</tg-emoji>',
        "stats": '<tg-emoji emoji-id="5877485980901971030">\U0001f4ca</tg-emoji>',
        "quota": '<tg-emoji emoji-id="6311858554944888333">\u231a\ufe0f</tg-emoji>',
        "verified": '<tg-emoji emoji-id="5958376256788502078">\u2b50\ufe0f</tg-emoji>',
        "comments": '<tg-emoji emoji-id="5886666250158870040">\U0001f4ac</tg-emoji>',
        "reply": "\U000021b3",
        "broken": '<tg-emoji emoji-id="5877260593903177342">\U0001f4a5</tg-emoji>',
        "loading": '<tg-emoji emoji-id="5447459604524971717">\U0001f50e</tg-emoji>',
        "success": '<tg-emoji emoji-id="5776375003280838798">\u2705</tg-emoji>',
        "info": '<tg-emoji emoji-id="6008090211181923982">\U0001f4dd</tg-emoji>',
        "none": '<tg-emoji emoji-id="5388785832956016892">\u274c</tg-emoji>',
        "scanning": '<tg-emoji emoji-id="5926783847453692661">\U0001f6e1</tg-emoji>',
        "scan_ok": '<tg-emoji emoji-id="5776375003280838798">\u2705</tg-emoji>',
        "scan_err": '<tg-emoji emoji-id="5388785832956016892">\u274c</tg-emoji>',
    }

    _ierrs: list[tuple[str, re.Pattern]] = [
        ("forbidden", re.compile(r"forbidden method\s+(\S+)")),
        ("requirements", re.compile(r"pip dependencies\s+(\S+)")),
        ("dependency", re.compile(r"missing dependency\s+(\S+)")),
        ("packages", re.compile(r"system packages\s+(\S+)")),
        ("core_overwrite", re.compile(r"tried to overwrite core\s+(\S+)\s+(\S+)")),
        ("ffmpeg", re.compile(r"requires ffmpeg")),
        ("inline", re.compile(r"requires inline mode")),
        (
            "heroku_min",
            re.compile(r"requires Heroku\s+(\S+),\s*current version is\s+(\S+)"),
        ),
        ("not_found", re.compile(r"was not found in configured repos")),
        ("download", re.compile(r"Failed to download module")),
    ]

    _http: aiohttp.ClientSession | None = None
    _http_lock: Any = None  # filled in on_load
    _ban_check_done: bool = False
    _cached_groups: dict[str, list[dict[str, Any]]] = {}
    bannote: str | None = None
    btid: int = 0
    httpc: int = 0

    async def on_load(self) -> None:
        LOG.info("Vector loaded")
        self._http_lock = asyncio.Lock()
        self._http = aiohttp.ClientSession(
            headers={"User-Agent": "Vector/MCUB/2.3.9"},
            timeout=aiohttp.ClientTimeout(total=30),
        )

        defaults = {
            "limit": 30,
            "max_batch": 50,
            "VectorInstall": True,
        }
        config_dict = await self.kernel.get_module_config(self.name, defaults)
        self.config.from_dict(config_dict)
        self.kernel.store_module_config_schema(self.name, self.config)
        await self.kernel.save_module_config(self.name, self.config.to_dict())

        asyncio.ensure_future(self._check_ban())

    async def on_unload(self) -> None:
        LOG.info("Vector unloading")
        if self._http and not self._http.closed:
            await self._http.close()

    async def _ensure_http(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            async with self._http_lock:
                if self._http is None or self._http.closed:
                    self._http = aiohttp.ClientSession(
                        headers={"User-Agent": "Vector/MCUB/2.3.9"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    )
        return self._http

    async def _net_req(
        self,
        method: str,
        path: str,
        token: str | None = None,
        json_data: dict | None = None,
        params: dict | None = None,
        as_bytes: bool = False,
    ) -> Any:
        url = urljoin(API_BASE, path.lstrip("/"))
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            http = await self._ensure_http()
            async with http.request(
                method, url, headers=headers, json=json_data, params=params
            ) as resp:
                self.httpc = resp.status
                if resp.status == 204:
                    return {"ok": True}
                if resp.status >= 400:
                    LOG.warning("_net_req: HTTP %d for %s %s", resp.status, method, url)
                    return None
                if as_bytes:
                    return await resp.read()
                ct = resp.headers.get("Content-Type", "")
                if "application/json" in ct:
                    return await resp.json()
                text = await resp.text()
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, ValueError):
                    return {"ok": True, "raw": text}
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            LOG.warning("_net_req: request failed: %r", e)
            return None

    async def _fetch_banner(self, url: str | None) -> bytes | None:
        if not url:
            return None
        try:
            http = await self._ensure_http()
            async with http.get(url) as resp:
                return await resp.read() if resp.status == 200 else None
        except Exception as e:
            LOG.debug("_fetch_banner: failed for %s: %r", url, e)
        return None

    async def _get_active_token(self, force: bool = False) -> str | None:
        LOG.debug("_get_active_token: force=%s", force)
        if force:
            await self.db.db_delete(self.name, "auth_token")
            LOG.debug("_get_active_token: auth_token cleared (force)")

        cached = await self.db.db_get(self.name, "auth_token")
        if cached:
            try:
                payload = self._parse_jwt(cached)
                if payload.get("exp", 0) - time.time() > 60:
                    LOG.debug(
                        "_get_active_token: cached token valid, exp=%s",
                        payload.get("exp"),
                    )
                    return cached
                LOG.debug("_get_active_token: cached token expired or expiring")
            except Exception:
                cached = None

        LOG.info("_get_active_token: requesting fresh token")
        bot_info = await self._net_req("GET", "/api/tg-bot")
        bot_username = (bot_info or {}).get("username", "").strip().lstrip("@")
        if not bot_username:
            LOG.warning("No bot username returned from /api/tg-bot")
            return None

        me = await self.client.get_me()
        uid = str(getattr(me, "id", ""))
        uname = getattr(me, "username", "") or ""
        fname = getattr(me, "first_name", "") or ""
        lname = getattr(me, "last_name", "") or ""
        dname = " ".join(filter(None, [fname, lname])).strip() or uname or uid

        uname = self._norm_hash_name(uname).lower()
        dname = self._norm_hash_name(dname)

        with suppress(Exception):
            await self.client(UnblockRequest(bot_username))

        new_jwt = ""
        ban_notice = ""
        for attempt in range(2):
            b_stamp = int(time.time() // 10) - attempt
            cmd_hash = hashlib.sha256(
                f"vector-token-v2|{uid}|{b_stamp}|{AUTH_SECRET}".encode()
            ).hexdigest()[:32]
            cmd_str = f"/{cmd_hash}"

            try:
                async with self.client.conversation(
                    bot_username, timeout=12, exclusive=False
                ) as conv:
                    out_msg = await conv.send_message(cmd_str)
                    try:
                        resp = await asyncio.wait_for(conv.get_response(), timeout=10)
                        txt = getattr(resp, "raw_text", getattr(resp, "text", ""))
                        match = JWT_RE.search(txt)
                        if match:
                            new_jwt = match.group(0)
                        elif "зaблoк" in txt.lower() or "\u26db" in txt:
                            ban_notice = self._format_ban_notice(txt)
                        with suppress(Exception):
                            await out_msg.delete()
                        if new_jwt:
                            break
                    except asyncio.TimeoutError:
                        with suppress(Exception):
                            await out_msg.delete()
            except Exception as e:
                LOG.warning("Token conversation attempt=%s failed: %r", attempt, e)

        if new_jwt:
            await self.db.db_set(self.name, "auth_token", new_jwt)
            self.bannote = None
            LOG.info("_get_active_token: new token obtained")
        elif ban_notice:
            self.bannote = ban_notice
            LOG.warning("_get_active_token: user banned")
        else:
            LOG.warning("_get_active_token: no token obtained")
        return new_jwt or None

    def _format_ban_notice(self, raw_text: str) -> str:
        LOG.debug("_format_ban_notice: raw_len=%d", len(raw_text) if raw_text else 0)
        txt = str(raw_text or "").strip()
        reason_match = BAN_REASON_RE.search(txt)
        term_match = BAN_TERM_RE.search(txt)

        reason_raw = reason_match.group(1).strip() if reason_match else ""
        term_raw = term_match.group(1).strip() if term_match else ""

        if not reason_raw or not term_raw:
            for line in txt.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key_l = key.strip().lower()
                val = value.strip()
                if not reason_raw and key_l in {
                    "пpичинa",
                    "reason",
                    "理由",
                    "grund",
                    "r3450n",
                    "weason",
                    "charge",
                }:
                    reason_raw = val
                if not term_raw and key_l in {
                    "cpoк",
                    "term",
                    "期間",
                    "dauer",
                    "73rm",
                    "tewm",
                }:
                    term_raw = val

        reason = _esc(reason_raw or "-")
        term = _esc(term_raw or "permanent")
        return self.strings("v_ban_notice", reason=reason, term=term)

    def _compute_hmac(self, payload: str) -> str:
        return hmac.new(
            AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _verify_hmac(self, payload: str, signature: str) -> bool:
        return hmac.compare_digest(self._compute_hmac(payload), signature)

    def _parse_jwt(self, token: str) -> dict:
        try:
            b64_part = token.split(".")[1]
            b64_part += "=" * (-len(b64_part) % 4)
            return json.loads(base64.urlsafe_b64decode(b64_part.encode()).decode())
        except Exception:
            return {}

    @staticmethod
    def _norm_hash_name(value: str) -> str:
        value = unicodedata.normalize("NFKC", str(value or ""))
        value = (
            value.replace("\u200b", "")
            .replace("\u200c", "")
            .replace("\u200d", "")
            .replace("\ufeff", "")
        )
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    def _detect_lang_suffix(self) -> str:
        variants = {"en", "ru", "jp", "uk", "de", "neofit", "tiktok", "leet", "uwu"}
        lang = str(self.strings.get("lang", "en")).strip().lower()
        return lang if lang in variants else "en"

    def _normalize_module(self, raw: dict) -> dict:
        LOG.debug("_normalize_module: name=%s", raw.get("name", "?"))
        lang = self._detect_lang_suffix()
        content_lang = (
            "ru"
            if lang in ("ru", "neofit", "tiktok", "leet", "uwu")
            else ("ua" if lang == "uk" else lang)
        )
        cmds = []
        for c in raw.get("commands") or []:
            if isinstance(c, dict):
                cmd_desc = (
                    c.get(f"desc_{content_lang}")
                    or c.get("description")
                    or c.get("desc")
                    or ""
                )
                cmds.append(
                    {
                        "name": c.get("name") or c.get("cmd") or "",
                        "description": cmd_desc,
                        "is_inline": bool(c.get("is_inline")),
                        "is_placeholder": bool(c.get("is_placeholder")),
                    }
                )
        dev = str(raw.get("developer") or raw.get("author") or "@Unknown")
        ioff = bool(
            raw.get("official")
            or raw.get("is_official")
            or raw.get("verified")
            or raw.get("is_verified")
            or raw.get("telegram_verified")
            or raw.get("official_developer")
            or raw.get("is_official_developer")
        )
        name = str(raw.get("name") or raw.get("class_name") or "Unknown")
        locales = raw.get("locales")
        desc = raw.get("description") or ""
        if isinstance(locales, dict):
            loc_key = f"description_{content_lang}"
            loc_val = locales.get(loc_key)
            if isinstance(loc_val, str) and loc_val.strip():
                desc = loc_val
        return {
            "name": name,
            "owner": raw.get("source_owner") or "unknown",
            "version": raw.get("version") or "?.?.?",
            "author": dev,
            "description": desc,
            "commands": cmds,
            "dependencies": [str(d) for d in (raw.get("dependencies") or [])],
            "official": ioff,
            "likes": int(raw.get("likes") or 0),
            "dislikes": int(raw.get("dislikes") or 0),
            "banner": raw.get("banner"),
            "source_url": raw.get("source_url")
            or f"{API_BASE}/modules/{quote(raw.get('source_owner', 'unknown'), safe='')}/{quote(name, safe='')}/source",
            "dl_url": raw.get("source_url")
            or f"{API_BASE}/modules/{quote(raw.get('source_owner', 'unknown'), safe='')}/{quote(name, safe='')}/source",
        }

    @staticmethod
    def _extract_counts(data: dict) -> tuple[int | None, int | None]:
        likes = dislikes = None
        for container in (
            data,
            data.get("module"),
            data.get("data"),
            data.get("result"),
            data.get("summary"),
        ):
            if not isinstance(container, dict):
                continue
            for lk in ("likes", "likes_count", "likesCount", "likeCount", "like_count"):
                v = container.get(lk)
                if v is not None:
                    try:
                        likes = int(v)
                    except (ValueError, TypeError):
                        pass
                    break
            for dk in (
                "dislikes",
                "dislikes_count",
                "dislikesCount",
                "dislikeCount",
                "dislike_count",
            ):
                v = container.get(dk)
                if v is not None:
                    try:
                        dislikes = int(v)
                    except (ValueError, TypeError):
                        pass
                    break
            if likes is not None and dislikes is not None:
                break
        return likes, dislikes

    async def _check_ban(self) -> None:
        if self._ban_check_done:
            return
        self._ban_check_done = True
        token = await self._get_active_token()
        if not token:
            return
        res = await self._net_req("GET", "/api/status", token=token)
        if res is None:
            return
        ban = res.get("ban") or res.get("banned") or res.get("is_banned")
        if ban:
            reason = ban.get("reason") or ""
            until = ban.get("until") or ""
            self.bannote = (
                f"\U0001f6ab Banned: {reason}" if reason else "\U0001f6ab Banned"
            )
            if until:
                self.bannote += f" until {until}"
            LOG.warning("_check_ban: %s", self.bannote)

    async def _safe_install(
        self, module_name: str, dl_url: str, notify: bool = True
    ) -> tuple[int, list[dict]]:
        LOG.info("_safe_install: %s from %s", module_name, dl_url)
        try:
            ihandler = _ILog()
            ihandler.setLevel(logging.WARNING)
            root = logging.getLogger()
            root.addHandler(ihandler)
            try:
                success, msg = await self.kernel.install_from_url(dl_url, module_name)
                LOG.info("_safe_install: success=%s msg=%s", success, msg)
                return (
                    (1, [])
                    if success
                    else (0, self._classify_install_errors(ihandler.records))
                )
            finally:
                root.removeHandler(ihandler)
        except Exception as e:
            LOG.error("_safe_install: exception: %r", e)
            return -1, []

    def _classify_install_errors(
        self, records: list[logging.LogRecord]
    ) -> list[dict[str, str]]:
        errors = []
        for rec in records:
            if rec.levelno < logging.WARNING:
                continue
            msg = rec.getMessage()
            for err_type, pattern in self._ierrs:
                m = pattern.search(msg)
                if m:
                    detail = m.group(1).strip() if m.lastindex else ""
                    if err_type == "core_overwrite":
                        detail = f"{m.group(1)}.{m.group(2)}"
                    elif err_type == "heroku_min":
                        detail = f"{m.group(1)} (current: {m.group(2)})"
                    errors.append({"type": err_type, "detail": detail, "raw": msg})
                    break
            else:
                if rec.levelno >= logging.ERROR:
                    errors.append({"type": "unknown", "detail": msg[:200], "raw": msg})
        return errors

    def _fmt_install_errors(self, m_name: str, errors: list[dict[str, str]]) -> str:
        if not errors:
            return f"{self.ICONS['error']} <b>{self.strings('v_dl_err')}</b>"
        lines = [
            f"{self.ICONS['broken']} <b>{self.strings('v_install_log_hdr', name=m_name)}</b>"
        ]
        seen = set()
        for err in errors:
            key = err["type"]
            if key in seen:
                continue
            seen.add(key)
            detail = err["detail"]
            fmt = self.strings.get(f"v_install_fail_{key}")
            if fmt:
                try:
                    lines.append(f"{self.ICONS['warn']} {fmt.format(detail=detail)}")
                except (KeyError, ValueError):
                    lines.append(f"{self.ICONS['warn']} {fmt}")
            else:
                lines.append(f"{self.ICONS['warn']} {key}: {detail}")
        return "\n".join(lines)

    def _build_html(self, item: dict, idx: int, total: int) -> str:
        name, author, version = (
            item.get("name", "?"),
            item.get("author", "?"),
            item.get("version", "?"),
        )
        description = item.get("description", "")
        commands, deps = item.get("commands", []), item.get("dependencies", [])
        official = item.get("official", False)

        parts = []

        # header block
        header = f"{self.ICONS['module']} <code>{_esc(name)}</code> by <code>{_esc(author)}</code>"
        if version and version != "?.?.?":
            header += f" (<code>v{_esc(version)}</code>)"

        status_text = (
            self.strings("v_dev_ofc") if official else self.strings("v_dev_unofc")
        )
        status_line = f"{self.ICONS['verified'] if official else self.ICONS['module']} dev {_esc(status_text)}"

        header_block = header + "\n" + status_line
        if total > 1:
            header_block += (
                "\n"
                + f"{self.ICONS['modules_list']} {self.strings('v_page', idx=idx, total=total)}"
            )
        parts.append(f"<blockquote expandable>{header_block}</blockquote>")

        # description block
        if description and description.strip():
            desc_text = _esc(description.strip()[:200])
            parts.append(
                f"<blockquote expandable>{self.ICONS['description']} info\n{desc_text}</blockquote>"
            )
        else:
            parts.append(
                f"<blockquote>{self.ICONS['description']} info\n\u2014</blockquote>"
            )

        # commands block
        if commands:
            cmd_lines = []
            visible_count = 0
            for c in commands[:15]:
                if isinstance(c, dict):
                    cn = c.get("name", "")
                    cd = (c.get("description", "") or "").split("\n")[0]
                    if c.get("is_placeholder"):
                        line = (
                            f"<code>{{{_esc(cn)}}}</code> {_esc(cd)}"
                            if cd
                            else f"<code>{{{_esc(cn)}}}</code>"
                        )
                    elif c.get("is_inline"):
                        line = (
                            f"<code>@bot {_esc(cn)}</code> {_esc(cd)}"
                            if cd
                            else f"<code>@bot {_esc(cn)}</code>"
                        )
                    else:
                        line = f".{_esc(cn)} {_esc(cd)}" if cd else f".{_esc(cn)}"
                    if not c.get("is_placeholder"):
                        visible_count += 1
                    cmd_lines.append(line)
                elif isinstance(c, str):
                    c2 = c.strip()
                    if c2 and not c2.startswith("+"):
                        cmd_lines.append(f".{_esc(c2)}")
                        visible_count += 1
            hidden = len(commands) - visible_count
            extra = (
                f"\n{self.strings('v_hid_cmd', rem=str(hidden))}" if hidden > 0 else ""
            )
            parts.append(
                f"<blockquote expandable>{self.ICONS['command']} usage\n{chr(10).join(cmd_lines)}{extra}</blockquote>"
            )
        else:
            parts.append(
                f"<blockquote>{self.ICONS['command']} usage\n\u2014</blockquote>"
            )

        # deps block
        if deps:
            dep_str = ", ".join(f"<code>{_esc(d)}</code>" for d in deps[:8])
            parts.append(
                f"<blockquote expandable>{self.ICONS['dependency']} deps:\n{dep_str}</blockquote>"
            )
        else:
            parts.append(
                f"<blockquote>{self.ICONS['dependency']} deps:\n\u2014</blockquote>"
            )

        return "\n".join(parts)

    def _cb_data(self, handler: str, **kwargs) -> dict:
        return {"h": handler, **kwargs}

    def _build_kbd(
        self,
        item: dict,
        i: int,
        group: list | None,
        q: str,
        expanded: bool = False,
        comments_pg: int = 0,
    ) -> list:
        name, owner = item.get("name", "?"), item.get("owner", "?")
        likes, dislikes = item.get("likes", 0), item.get("dislikes", 0)
        gl = len(group) if group else 1

        kbd = [
            [
                {"text": self.strings["v_btn_copy"], "copy": q},
                self.Button.inline(
                    self.strings["v_btn_dl"],
                    self.cb_install,
                    data=self._cb_data(
                        "install", owner=owner, name=name, i=i, gl=gl, q=q
                    ),
                ),
                Button.url(
                    self.strings["v_btn_code"], item.get("source_url", "") or ""
                ),
            ],
            [
                self.Button.inline(
                    f"\U0001f44d {likes}",
                    self.cb_rate,
                    data=self._cb_data(
                        "rate", action="like", owner=owner, name=name, i=i, gl=gl, q=q
                    ),
                ),
                self.Button.inline(
                    f"\U0001f44e {dislikes}",
                    self.cb_rate,
                    data=self._cb_data(
                        "rate",
                        action="dislike",
                        owner=owner,
                        name=name,
                        i=i,
                        gl=gl,
                        q=q,
                    ),
                ),
            ],
        ]

        if group and gl > 1:
            prev_i = (i - 1) % gl
            next_i = (i + 1) % gl
            kbd.append(
                [
                    self.Button.inline(
                        "\u25c0\ufe0f",
                        self.cb_nav,
                        data=self._cb_data("nav", i=prev_i, gl=gl, q=q),
                    ),
                    self.Button.inline(
                        f"\u2022{i + 1}/{gl}\u2022",
                        self.cb_list,
                        data=self._cb_data("list", i=i, gl=gl, q=q),
                    ),
                    self.Button.inline(
                        "\u25b6\ufe0f",
                        self.cb_nav,
                        data=self._cb_data("nav", i=next_i, gl=gl, q=q),
                    ),
                ]
            )

        kbd.append(
            [
                self.Button.inline(
                    self.strings["v_btn_col" if expanded else "v_btn_exp"],
                    self.cb_toggle,
                    data=self._cb_data(
                        "toggle", i=i, gl=gl, q=q, expanded=not expanded
                    ),
                ),
            ]
        )

        if expanded:
            kbd.append(
                [
                    self.Button.inline(
                        self.strings["v_btn_talk"],
                        self.cb_talk,
                        data=self._cb_data(
                            "talk", owner=owner, name=name, i=i, gl=gl, q=q
                        ),
                    ),
                    self.Button.inline(
                        self.strings["v_btn_sec"],
                        self.cb_sec_check,
                        data=self._cb_data(
                            "sec", owner=owner, name=name, i=i, gl=gl, q=q
                        ),
                    ),
                ]
            )

        return kbd

    def _build_discussion_html(
        self, data: dict | None, name: str, emoji: str = "\U0001f4ac"
    ) -> str:
        if not data:
            return f"{emoji} <b>{self.strings('v_talk_hdr', emoji=emoji, name=_esc(name))}</b>\n\n{self.strings('v_talk_err')}"
        posts = data.get("posts") or data.get("messages") or []
        if not posts:
            return f"{emoji} <b>{self.strings('v_talk_hdr', emoji=emoji, name=_esc(name))}</b>\n{self.strings('v_talk_desc')}\n\n{self.strings('v_talk_0')}"
        lines = [
            f"{emoji} <b>{self.strings('v_talk_hdr', emoji=emoji, name=_esc(name))}</b>",
            f"{self.strings('v_talk_desc')}",
            f"{self.strings('v_talk_num', count=len(posts))}",
            "",
        ]
        for p in posts[:20]:
            author = p.get("author") or p.get("user") or "?"
            text = p.get("text") or p.get("content") or "..."
            ts = p.get("timestamp") or p.get("date") or ""
            lines.append(f"<b>{_esc(str(author))}</b>: {_esc(str(text)[:200])}")
            if ts:
                lines.append(f"<i>{ts}</i>")
            lines.append("")
        if len(posts) > 20:
            lines.append(self.strings("v_more_comments"))
        return "\n".join(lines)

    def _build_discussion_kbd(
        self, owner: str, name: str, i: int, gl: int, q: str
    ) -> list:
        uid = self._norm_hash_name(f"{owner}|{name}")
        return [
            [
                Button.switch_inline(self.strings["v_btn_wrt"], query=f"vector {uid} "),
                self.Button.inline(
                    self.strings["v_btn_bck"],
                    self.cb_list,
                    data=self._cb_data("list", i=i, gl=gl, q=q),
                ),
            ]
        ]

    def _build_sec_html(self, item: dict, payload: dict | None) -> str:
        name = item.get("name", "?")
        if not payload:
            return f"{self.ICONS['shield']} <b>{_esc(name)}</b>\n\n{self.strings('v_aud_none')}"
        scan = payload.get("check") or payload
        details = scan.get("details", {})
        static = details.get("static", {})
        verdict = scan.get("verdict") or scan.get("threat_level") or "unknown"
        emoji_map = {
            "safe": self.ICONS["safe"],
            "unknown": self.ICONS["warn"],
            "malicious": self.ICONS["error"],
            "critical": self.ICONS["error"],
        }
        lines = [
            f"{emoji_map.get(verdict, self.ICONS['warn'])} <b>{self.strings('v_aud_lvl')}: {_esc(verdict.upper())}</b>"
        ]
        sigs = static.get("signatures") or scan.get("signatures") or []
        if sigs:
            crit = [s for s in sigs if s.get("severity") == "critical"]
            warn_s = [s for s in sigs if s.get("severity") == "warning"]
            info_s = [s for s in sigs if s.get("severity") == "info"]
            lines.append(f"\n{self.ICONS['shield']} {self.strings('v_aud_sigs')}:")
            if crit:
                lines.append(
                    f"  {self.ICONS['error']} {self.strings('v_sig_crit')}: {len(crit)}"
                )
                for s in crit[:3]:
                    lines.append(f"    \u2022 {s.get('name', s.get('rule', '?'))}")
            if warn_s:
                lines.append(
                    f"  {self.ICONS['warn']} {self.strings('v_sig_warn')}: {len(warn_s)}"
                )
                for s in warn_s[:3]:
                    lines.append(f"    \u2022 {s.get('name', s.get('rule', '?'))}")
            if info_s:
                lines.append(
                    f"  {self.ICONS['info']} {self.strings('v_sig_info')}: {len(info_s)}"
                )
        summary = scan.get("summary") or static.get("summary") or ""
        if summary:
            lines.append(
                f"\n{self.ICONS['info']} {self.strings('v_aud_out')}: {_esc(str(summary)[:300])}"
            )
        if not sigs and not summary:
            lines.append(f"\n{self.strings('v_aud_no_txt')}")
        return "\n".join(lines)

    def _build_sec_kbd(
        self, item: dict, i: int, group: list | None, q: str, has_run: bool
    ) -> list:
        name, owner = item.get("name", "?"), item.get("owner", "?")
        gl = len(group) if group else 1
        kbd = []
        if not has_run:
            kbd.append(
                [
                    self.Button.inline(
                        self.strings["v_btn_aud_run"],
                        self.cb_scan_go,
                        data=self._cb_data(
                            "scan_go", owner=owner, name=name, i=i, gl=gl, q=q
                        ),
                    )
                ]
            )
        kbd.append(
            [
                self.Button.inline(
                    self.strings["v_btn_bck"],
                    self.cb_list,
                    data=self._cb_data("list", i=i, gl=gl, q=q),
                )
            ]
        )
        return kbd

    async def _safe_edit(
        self,
        event: Any,
        text: str,
        buttons: list | None = None,
        banner_url: str | None = None,
    ) -> None:
        try:
            kw: dict[str, Any] = {}
            if buttons:
                kw["buttons"] = buttons
            if banner_url:
                kw["file"] = banner_url
            try:
                await event.edit(text, parse_mode="html", link_preview=False, **kw)
            except Exception as e:
                ename = type(e).__name__
                if (
                    "WebpageMediaEmpty" in ename
                    or "WebpageCurlFailed" in ename
                    or "MediaCaptionTooLong" in ename
                ):
                    kw.pop("file", None)
                    with suppress(Exception):
                        await event.edit(
                            text, parse_mode="html", link_preview=False, **kw
                        )
                else:
                    raise
        except Exception as e:
            LOG.warning("_safe_edit: %r", e)
            with suppress(Exception):
                await event.answer(self.strings("v_err_gui"), alert=True)

    async def _search_modules(
        self, query: str, limit: int = 30, lang: str = "en"
    ) -> list[dict[str, Any]]:
        token = await self._get_active_token()
        params = {"q": query, "limit": str(limit), "lang": lang}
        res = await self._net_req("GET", "/api/search", token=token, params=params)
        if self.httpc == 401:
            LOG.info("_search_modules: got 401, forcing token refresh")
            token = await self._get_active_token()
            if token:
                res = await self._net_req(
                    "GET", "/api/search", token=token, params=params
                )
        if not res:
            return []
        raw_list = (
            res.get("results", [])
            if isinstance(res, dict)
            else (res if isinstance(res, list) else [])
        )
        return [self._normalize_module(m) for m in raw_list if isinstance(m, dict)]

    async def _get_discussion(self, owner: str, name: str) -> dict | None:
        token = await self._get_active_token()
        return await self._net_req(
            "GET",
            f"/api/discuss/{quote(owner, safe='')}/{quote(name, safe='')}",
            token=token,
        )

    async def _post_discussion(self, owner: str, name: str, text: str) -> bool:
        token = await self._get_active_token()
        if not token:
            return False
        res = await self._net_req(
            "POST",
            f"/api/discuss/{quote(owner, safe='')}/{quote(name, safe='')}",
            token=token,
            json_data={"text": text},
        )
        return bool(res and res.get("ok"))

    @command(
        "vector",
        doc_en="<query> \u2014 search modules in Vector.",
        doc_ru="<\u0437\u0430\u043f\u0440\u043e\u0441> \u2014 \u043f\u043e\u0438\u0441\u043a \u043c\u043e\u0434\u0443\u043b\u0435\u0439 \u0432 Vector.",
    )
    async def vectorcmd(self, event: events.NewMessage.Event) -> None:
        q = event.text.split(maxsplit=1)
        q = q[1].strip() if len(q) > 1 else ""
        LOG.info("vectorcmd: query=%r", q)
        if not q:
            await event.edit(
                f"{self.ICONS['error']} <b>{self.strings('v_err_empty', p='<code>.</code>')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            return
        if len(q) > 120:
            await event.edit(
                f"{self.ICONS['warn']} <b>{self.strings('v_err_len')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            return

        success, form_msg = await self.kernel.inline_form(
            event.chat_id,
            "🪐",
            buttons=[
                [
                    self.Button.inline(
                        "\u2800",
                        self.cb_vector_search,
                        data=self._cb_data("v_search", q=q),
                    )
                ]
            ],
            ttl=300,
        )
        if success and form_msg:
            await form_msg.click(0)
        else:
            await event.edit(
                f"{self.ICONS['error']} <b>{self.strings('v_err_api')}</b>",
                parse_mode="html",
                link_preview=False,
            )

    @command(
        "vecupdate",
        doc_en="[-f|--force] \u2014 update Vector module.",
        doc_ru="[-f|--force] \u2014 \u043e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043c\u043e\u0434\u0443\u043b\u044c Vector.",
    )
    async def vecupdate(self, event: events.NewMessage.Event) -> None:
        args = event.text.split(maxsplit=1)
        args_str = args[1].strip() if len(args) > 1 else ""
        force = "-f" in args_str or "--force" in args_str
        LOG.info("vecupdate: force=%s", force)
        dl_url = "https://raw.githubusercontent.com/hairpin01/repo-MCUB-fork/refs/heads/main/Vector-MCUB-repo.py"
        if force:
            await event.edit(
                f"{self.ICONS['search']} <b>{self.strings('v_upd_req')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            res, _ = await self._safe_install("Vector", dl_url, notify=False)
            if res == -1:
                await event.edit(
                    f"{self.ICONS['error']} <b>{self.strings('v_upd_err')}</b>",
                    parse_mode="html",
                    link_preview=False,
                )
            elif res == 1:
                await event.edit(
                    f"{self.ICONS['safe']} <b>{self.strings('v_upd_ok')}</b>",
                    parse_mode="html",
                    link_preview=False,
                )
            else:
                await event.edit(
                    f"{self.ICONS['error']} <b>{self.strings('v_upd_err')}</b>",
                    parse_mode="html",
                    link_preview=False,
                )
            return
        await self.inline(
            event.chat_id,
            f"{self.ICONS['safe']} {self.strings('v_upd_same')}",
            buttons=[
                [
                    self.Button.inline(
                        self.strings["v_upd_force_btn"],
                        self.force_update,
                        data=self._cb_data("force_upd", url=dl_url),
                    )
                ]
            ],
            parse_mode="html",
        )

    @callback()
    async def force_update(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        if not data:
            return
        with suppress(Exception):
            await event.answer()
        with suppress(Exception):
            await event.edit(
                f"{self.ICONS['search']} <b>{self.strings('v_upd_req')}</b>",
                parse_mode="html",
                link_preview=False,
            )
        res, _ = await self._safe_install("Vector", data.get("url", ""), notify=False)
        with suppress(Exception):
            await event.edit(
                (
                    f"{self.ICONS['safe']} <b>{self.strings('v_upd_ok')}</b>"
                    if res == 1
                    else f"{self.ICONS['error']} <b>{self.strings('v_upd_err')}</b>"
                ),
                parse_mode="html",
                link_preview=False,
            )

    @command(
        "vecme",
        doc_en="\u2014 open Vector as Telegram Mini App.",
        doc_ru="\u2014 \u043e\u0442\u043a\u0440\u044b\u0442\u044c Vector \u043a\u0430\u043a Telegram Mini App.",
    )
    async def vecmecmd(self, event: events.NewMessage.Event) -> None:
        bot_info = await self._net_req("GET", "/api/tg-bot")
        bot_uname = (bot_info or {}).get("username", "").strip().lstrip("@")
        if not bot_uname:
            await event.edit(
                f"{self.ICONS['error']} <b>{self.strings('v_err_api')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            return
        link = f"https://t.me/{bot_uname}/vector"
        text = f"{self.ICONS['shield']} <b>Vector Mini App</b>\n\nOpen Vector in Telegram Mini App"
        await self.inline(
            event.chat_id,
            text,
            buttons=[[Button.url("\U0001f680 Open", link)]],
            parse_mode="html",
        )

    @command(
        "vecdl",
        doc_en="<slug or URL> \u2014 download and install entire module collection from Vector.",
        doc_ru="<slug \u0438\u043b\u0438 \u0441\u0441\u044b\u043b\u043a\u0430> \u2014 \u0441\u043a\u0430\u0447\u0430\u0442\u044c \u0438 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u043a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u044e \u0438\u0437 Vector.",
    )
    async def vecdlcmd(self, event: events.NewMessage.Event) -> None:
        args = event.text.split(maxsplit=1)
        raw_arg = args[1].strip() if len(args) > 1 else ""
        slug = (
            raw_arg.split("/collections/")[-1].split("/")[0].split("?")[0]
            if "/collections/" in raw_arg
            else raw_arg
        )
        LOG.info("vecdl: slug=%r", slug)
        if not slug:
            await event.edit(
                f"{self.ICONS['error']} <b>{self.strings('v_vecdl_usage', p='<code>.</code>')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            return
        token = await self._get_active_token()
        if not token:
            await event.edit(
                self.bannote
                or f"{self.ICONS['error']} <b>{self.strings('v_err_api')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            return
        raw = await self._net_req(
            "GET", f"/api/collections/{quote(slug, safe='')}", token=token
        )
        if not raw or not raw.get("ok"):
            await event.edit(
                f"{self.ICONS['error']} <b>{self.strings('v_dlcoll_not_found')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            return
        col = raw["collection"]
        modules = [
            entry["module"]
            for entry in (col.get("modules") or [])
            if entry.get("module")
        ]
        if not modules:
            await event.edit(
                f"{self.ICONS['warn']} <b>{self.strings('v_dlcoll_empty')}</b>",
                parse_mode="html",
                link_preview=False,
            )
            return
        await event.edit(
            f"{self.ICONS['search']} <b>{self.strings('v_sending')}</b>",
            parse_mode="html",
            link_preview=False,
        )
        max_batch = int(self.config["max_batch"])
        total_orig = len(modules)
        if total_orig > max_batch:
            modules = modules[:max_batch]
        col_name = col.get("name", slug)
        await self._safe_edit(
            event,
            f"{self.ICONS['modules_list']} {self.strings('v_dlcoll_hdr', name=_esc(col_name))}\n{self.strings('v_dlcoll_count', count=len(modules))}",
            [
                [
                    self.Button.inline(
                        self.strings["v_btn_dl"],
                        self.cb_vecdl_install,
                        data=self._cb_data(
                            "vecdl_install",
                            modules=modules,
                            col_name=col_name,
                            total_orig=total_orig,
                            max_batch=max_batch,
                        ),
                    )
                ]
            ],
        )

    @callback()
    async def cb_vecdl_install(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        if not data:
            return
        with suppress(Exception):
            await event.answer()
        modules = data.get("modules", [])
        col_name = data.get("col_name", "?")
        total_orig = data.get("total_orig", 0)
        max_batch = data.get("max_batch", 50)
        await self._safe_edit(
            event,
            f"{self.ICONS['modules_list']} {self.strings('v_dlcoll_hdr', name=_esc(col_name))}\n{self.strings('v_dlcoll_count', count=len(modules))}\n\n{self.ICONS['search']} {self.strings('v_dlcoll_start')}",
            [
                [
                    self.Button.inline(
                        "\u2026", self.cb_dummy, data=self._cb_data("dummy")
                    )
                ]
            ],
        )
        ok = 0
        failed: list[str] = []
        for mod in modules:
            dl_url = (
                mod.get("source_download_url")
                or mod.get("source_raw_url")
                or f"{API_BASE}/modules/{quote(str(mod.get('source_owner', 'unknown')), safe='')}/{quote((mod.get('name') or ''), safe='')}/source"
            )
            m_name = mod.get("name", "?")
            res, errors = await self._safe_install(m_name, dl_url, notify=False)
            if res == 1:
                ok += 1
            else:
                err_text = "unknown"
                if errors:
                    err_text = errors[0].get("type", "unknown")
                elif res == -1:
                    err_text = self.strings("v_install_fail_not_found")
                else:
                    err_text = self.strings("v_dl_err")
                failed.append(
                    self.strings(
                        "v_dlcoll_fail_item", name=_esc(m_name), reason=err_text
                    )
                )
            await asyncio.sleep(2)
        if ok == len(modules):
            result = f"{self.ICONS['safe']} {self.strings('v_dlcoll_done')}"
        elif ok > 0:
            result = f"{self.ICONS['warn']} {self.strings('v_dlcoll_done_partial')}"
        else:
            result = f"{self.ICONS['error']} {self.strings('v_dlcoll_done_none')}"
        result += f"\n<b>{ok}/{len(modules)}</b>"
        if failed:
            result += "\n\n" + "\n".join(failed[:8])
            if len(failed) > 8:
                result += f"\n\u2026 +{len(failed) - 8} more"
        if total_orig > max_batch:
            result += f"\n\n<i>{self.strings('v_dlcoll_max_batch', total=total_orig, max=max_batch)}</i>"
        await self._safe_edit(
            event,
            result,
            [
                [
                    self.Button.inline(
                        "\u2716\ufe0f", self.cb_dummy, data=self._cb_data("close")
                    )
                ]
            ],
        )

    @watcher()
    async def vector_install_payload_watcher(
        self, event: events.NewMessage.Event
    ) -> None:
        if event.out:
            return
        if not self.config["VectorInstall"]:
            return
        if not self.btid:
            try:
                binfo = await self._net_req("GET", "/api/tg-bot")
                buname = (binfo or {}).get("username", "").strip().lstrip("@")
                if buname:
                    self.btid = getattr(await self.client.get_entity(buname), "id", 0)
            except Exception:
                self.btid = -1
        if self.btid <= 0:
            return
        sid = getattr(event, "sender_id", None) or 0
        if sid and int(sid) != self.btid:
            return
        text = (event.text or "").strip()
        if text == LANG_PING:
            with suppress(Exception):
                await self.client.send_message(
                    event.chat_id, f"{LANG_PONG}{self._detect_lang_suffix()}"
                )
            with suppress(Exception):
                await event.delete()
            return
        if not text.startswith("#v_payload:"):
            return
        parts = text.split(":", 4)
        if len(parts) != 5:
            return
        _, owner_module, action, ts_raw, signature = parts
        LOG.info("vector_watcher: owner_module=%s action=%s", owner_module, action)
        owner, module_name = (
            owner_module.split("|", 1)
            if "|" in owner_module
            else ("unknown", owner_module)
        )
        if action not in {"install", "like", "dislike"}:
            return
        if not re.fullmatch(r"[A-Za-z0-9._-]+", module_name) or not ts_raw.isdigit():
            return
        if abs(int(time.time()) - int(ts_raw)) > 60:
            return
        local_signature = hmac.new(
            AUTH_SECRET.encode("utf-8"),
            f"{owner_module}:{action}:{ts_raw}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(local_signature, signature):
            return
        with suppress(Exception):
            await event.delete()

        async def send_feedback(
            status: str, reason: str = "", b_until: str = ""
        ) -> None:
            fb_ts = int(time.time())
            safe_r = reason.replace(":", " ").strip()[:200]
            safe_u = b_until.replace(":", " ").strip()[:50]
            fb_payload = f"{owner_module}:{action}:{status}:{fb_ts}:{safe_r}:{safe_u}"
            fb_sig = hmac.new(
                AUTH_SECRET.encode("utf-8"), fb_payload.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            with suppress(Exception):
                await self.client.send_message(
                    event.chat_id,
                    f"#v_feedback:{owner_module}:{action}:{status}:{fb_ts}:{safe_r}:{safe_u}:{fb_sig}",
                )

        token = await self._get_active_token()
        if not token:
            await send_feedback(
                "banned",
                "User is banned" if not self.bannote else str(self.bannote),
                "permanent",
            )
            return
        if action == "install":
            dl_url = f"{API_BASE}/modules/{quote(owner, safe='')}/{quote(module_name, safe='')}/source"
            res, _ = await self._safe_install(module_name, dl_url, notify=False)
            await send_feedback("ok" if res == 1 else "error")
            return
        uid = self._parse_jwt(token).get("sub", "")
        res = await self._net_req(
            "POST",
            f"/api/rate/{quote(str(uid), safe='')}/{quote(owner, safe='')}/{quote(module_name, safe='')}/{action}",
            token=token,
        )
        if not res and self.httpc in {401, 403}:
            await send_feedback("banned", "User is banned", "permanent")
            return
        await send_feedback("ok" if res and res.get("ok") else "error")

    @inline("vector")
    async def vector_discussion_inline(self, event: events.InlineQuery.Event) -> None:
        query = event.args.strip()
        # Format: uid text message
        space = query.find(" ")
        if space == -1:
            await event.answer(
                [
                    event.builder.article(
                        title=self.strings("v_rep_ask"),
                        text=self.strings("v_rep_ask"),
                    )
                ]
            )
            return
        raw_uid = query[:space].strip()
        text = query[space + 1 :].strip()
        if len(text) < 2:
            await event.answer(
                [
                    event.builder.article(
                        title=self.strings("v_rep_min"),
                        text=self.strings("v_rep_min"),
                    )
                ]
            )
            return
        if len(text) > 1800:
            await event.answer(
                [
                    event.builder.article(
                        title=self.strings("v_rep_max"),
                        text=self.strings("v_rep_max"),
                    )
                ]
            )
            return

        # Find which module this uid belongs to by scanning cached groups
        owner = name = ""
        for group_key, group in self._cached_groups.items():
            for mod in group:
                mod_uid = self._norm_hash_name(
                    f"{mod.get('owner', '')}|{mod.get('name', '')}"
                )
                if mod_uid == raw_uid:
                    owner = mod.get("owner", "")
                    name = mod.get("name", "")
                    break
            if owner and name:
                break

        if not owner or not name:
            await event.answer(
                [
                    event.builder.article(
                        title=self.strings("v_rep_err"),
                        text=self.strings("v_rep_err"),
                    )
                ]
            )
            return

        ok = await self._post_discussion(owner, name, text)
        if ok:
            await event.answer(
                [
                    event.builder.article(
                        title=self.strings("v_rep_ok"),
                        text=self.strings("v_rep_ok"),
                    )
                ]
            )
        else:
            await event.answer(
                [
                    event.builder.article(
                        title=self.strings("v_rep_err"),
                        text=self.strings("v_rep_err"),
                    )
                ]
            )

    @callback()
    async def cb_vector_search(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        with suppress(Exception):
            await event.answer()
        if not data:
            return
        q = data.get("q", "")
        if not q:
            with suppress(Exception):
                await event.edit(
                    f"{self.ICONS['error']} <b>{self.strings('v_err_404', q='?')}</b>",
                    parse_mode="html",
                    link_preview=False,
                )
            return

        # Step 2: show loading text + fallback banner
        await self._safe_edit(
            event,
            f"{self.ICONS['search']} <b>{self.strings('v_sending')}</b>",
            banner_url=LOADING_BANNER,
        )

        token = await self._get_active_token()
        if not token:
            with suppress(Exception):
                await event.edit(
                    self.bannote
                    or f"{self.ICONS['error']} <b>{self.strings('v_err_api')}</b>",
                    parse_mode="html",
                    link_preview=False,
                )
            return

        m_list = await self._search_modules(
            q, limit=self.config["limit"], lang=self._detect_lang_suffix()
        )
        LOG.info("cb_vector_search: %d results for q=%r", len(m_list), q)

        if not m_list:
            with suppress(Exception):
                await event.edit(
                    f"{self.ICONS['error']} <b>{self.strings('v_err_404', q=_esc(q))}</b>",
                    parse_mode="html",
                    link_preview=False,
                )
            return

        cache_key = f"v_{self._norm_hash_name(q)}_{int(time.time())}"
        self._cached_groups[cache_key] = m_list
        if len(self._cached_groups) > 50:
            old = sorted(self._cached_groups.keys())[:-40]
            for k in old:
                self._cached_groups.pop(k, None)

        # Step 3: show results with module banner (or fallback)
        item = m_list[0]
        await self._safe_edit(
            event,
            self._build_html(item, 1, len(m_list)),
            self._build_kbd(item, 0, m_list, cache_key),
            item.get("banner") or FALLBACK_BANNER,
        )

    @callback()
    async def cb_toggle(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        with suppress(Exception):
            await event.answer()
        if not data:
            return
        i = data.get("i", 0)
        q = data.get("q", "")
        expanded = bool(data.get("expanded", False))
        group = self._cached_groups.get(q, [])
        if 0 <= i < len(group):
            item = group[i]
            await self._safe_edit(
                event,
                self._build_html(item, i + 1, len(group)),
                self._build_kbd(item, i, group, q, expanded=expanded),
                item.get("banner"),
            )

    @callback()
    async def cb_dummy(self, event: events.CallbackQuery.Event) -> None:
        with suppress(Exception):
            await event.answer()

    @callback()
    async def cb_nav(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        with suppress(Exception):
            await event.answer()
        if not data:
            return
        group = self._cached_groups.get(data.get("q", ""), [])
        i = data.get("i", 0)
        expanded = bool(data.get("expanded", False))
        cp = data.get("cp", 0)
        if 0 <= i < len(group):
            await self._safe_edit(
                event,
                self._build_html(group[i], i + 1, len(group)),
                self._build_kbd(
                    group[i],
                    i,
                    group,
                    data.get("q", ""),
                    expanded=expanded,
                    comments_pg=cp,
                ),
                group[i].get("banner"),
            )

    @callback()
    async def cb_list(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        with suppress(Exception):
            await event.answer()
        if not data:
            return
        group = self._cached_groups.get(data.get("q", ""), [])
        i = data.get("i", 0)
        if not group:
            with suppress(Exception):
                await event.edit(
                    f"{self.ICONS['error']} {self.strings('v_err_404', q='?')}",
                    parse_mode="html",
                    link_preview=False,
                )
            return
        i = i if 0 <= i < len(group) else 0
        await self._safe_edit(
            event,
            self._build_html(group[i], i + 1, len(group)),
            self._build_kbd(group[i], i, group, data.get("q", "")),
            group[i].get("banner"),
        )

    @callback()
    async def cb_rate(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        if not data:
            return
        action = data.get("action", "like")
        m_owner, m_name = data.get("owner", ""), data.get("name", "")
        i, q = data.get("i", 0), data.get("q", "")
        group = self._cached_groups.get(q, [])
        token = await self._get_active_token()
        if not token:
            with suppress(Exception):
                await event.answer(
                    self.bannote or self.strings("v_err_api"), alert=True
                )
            return
        uid = self._parse_jwt(token).get("sub", "")
        res = await self._net_req(
            "POST",
            f"/api/rate/{quote(str(uid), safe='')}/{quote(m_owner, safe='')}/{quote(m_name, safe='')}/{action}",
            token=token,
        )
        if not res:
            with suppress(Exception):
                await event.answer(self.strings("v_err_api"), alert=True)
            return
        nl, nd = self._extract_counts(res)
        if group and i < len(group):
            if nl is not None:
                group[i]["likes"] = nl
            if nd is not None:
                group[i]["dislikes"] = nd
            item = group[i]
        else:
            item = {"name": m_name, "likes": nl or 0, "dislikes": nd or 0}
        await self._safe_edit(
            event,
            self._build_html(item, i + 1, len(group or [item])),
            self._build_kbd(item, i, group, q),
            item.get("banner"),
        )
        s_val = res.get("rating", {}).get("state")
        with suppress(Exception):
            await event.answer(
                self.strings("v_fb_rm" if s_val == "removed" else "v_fb_add"),
                alert=True,
            )

    @callback()
    async def cb_install(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        if not data:
            return
        m_owner, m_name = data.get("owner", ""), data.get("name", "")
        i, q = data.get("i", 0), data.get("q", "")
        group = self._cached_groups.get(q, [])
        token = await self._get_active_token()
        if not token:
            with suppress(Exception):
                await event.answer(
                    self.bannote or self.strings("v_err_api"), alert=True
                )
            return
        dl_url = f"{API_BASE}/modules/{quote(m_owner, safe='')}/{quote(m_name, safe='')}/source"
        res, errors = await self._safe_install(m_name, dl_url)
        if res == -1:
            with suppress(Exception):
                await event.answer(self.strings("v_dl_err"), alert=True)
            return
        if res == 1:
            with suppress(Exception):
                await event.answer(self.strings("v_dl_ok"), alert=True)
            return
        if errors:
            item = group[i] if group and 0 <= i < len(group) else {"name": m_name}
            await self._safe_edit(
                event,
                self._fmt_install_errors(m_name, errors),
                self._build_kbd(item, i, group, q),
                item.get("banner"),
            )
        else:
            with suppress(Exception):
                await event.answer(self.strings("v_dl_err"), alert=True)

    @callback()
    async def cb_sec_check(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        if not data:
            return
        m_owner, m_name = data.get("owner", ""), data.get("name", "")
        i, q = data.get("i", 0), data.get("q", "")
        group = self._cached_groups.get(q, [])
        item = group[i] if group and 0 <= i < len(group) else {"name": m_name}
        await self._safe_edit(
            event,
            self._build_sec_html(item, None),
            self._build_sec_kbd(item, i, group, q, False),
        )

    @callback()
    async def cb_scan_go(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        if not data:
            return
        m_owner, m_name = data.get("owner", ""), data.get("name", "")
        i, q = data.get("i", 0), data.get("q", "")
        group = self._cached_groups.get(q, [])
        item = (
            group[i]
            if group and 0 <= i < len(group)
            else {"name": m_name, "owner": m_owner}
        )
        token = await self._get_active_token()
        if not token:
            with suppress(Exception):
                await event.answer(self.strings("v_err_api"), alert=True)
            return
        with suppress(Exception):
            await event.edit(
                f"{self.ICONS['shield']} <b>{_esc(m_name)}</b>\n\n{self.strings('v_aud_req')}",
                parse_mode="html",
                link_preview=False,
            )
        res = await self._net_req(
            "POST",
            f"/api/scan/{quote(m_owner, safe='')}/{quote(m_name, safe='')}",
            token=token,
        )
        if not res:
            await self._safe_edit(
                event,
                f"{self.ICONS['error']} <b>{_esc(m_name)}</b>\n\n{self.strings('v_aud_err')}",
                self._build_sec_kbd(item, i, group, q, True),
            )
            return
        await self._safe_edit(
            event,
            self._build_sec_html(item, res),
            self._build_sec_kbd(item, i, group, q, True),
        )

    @callback()
    async def cb_talk(
        self, event: events.CallbackQuery.Event, data: dict[str, Any] | None = None
    ) -> None:
        if not data:
            return
        m_owner, m_name = data.get("owner", ""), data.get("name", "")
        i, q = data.get("i", 0), data.get("q", "")
        group = self._cached_groups.get(q, [])
        disc = await self._get_discussion(m_owner, m_name)
        html = self._build_discussion_html(disc, m_name)
        kbd = self._build_discussion_kbd(
            m_owner, m_name, i, len(group) if group else 1, q
        )
        item = group[i] if group and 0 <= i < len(group) else {"name": m_name}
        await self._safe_edit(event, html, kbd, item.get("banner"))
