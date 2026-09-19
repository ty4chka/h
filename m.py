#!/usr/bin/env python3
"""
Hydra UserBot — Cython Edition v4.1 (MCUB Ready + Debug Modules)
Tokyo Night TUI with Tabbed Account Manager + Multi-Theme + Vim Navigation
+ Module Scanner & BAT Viewer + Normal Input Flow
"""

import asyncio
import logging
import os
import time
import sys
import json
import argparse
import shutil
import subprocess
import tty
import termios
import threading
import queue
import ast
import select
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from collections import deque

# ── MCUB Integration ──────────────────────────────────────
try:
    from core.lib.telethon_mcub import (
        UnifiedTelegramClient,
        patch_adapter_for_unified_client,
    )
    MCUB_READY = True
except ImportError:
    from telethon import TelegramClient
    MCUB_READY = False

from telethon import connection
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
)
from telethon.sessions import StringSession

from rich.console import Console, Group
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeRemainingColumn, MofNCompleteColumn
)
from rich.panel import Panel
from rich.box import Box, ROUNDED, HEAVY_EDGE, DOUBLE_EDGE, SIMPLE
from rich.prompt import Prompt, Confirm
from rich.layout import Layout
from rich.columns import Columns
from rich.text import Text
from rich.align import Align
from rich.rule import Rule
from rich.live import Live
from rich.style import Style
from rich.syntax import Syntax

import config
from utils.misc import set_start_time

console = Console()

# ═══════════════════════════════════════════════════════════
#  MULTI-THEME SYSTEM
# ═══════════════════════════════════════════════════════════

THEMES = {
    "tokyo_night": {
        "name": "Tokyo Night",
        "BG": "#1a1b26", "SURFACE": "#24283b", "BORDER": "#3b4261",
        "COMMENT": "#565f89", "BLUE": "#7aa2f7", "GREEN": "#9ece6a",
        "CYAN": "#73daca", "FG": "#c0caf5", "YELLOW": "#e0af68",
        "RED": "#f7768e", "PURPLE": "#bb9af7", "ORANGE": "#ff9e64",
    },
    "catppuccin_mocha": {
        "name": "Catppuccin Mocha",
        "BG": "#1e1e2e", "SURFACE": "#313244", "BORDER": "#45475a",
        "COMMENT": "#6c7086", "BLUE": "#89b4fa", "GREEN": "#a6e3a1",
        "CYAN": "#94e2d5", "FG": "#cdd6f4", "YELLOW": "#f9e2af",
        "RED": "#f38ba8", "PURPLE": "#cba6f7", "ORANGE": "#fab387",
    },
    "gruvbox_dark": {
        "name": "Gruvbox Dark",
        "BG": "#282828", "SURFACE": "#3c3836", "BORDER": "#504945",
        "COMMENT": "#928374", "BLUE": "#83a598", "GREEN": "#b8bb26",
        "CYAN": "#8ec07c", "FG": "#ebdbb2", "YELLOW": "#fabd2f",
        "RED": "#fb4934", "PURPLE": "#d3869b", "ORANGE": "#fe8019",
    },
    "nord": {
        "name": "Nord",
        "BG": "#2e3440", "SURFACE": "#3b4252", "BORDER": "#434c5e",
        "COMMENT": "#4c566a", "BLUE": "#81a1c1", "GREEN": "#a3be8c",
        "CYAN": "#88c0d0", "FG": "#eceff4", "YELLOW": "#ebcb8b",
        "RED": "#bf616a", "PURPLE": "#b48ead", "ORANGE": "#d08770",
    },
    "dracula": {
        "name": "Dracula",
        "BG": "#282a36", "SURFACE": "#44475a", "BORDER": "#6272a4",
        "COMMENT": "#6272a4", "BLUE": "#8be9fd", "GREEN": "#50fa7b",
        "CYAN": "#8be9fd", "FG": "#f8f8f2", "YELLOW": "#f1fa8c",
        "RED": "#ff5555", "PURPLE": "#bd93f9", "ORANGE": "#ffb86c",
    },
    "one_dark": {
        "name": "One Dark",
        "BG": "#282c34", "SURFACE": "#353b45", "BORDER": "#3e4451",
        "COMMENT": "#5c6370", "BLUE": "#61afef", "GREEN": "#98c379",
        "CYAN": "#56b6c2", "FG": "#abb2bf", "YELLOW": "#e5c07b",
        "RED": "#e06c75", "PURPLE": "#c678dd", "ORANGE": "#d19a66",
    },
    "solarized_dark": {
        "name": "Solarized Dark",
        "BG": "#002b36", "SURFACE": "#073642", "BORDER": "#586e75",
        "COMMENT": "#657b83", "BLUE": "#268bd2", "GREEN": "#859900",
        "CYAN": "#2aa198", "FG": "#eee8d5", "YELLOW": "#b58900",
        "RED": "#dc322f", "PURPLE": "#d33682", "ORANGE": "#cb4b16",
    },
    "monokai": {
        "name": "Monokai",
        "BG": "#272822", "SURFACE": "#383830", "BORDER": "#49483e",
        "COMMENT": "#75715e", "BLUE": "#66d9ef", "GREEN": "#a6e22e",
        "CYAN": "#66d9ef", "FG": "#f8f8f2", "YELLOW": "#e6db74",
        "RED": "#f92672", "PURPLE": "#ae81ff", "ORANGE": "#fd971f",
    },
    "rose_pine": {
        "name": "Rosé Pine",
        "BG": "#191724", "SURFACE": "#1f1d2e", "BORDER": "#26233a",
        "COMMENT": "#6e6a86", "BLUE": "#9ccfd8", "GREEN": "#31748f",
        "CYAN": "#9ccfd8", "FG": "#e0def4", "YELLOW": "#f6c177",
        "RED": "#eb6f92", "PURPLE": "#c4a7e7", "ORANGE": "#ebbcba",
    },
    "cyberpunk": {
        "name": "Cyberpunk",
        "BG": "#0d0221", "SURFACE": "#1a0b2e", "BORDER": "#2d1b4e",
        "COMMENT": "#5a4a6a", "BLUE": "#00f0ff", "GREEN": "#00ff9f",
        "CYAN": "#00f0ff", "FG": "#f0e6ff", "YELLOW": "#ffee00",
        "RED": "#ff006e", "PURPLE": "#bc13fe", "ORANGE": "#ff8500",
    },
    "material_ocean": {
        "name": "Material Ocean",
        "BG": "#0f111a", "SURFACE": "#1a1c25", "BORDER": "#2a2d3a",
        "COMMENT": "#464b5d", "BLUE": "#82aaff", "GREEN": "#c3e88d",
        "CYAN": "#89ddff", "FG": "#a6accd", "YELLOW": "#ffcb6b",
        "RED": "#f07178", "PURPLE": "#c792ea", "ORANGE": "#f78c6c",
    },
    "ayu_dark": {
        "name": "Ayu Dark",
        "BG": "#0a0e14", "SURFACE": "#131721", "BORDER": "#242936",
        "COMMENT": "#5c6773", "BLUE": "#39bae6", "GREEN": "#7ee787",
        "CYAN": "#73d0ff", "FG": "#bfbdb6", "YELLOW": "#e6b450",
        "RED": "#f07178", "PURPLE": "#d2a6ff", "ORANGE": "#ff8f40",
    },
    "ayu_mirage": {
        "name": "Ayu Mirage",
        "BG": "#1f2430", "SURFACE": "#2a3341", "BORDER": "#3d4a5c",
        "COMMENT": "#5c6773", "BLUE": "#73d0ff", "GREEN": "#87d96c",
        "CYAN": "#95e6cb", "FG": "#cccac2", "YELLOW": "#ffd580",
        "RED": "#f28779", "PURPLE": "#d4bfff", "ORANGE": "#ffad66",
    },
    "palenight": {
        "name": "Palenight",
        "BG": "#292d3e", "SURFACE": "#34324a", "BORDER": "#444267",
        "COMMENT": "#676e95", "BLUE": "#82aaff", "GREEN": "#c3e88d",
        "CYAN": "#89ddff", "FG": "#959dcb", "YELLOW": "#ffcb6b",
        "RED": "#f07178", "PURPLE": "#c792ea", "ORANGE": "#f78c6c",
    },
    "horizon": {
        "name": "Horizon",
        "BG": "#1c1e26", "SURFACE": "#232530", "BORDER": "#2e303e",
        "COMMENT": "#6c6f93", "BLUE": "#25b2bc", "GREEN": "#27d796",
        "CYAN": "#21bfc2", "FG": "#d5d8da", "YELLOW": "#fab795",
        "RED": "#e95678", "PURPLE": "#b877db", "ORANGE": "#f09383",
    },
    "outrun": {
        "name": "Outrun",
        "BG": "#1e1e2e", "SURFACE": "#2d1b4e", "BORDER": "#3d2b5e",
        "COMMENT": "#6c6f93", "BLUE": "#00f0ff", "GREEN": "#00ff9f",
        "CYAN": "#00f0ff", "FG": "#f0e6ff", "YELLOW": "#ffee00",
        "RED": "#ff006e", "PURPLE": "#bc13fe", "ORANGE": "#ff8500",
    },
    "synthwave": {
        "name": "Synthwave",
        "BG": "#2b213a", "SURFACE": "#362b48", "BORDER": "#463458",
        "COMMENT": "#6c6f93", "BLUE": "#00f0ff", "GREEN": "#72f1b8",
        "CYAN": "#00f0ff", "FG": "#f0e6ff", "YELLOW": "#fede5d",
        "RED": "#fe4450", "PURPLE": "#ff7edb", "ORANGE": "#ff8b39",
    },
    "oceanic_next": {
        "name": "Oceanic Next",
        "BG": "#1b2b34", "SURFACE": "#24333d", "BORDER": "#343d46",
        "COMMENT": "#65737e", "BLUE": "#6699cc", "GREEN": "#99c794",
        "CYAN": "#5fb3b3", "FG": "#cdd3de", "YELLOW": "#fac863",
        "RED": "#ec5f67", "PURPLE": "#c594c5", "ORANGE": "#f99157",
    },
    "panda": {
        "name": "Panda",
        "BG": "#292a2b", "SURFACE": "#333435", "BORDER": "#444546",
        "COMMENT": "#676b79", "BLUE": "#6cb3e3", "GREEN": "#87d96c",
        "CYAN": "#6fc3df", "FG": "#e6e6e6", "YELLOW": "#ffd866",
        "RED": "#ff2c6d", "PURPLE": "#c792ea", "ORANGE": "#ff9ac1",
    },
    "vaporwave": {
        "name": "Vaporwave",
        "BG": "#1a1a2e", "SURFACE": "#16213e", "BORDER": "#0f3460",
        "COMMENT": "#533483", "BLUE": "#00d2ff", "GREEN": "#00ff87",
        "CYAN": "#00d2ff", "FG": "#e94560", "YELLOW": "#ff9a8b",
        "RED": "#ff006e", "PURPLE": "#8338ec", "ORANGE": "#fb5607",
    },
    "matrix": {
        "name": "Matrix",
        "BG": "#000000", "SURFACE": "#0d1117", "BORDER": "#1a2e1a",
        "COMMENT": "#2d5a27", "BLUE": "#00ff41", "GREEN": "#00ff41",
        "CYAN": "#00ff41", "FG": "#00ff41", "YELLOW": "#55ff55",
        "RED": "#ff0040", "PURPLE": "#00cc33", "ORANGE": "#33ff33",
    },
    "github_dark": {
        "name": "GitHub Dark",
        "BG": "#0d1117", "SURFACE": "#161b22", "BORDER": "#30363d",
        "COMMENT": "#8b949e", "BLUE": "#58a6ff", "GREEN": "#3fb950",
        "CYAN": "#39c5cf", "FG": "#c9d1d9", "YELLOW": "#d29922",
        "RED": "#f85149", "PURPLE": "#a371f7", "ORANGE": "#f0883e",
    },
    "deep_ocean": {
        "name": "Deep Ocean",
        "BG": "#0f111a", "SURFACE": "#181a25", "BORDER": "#252836",
        "COMMENT": "#4a4e69", "BLUE": "#7aa2f7", "GREEN": "#73daca",
        "CYAN": "#7dcfff", "FG": "#a9b1d6", "YELLOW": "#e0af68",
        "RED": "#f7768e", "PURPLE": "#bb9af7", "ORANGE": "#ff9e64",
    },
    "night_owl": {
        "name": "Night Owl",
        "BG": "#011627", "SURFACE": "#0b2942", "BORDER": "#1d3b53",
        "COMMENT": "#637777", "BLUE": "#82aaff", "GREEN": "#c792ea",
        "CYAN": "#7fdbca", "FG": "#d6deeb", "YELLOW": "#ecc48d",
        "RED": "#ef5350", "PURPLE": "#c792ea", "ORANGE": "#f78c6c",
    },
    "atom_one_dark": {
        "name": "Atom One Dark",
        "BG": "#282c34", "SURFACE": "#353b45", "BORDER": "#3e4451",
        "COMMENT": "#5c6370", "BLUE": "#61afef", "GREEN": "#98c379",
        "CYAN": "#56b6c2", "FG": "#abb2bf", "YELLOW": "#e5c07b",
        "RED": "#e06c75", "PURPLE": "#c678dd", "ORANGE": "#d19a66",
    },
    "tomorrow_night": {
        "name": "Tomorrow Night",
        "BG": "#1d1f21", "SURFACE": "#282a2e", "BORDER": "#373b41",
        "COMMENT": "#969896", "BLUE": "#81a2be", "GREEN": "#b5bd68",
        "CYAN": "#8abeb7", "FG": "#c5c8c6", "YELLOW": "#f0c674",
        "RED": "#cc6666", "PURPLE": "#b294bb", "ORANGE": "#de935f",
    },
    "shades_of_purple": {
        "name": "Shades of Purple",
        "BG": "#2d2b55", "SURFACE": "#363377", "BORDER": "#444488",
        "COMMENT": "#6c6f93", "BLUE": "#9effff", "GREEN": "#72f1b8",
        "CYAN": "#9effff", "FG": "#e0e0e0", "YELLOW": "#ffe66d",
        "RED": "#ff2c6d", "PURPLE": "#ff7edb", "ORANGE": "#ff9a8b",
    },
    "city_lights": {
        "name": "City Lights",
        "BG": "#1d252c", "SURFACE": "#252f38", "BORDER": "#33404d",
        "COMMENT": "#41505e", "BLUE": "#5ec4ff", "GREEN": "#8bd49c",
        "CYAN": "#70e1e8", "FG": "#a0b3c5", "YELLOW": "#ebbf83",
        "RED": "#d95468", "PURPLE": "#b62d65", "ORANGE": "#e27e8d",
    },
    "cobalt2": {
        "name": "Cobalt2",
        "BG": "#193549", "SURFACE": "#1f4662", "BORDER": "#2b5c82",
        "COMMENT": "#0088ff", "BLUE": "#1478db", "GREEN": "#3ad900",
        "CYAN": "#00ffff", "FG": "#e1efff", "YELLOW": "#ffee80",
        "RED": "#ff628c", "PURPLE": "#ff80e1", "ORANGE": "#ff9d00",
    },
    "dark_plus": {
        "name": "Dark+",
        "BG": "#1e1e1e", "SURFACE": "#252526", "BORDER": "#3e3e42",
        "COMMENT": "#6a9955", "BLUE": "#569cd6", "GREEN": "#b5cea8",
        "CYAN": "#4ec9b0", "FG": "#d4d4d4", "YELLOW": "#dcdcaa",
        "RED": "#f44747", "PURPLE": "#c586c0", "ORANGE": "#ce9178",
    },
    "edge_dark": {
        "name": "Edge Dark",
        "BG": "#2c2e34", "SURFACE": "#363944", "BORDER": "#414550",
        "COMMENT": "#5a5b5e", "BLUE": "#6cb6eb", "GREEN": "#a0c980",
        "CYAN": "#5dbbc1", "FG": "#c5cdd9", "YELLOW": "#de935f",
        "RED": "#ec7279", "PURPLE": "#d38aea", "ORANGE": "#e59b4e",
    },
    "everforest": {
        "name": "Everforest",
        "BG": "#2b3339", "SURFACE": "#323c41", "BORDER": "#3a454a",
        "COMMENT": "#859289", "BLUE": "#7fbbb3", "GREEN": "#a7c080",
        "CYAN": "#83c092", "FG": "#d3c6aa", "YELLOW": "#dbbc7f",
        "RED": "#e67e80", "PURPLE": "#d699b6", "ORANGE": "#e69875",
    },
    "kanagawa": {
        "name": "Kanagawa",
        "BG": "#1f1f28", "SURFACE": "#2a2a37", "BORDER": "#363646",
        "COMMENT": "#727169", "BLUE": "#7e9cd8", "GREEN": "#98bb6c",
        "CYAN": "#6a9589", "FG": "#dcd7ba", "YELLOW": "#e6c384",
        "RED": "#ff5d62", "PURPLE": "#957fb8", "ORANGE": "#ffa066",
    },
    "nightfox": {
        "name": "Nightfox",
        "BG": "#192330", "SURFACE": "#212e3f", "BORDER": "#2f3f52",
        "COMMENT": "#738091", "BLUE": "#719cd6", "GREEN": "#81b29a",
        "CYAN": "#63cdcf", "FG": "#cdcecf", "YELLOW": "#dbc074",
        "RED": "#c94f6d", "PURPLE": "#9d79d6", "ORANGE": "#f4a261",
    },
    "oxocarbon": {
        "name": "Oxocarbon",
        "BG": "#161616", "SURFACE": "#262626", "BORDER": "#393939",
        "COMMENT": "#525252", "BLUE": "#78a9ff", "GREEN": "#42be65",
        "CYAN": "#33b1ff", "FG": "#f4f4f4", "YELLOW": "#f1c21b",
        "RED": "#fa4d56", "PURPLE": "#be95ff", "ORANGE": "#ff832b",
    },
    "rose_pine_moon": {
        "name": "Rosé Pine Moon",
        "BG": "#232136", "SURFACE": "#2a273f", "BORDER": "#393552",
        "COMMENT": "#6e6a86", "BLUE": "#9ccfd8", "GREEN": "#3e8fb0",
        "CYAN": "#9ccfd8", "FG": "#e0def4", "YELLOW": "#f6c177",
        "RED": "#eb6f92", "PURPLE": "#c4a7e7", "ORANGE": "#ea9a97",
    },
    "rose_pine_dawn": {
        "name": "Rosé Pine Dawn",
        "BG": "#faf4ed", "SURFACE": "#fffaf3", "BORDER": "#f2e9e1",
        "COMMENT": "#9893a5", "BLUE": "#56949f", "GREEN": "#286983",
        "CYAN": "#56949f", "FG": "#575279", "YELLOW": "#ea9d34",
        "RED": "#b4637a", "PURPLE": "#907aa9", "ORANGE": "#d7827e",
    },
    "solarized_light": {
        "name": "Solarized Light",
        "BG": "#fdf6e3", "SURFACE": "#eee8d5", "BORDER": "#93a1a1",
        "COMMENT": "#839496", "BLUE": "#268bd2", "GREEN": "#859900",
        "CYAN": "#2aa198", "FG": "#073642", "YELLOW": "#b58900",
        "RED": "#dc322f", "PURPLE": "#d33682", "ORANGE": "#cb4b16",
    },
    "gruvbox_light": {
        "name": "Gruvbox Light",
        "BG": "#fbf1c7", "SURFACE": "#ebdbb2", "BORDER": "#d5c4a1",
        "COMMENT": "#928374", "BLUE": "#076678", "GREEN": "#79740e",
        "CYAN": "#427b58", "FG": "#3c3836", "YELLOW": "#b57614",
        "RED": "#9d0006", "PURPLE": "#8f3f71", "ORANGE": "#af3a03",
    },
    "catppuccin_latte": {
        "name": "Catppuccin Latte",
        "BG": "#eff1f5", "SURFACE": "#e6e9ef", "BORDER": "#ccd0da",
        "COMMENT": "#9ca0b0", "BLUE": "#1e66f5", "GREEN": "#40a02b",
        "CYAN": "#179299", "FG": "#4c4f69", "YELLOW": "#df8e1d",
        "RED": "#d20f39", "PURPLE": "#8839ef", "ORANGE": "#fe640b",
    },
    "catppuccin_frappe": {
        "name": "Catppuccin Frappe",
        "BG": "#303446", "SURFACE": "#292c3c", "BORDER": "#414559",
        "COMMENT": "#737994", "BLUE": "#8caaee", "GREEN": "#a6d189",
        "CYAN": "#81c8be", "FG": "#c6d0f5", "YELLOW": "#e5c890",
        "RED": "#e78284", "PURPLE": "#ca9ee6", "ORANGE": "#ef9f76",
    },
    "catppuccin_macchiato": {
        "name": "Catppuccin Macchiato",
        "BG": "#24273a", "SURFACE": "#1e2030", "BORDER": "#363a4f",
        "COMMENT": "#6e738d", "BLUE": "#8aadf4", "GREEN": "#a6da95",
        "CYAN": "#8bd5ca", "FG": "#cad3f5", "YELLOW": "#eed49f",
        "RED": "#ed8796", "PURPLE": "#c6a0f6", "ORANGE": "#f5a97f",
    },
    "zenburn": {
        "name": "Zenburn",
        "BG": "#3f3f3f", "SURFACE": "#4f4f4f", "BORDER": "#5f5f5f",
        "COMMENT": "#7f9f7f", "BLUE": "#8cd0d3", "GREEN": "#7f9f7f",
        "CYAN": "#93e0e3", "FG": "#dcdccc", "YELLOW": "#dfaf8f",
        "RED": "#cc9393", "PURPLE": "#dc8cc3", "ORANGE": "#dca3a3",
    },
    "apprentice": {
        "name": "Apprentice",
        "BG": "#262626", "SURFACE": "#303030", "BORDER": "#3a3a3a",
        "COMMENT": "#6c6c6c", "BLUE": "#5f87af", "GREEN": "#87af87",
        "CYAN": "#5f8787", "FG": "#bcbcbc", "YELLOW": "#ffaf00",
        "RED": "#af5f5f", "PURPLE": "#8787af", "ORANGE": "#d7875f",
    },
    "tango": {
        "name": "Tango",
        "BG": "#2e3436", "SURFACE": "#3a4042", "BORDER": "#4a5052",
        "COMMENT": "#555753", "BLUE": "#3465a4", "GREEN": "#4e9a06",
        "CYAN": "#06989a", "FG": "#d3d7cf", "YELLOW": "#c4a000",
        "RED": "#cc0000", "PURPLE": "#75507b", "ORANGE": "#ce5c00",
    },
    "base16": {
        "name": "Base16 Dark",
        "BG": "#181818", "SURFACE": "#282828", "BORDER": "#383838",
        "COMMENT": "#585858", "BLUE": "#7cafc2", "GREEN": "#a1b56c",
        "CYAN": "#86c1b9", "FG": "#d8d8d8", "YELLOW": "#f7ca88",
        "RED": "#ab4642", "PURPLE": "#ba8baf", "ORANGE": "#dc9656",
    },
    "challenger_deep": {
        "name": "Challenger Deep",
        "BG": "#1e1c31", "SURFACE": "#29263c", "BORDER": "#34324a",
        "COMMENT": "#6c6f93", "BLUE": "#65b2ff", "GREEN": "#62d196",
        "CYAN": "#63f2f1", "FG": "#cbe3e7", "YELLOW": "#ffe9aa",
        "RED": "#ff5458", "PURPLE": "#a37acc", "ORANGE": "#ff8080",
    },
    "fairy_floss": {
        "name": "Fairy Floss",
        "BG": "#5a5475", "SURFACE": "#6b6594", "BORDER": "#7c76a3",
        "COMMENT": "#a39bb0", "BLUE": "#c2ffdf", "GREEN": "#c2ffdf",
        "CYAN": "#c2ffdf", "FG": "#f8f8f2", "YELLOW": "#ff857f",
        "RED": "#ff857f", "PURPLE": "#ffb8d1", "ORANGE": "#fff352",
    },
    "jellybeans": {
        "name": "Jellybeans",
        "BG": "#151515", "SURFACE": "#1c1c1c", "BORDER": "#252525",
        "COMMENT": "#888888", "BLUE": "#8197bf", "GREEN": "#99ad6a",
        "CYAN": "#8fbfdc", "FG": "#e8e8d3", "YELLOW": "#fad07a",
        "RED": "#cf6a4c", "PURPLE": "#c6b6ee", "ORANGE": "#e9c062",
    },
    "laserwave": {
        "name": "LaserWave",
        "BG": "#27212e", "SURFACE": "#332b3b", "BORDER": "#3e3449",
        "COMMENT": "#6c6f93", "BLUE": "#40b4c4", "GREEN": "#74ee15",
        "CYAN": "#00d5c3", "FG": "#ecebf0", "YELLOW": "#ffe261",
        "RED": "#eb64b9", "PURPLE": "#b381c5", "ORANGE": "#fe8c52",
    },
    "nova": {
        "name": "Nova",
        "BG": "#3c4c55", "SURFACE": "#4b5861", "BORDER": "#5a6a73",
        "COMMENT": "#899ba6", "BLUE": "#7fc1ca", "GREEN": "#99c794",
        "CYAN": "#7fc1ca", "FG": "#c5d4dd", "YELLOW": "#fac863",
        "RED": "#ec5f67", "PURPLE": "#c594c5", "ORANGE": "#f99157",
    },
    "snazzy": {
        "name": "Snazzy",
        "BG": "#282a36", "SURFACE": "#34353e", "BORDER": "#43454f",
        "COMMENT": "#686868", "BLUE": "#57c7ff", "GREEN": "#5af78e",
        "CYAN": "#9aedfe", "FG": "#eff0eb", "YELLOW": "#f3f99d",
        "RED": "#ff5c57", "PURPLE": "#ff6ac1", "ORANGE": "#ff9f43",
    },
    "spacegray": {
        "name": "Spacegray",
        "BG": "#2b303b", "SURFACE": "#343d46", "BORDER": "#4f5b66",
        "COMMENT": "#65737e", "BLUE": "#8fa1b3", "GREEN": "#a3be8c",
        "CYAN": "#96b5b4", "FG": "#c0c5ce", "YELLOW": "#ebcb8b",
        "RED": "#bf616a", "PURPLE": "#b48ead", "ORANGE": "#d08770",
    },
    "tender": {
        "name": "Tender",
        "BG": "#282828", "SURFACE": "#323232", "BORDER": "#424242",
        "COMMENT": "#666666", "BLUE": "#73cef4", "GREEN": "#c9d05c",
        "CYAN": "#66d9ef", "FG": "#eeeeee", "YELLOW": "#ffc24b",
        "RED": "#f43753", "PURPLE": "#b3deef", "ORANGE": "#ff8c42",
    },
    "twilight": {
        "name": "Twilight",
        "BG": "#1e1e1e", "SURFACE": "#323232", "BORDER": "#464646",
        "COMMENT": "#5f5a60", "BLUE": "#7587a6", "GREEN": "#8f9d6a",
        "CYAN": "#a7dbd8", "FG": "#f8f8f8", "YELLOW": "#f9ee98",
        "RED": "#cf6a4c", "PURPLE": "#9b859d", "ORANGE": "#cda869",
    },
    "ubuntu": {
        "name": "Ubuntu",
        "BG": "#300a24", "SURFACE": "#3d0f2e", "BORDER": "#4a1438",
        "COMMENT": "#6d4c5f", "BLUE": "#729fcf", "GREEN": "#8ae234",
        "CYAN": "#34e2e2", "FG": "#eeeeec", "YELLOW": "#fce94f",
        "RED": "#ef2929", "PURPLE": "#ad7fa8", "ORANGE": "#fcaf3e",
    },
    "warm_neon": {
        "name": "Warm Neon",
        "BG": "#1a1a1a", "SURFACE": "#252525", "BORDER": "#333333",
        "COMMENT": "#6c6c6c", "BLUE": "#7aa6da", "GREEN": "#99cc99",
        "CYAN": "#66cccc", "FG": "#e0e0e0", "YELLOW": "#ffcc66",
        "RED": "#f2777a", "PURPLE": "#cc99cc", "ORANGE": "#f99157",
    },
    "wild_cherry": {
        "name": "Wild Cherry",
        "BG": "#1a1221", "SURFACE": "#241a2e", "BORDER": "#2e223a",
        "COMMENT": "#6c6f93", "BLUE": "#00d2ff", "GREEN": "#72f1b8",
        "CYAN": "#00d2ff", "FG": "#f0e6ff", "YELLOW": "#ffee00",
        "RED": "#ff006e", "PURPLE": "#bc13fe", "ORANGE": "#ff8500",
    },
    "wombat": {
        "name": "Wombat",
        "BG": "#242424", "SURFACE": "#2e2e2e", "BORDER": "#3a3a3a",
        "COMMENT": "#656565", "BLUE": "#8ac6f2", "GREEN": "#95e454",
        "CYAN": "#8ac6f2", "FG": "#e3e0d7", "YELLOW": "#e9c062",
        "RED": "#e5786d", "PURPLE": "#d787ff", "ORANGE": "#ffad29",
    },
}

THEME_CONFIG = Path("data/theme.json")

def load_theme() -> str:
    if THEME_CONFIG.exists():
        try:
            with open(THEME_CONFIG, 'r') as f:
                data = json.load(f)
                theme = data.get("theme", "tokyo_night")
                if theme in THEMES:
                    return theme
        except:
            pass
    return "tokyo_night"

def save_theme(theme_name: str):
    THEME_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(THEME_CONFIG, 'w') as f:
        json.dump({"theme": theme_name}, f)

class Theme:
    """Dynamic theme - loads from config"""
    _current = load_theme()

    @classmethod
    def _get(cls, key: str) -> str:
        return THEMES[cls._current].get(key, THEMES["tokyo_night"][key])

    @classmethod
    def set_theme(cls, name: str):
        if name in THEMES:
            cls._current = name
            save_theme(name)

    @classmethod
    def get_current_name(cls) -> str:
        return THEMES[cls._current]["name"]

    @classmethod
    def list_themes(cls) -> List[Tuple[str, str]]:
        return [(k, v["name"]) for k, v in THEMES.items()]

    @property
    def BG(self): return self._get("BG")
    @property
    def SURFACE(self): return self._get("SURFACE")
    @property
    def BORDER(self): return self._get("BORDER")
    @property
    def COMMENT(self): return self._get("COMMENT")
    @property
    def BLUE(self): return self._get("BLUE")
    @property
    def GREEN(self): return self._get("GREEN")
    @property
    def CYAN(self): return self._get("CYAN")
    @property
    def FG(self): return self._get("FG")
    @property
    def YELLOW(self): return self._get("YELLOW")
    @property
    def RED(self): return self._get("RED")
    @property
    def PURPLE(self): return self._get("PURPLE")
    @property
    def ORANGE(self): return self._get("ORANGE")

Theme = Theme()

DRAGON = r"""
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@%%*#*%%@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@%##**+*##%%@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@%#*+*+***+++*#%@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@%*++++**+++++++*#%@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@##++++##*++*+*###%@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@%*++++#%%%%%%**%@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@%##++++*#%@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@%%*+++++*#%%@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@%%#*++++++#%@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@%%%%%%%%%#++++*%@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@%*+++++##%%%#*+++*%@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@%*+++++++++*#*++++#%@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@%*++*#%%#*++++++++#%@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@#++#%@@@@%###*##%@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@%#++*%%%%%%%##*%@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@%#*++++++*#%%@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@%%%%%@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@#*##*#%%%%##*#%#%#%@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@#*******#*#***##***#@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@%%%%#*#%%##%%%%%##%@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
"""

os.environ.update({
    'TERM': 'xterm-256color',
    'HOME': '/data/data/com.termux/files/home',
    'SHELL': '/data/data/com.termux/files/usr/bin/bash',
    'PREFIX': '/data/data/com.termux/files/usr',
})

sys.path.insert(0, '/data/data/com.termux/files/usr/lib/python3.12/site-packages')
sys.path.insert(0, '/data/data/com.termux/files/home/.local/lib/python3.12/site-packages')
sys.path.insert(0, str(Path.cwd()))

LOG_FILE = Path("data/hydra.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("hydra")

start_time = time.time()
set_start_time(start_time)

# ═══════════════════════════════════════════════════════════
#  ENHANCED ACCOUNT MANAGER
# ═══════════════════════════════════════════════════════════
ACCOUNTS_FILE = Path("data/accounts.json")
BACKUP_DIR = Path("data/backups")

class AccountManager:
    def __init__(self):
        self.accounts: Dict = {}
        self.load()

    def load(self) -> Dict:
        if ACCOUNTS_FILE.exists():
            try:
                with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.accounts = self._migrate(data)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load accounts: {e}")
                self.accounts = {}
        return self.accounts

    def _migrate(self, data: Dict) -> Dict:
        migrated = {}
        for name, acc in data.items():
            if isinstance(acc, dict):
                if "created_at" not in acc:
                    acc["created_at"] = datetime.now().isoformat()
                if "last_used" not in acc:
                    acc["last_used"] = None
                if "login_method" not in acc:
                    acc["login_method"] = "classic"
                if "favorite" not in acc:
                    acc["favorite"] = False
                migrated[name] = acc
        return migrated

    def save(self):
        try:
            if ACCOUNTS_FILE.exists():
                self._create_backup()
            ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp_file = ACCOUNTS_FILE.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.accounts, f, ensure_ascii=False, indent=2)
            temp_file.replace(ACCOUNTS_FILE)
        except Exception as e:
            logger.error(f"Failed to save accounts: {e}")
            raise

    def _create_backup(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"accounts_{timestamp}.json"
        shutil.copy2(ACCOUNTS_FILE, backup_path)
        backups = sorted(BACKUP_DIR.glob("accounts_*.json"))
        for old in backups[:-10]:
            old.unlink()

    def add(self, name: str, phone: str, session: str,
            username: str = "", first_name: str = "",
            login_method: str = "classic") -> bool:
        if name in self.accounts:
            return False
        self.accounts[name] = {
            "phone": phone, "session": session,
            "username": username, "first_name": first_name,
            "created_at": datetime.now().isoformat(),
            "last_used": None, "login_method": login_method,
            "favorite": False
        }
        self.save()
        return True

    def remove(self, name: str) -> bool:
        if name not in self.accounts:
            return False
        session_file = Path(f"{self.accounts[name]['session']}.session")
        if session_file.exists():
            session_file.unlink()
        del self.accounts[name]
        self.save()
        return True

    def get(self, name: str) -> Optional[Dict]:
        return self.accounts.get(name)

    def list(self) -> List[Tuple[str, Dict]]:
        return list(self.accounts.items())

    def exists(self, name: str) -> bool:
        return name in self.accounts

    def update_last_used(self, name: str):
        if name in self.accounts:
            self.accounts[name]["last_used"] = datetime.now().isoformat()
            self.save()

    def toggle_favorite(self, name: str) -> bool:
        if name in self.accounts:
            self.accounts[name]["favorite"] = not self.accounts[name].get("favorite", False)
            self.save()
            return self.accounts[name]["favorite"]
        return False

account_manager = AccountManager()

# ═══════════════════════════════════════════════════════════
#  MODULE SCANNER (DEBUG)
# ═══════════════════════════════════════════════════════════

class ModuleScanner:
    """Сканирует modules/ и modules/mcub_mods/, парсит метаданные через AST"""

    def __init__(self):
        self.modules: List[Dict] = []
        self.scan()

    def scan(self):
        self.modules = []
        for directory in ["modules", "modules/mcub_mods"]:
            if not os.path.isdir(directory):
                continue
            for fname in sorted(os.listdir(directory)):
                if not fname.endswith(".py") or fname.startswith("_"):
                    continue
                fpath = os.path.join(directory, fname)
                self.modules.append(self._parse_module(fpath, directory))
        # Сортируем: сначала Hydra, потом MCUB, по имени
        self.modules.sort(key=lambda m: (0 if m["type"] == "Hydra" else 1, m["name"].lower()))

    def _parse_module(self, fpath: str, directory: str) -> Dict:
        fname = os.path.basename(fpath)
        name = fname[:-3]
        meta = {
            "file": fpath,
            "dir": directory,
            "fname": fname,
            "name": name,
            "version": "?",
            "author": "unknown",
            "description": "No description",
            "commands": [],
            "type": "MCUB" if "mcub" in directory else "Hydra",
            "size": 0,
            "lines": 0,
        }
        try:
            meta["size"] = os.path.getsize(fpath)
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                code = f.read()
            meta["lines"] = code.count('\n') + 1
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "name" and isinstance(node.value, ast.Constant):
                                meta["name"] = str(node.value.value)
                            elif target.id == "version" and isinstance(node.value, ast.Constant):
                                meta["version"] = str(node.value.value)
                            elif target.id == "author" and isinstance(node.value, ast.Constant):
                                meta["author"] = str(node.value.value)
                            elif target.id == "description":
                                if isinstance(node.value, ast.Constant):
                                    meta["description"] = str(node.value.value)
                                elif isinstance(node.value, ast.Dict):
                                    for k, v in zip(node.value.keys, node.value.values):
                                        if isinstance(k, ast.Constant) and k.value == "ru":
                                            if isinstance(v, ast.Constant):
                                                meta["description"] = str(v.value)
                                                break
                            elif target.id == "modules_help" and isinstance(node.value, ast.Dict):
                                for k in node.value.keys:
                                    if isinstance(k, ast.Constant):
                                        meta["commands"].append(str(k.value))
                elif isinstance(node, ast.FunctionDef):
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call):
                            cmd_name = None
                            if isinstance(dec.func, ast.Name) and dec.func.id == "command":
                                if dec.args and isinstance(dec.args[0], ast.Constant):
                                    cmd_name = str(dec.args[0].value)
                            elif isinstance(dec.func, ast.Attribute) and dec.func.attr == "command":
                                if dec.args and isinstance(dec.args[0], ast.Constant):
                                    cmd_name = str(dec.args[0].value)
                            if cmd_name and cmd_name not in meta["commands"]:
                                meta["commands"].append(cmd_name)
        except Exception:
            pass
        return meta

module_scanner = ModuleScanner()

# ═══════════════════════════════════════════════════════════
#  TABBED UI STATE
# ═══════════════════════════════════════════════════════════
class AppState:
    def __init__(self):
        self.active_tab = 0
        self.selected_account = 0
        self.selected_theme = 0
        self.selected_add_method = 0
        self.selected_backup = 0
        self.selected_module = 0
        self.module_view = "list"      # "list" | "bat"
        self.current_module = None     # dict метаданных
        self.module_bat_scroll = 0
        self.notifications = deque(maxlen=20)
        self.running = True
        self.use_web = False
        self.result = None
        self.need_refresh = True
        self.in_dialog = False
        self.add_flow_step = 0
        self.add_data = {}
        self.add_use_qr = False
        self.action_queue = queue.Queue()
        self.input_buffer = ""

    def add_notification(self, msg, level="info"):
        self.notifications.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "msg": msg,
            "level": level
        })

STATE = AppState()

# ═══════════════════════════════════════════════════════════
#  TERMINAL INPUT CONTROLLER (raw mode + pause/resume)
# ═══════════════════════════════════════════════════════════

class TerminalInput:
    """Управляет вводом в raw mode. Может приостанавливаться для Prompt.ask"""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._old_settings = None
        self._lock = threading.Lock()

    def start(self):
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._paused.set()
        if self._thread:
            self._thread.join(timeout=1)
        self._restore()

    def pause(self):
        """Приостановить raw mode и восстановить терминал"""
        self._paused.set()
        time.sleep(0.05)
        self._restore()

    def resume(self):
        """Возобновить raw mode"""
        with self._lock:
            self._old_settings = termios.tcgetattr(sys.stdin.fileno())
            new = termios.tcgetattr(sys.stdin.fileno())
            new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
            new[6][termios.VMIN] = 0
            new[6][termios.VTIME] = 1
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, new)
        self._paused.clear()

    def _restore(self):
        with self._lock:
            if self._old_settings:
                try:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)
                except Exception:
                    pass

    def _loop(self):
        self.resume()
        try:
            while not self._stop.is_set():
                if self._paused.is_set():
                    time.sleep(0.05)
                    continue
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue
                try:
                    char = sys.stdin.read(1)
                except Exception:
                    continue
                if not char:
                    continue
                self._handle_char(char)
        finally:
            self._restore()

    def _handle_char(self, char: str):
        # Quit
        if char == 'q' and STATE.active_tab != 1:
            STATE.action_queue.put(('quit', None))
        # Refresh
        elif char == 'r':
            STATE.action_queue.put(('refresh', None))
        # Tab switching (1-6)
        elif char in '123456':
            tab_idx = int(char) - 1
            if tab_idx <= 5:
                STATE.action_queue.put(('tab', tab_idx))
        # Vim navigation
        elif char == 'k':
            STATE.action_queue.put(('up', None))
        elif char == 'j':
            STATE.action_queue.put(('down', None))
        elif char == 'g':
            STATE.action_queue.put(('first', None))
        elif char == 'G':
            STATE.action_queue.put(('last', None))
        elif char == 'l':
            STATE.action_queue.put(('enter', None))
        elif char == 'h':
            STATE.action_queue.put(('back', None))
        # Arrow keys
        elif char == '\x1b':
            try:
                seq = sys.stdin.read(2)
            except Exception:
                return
            if seq == '[A':
                STATE.action_queue.put(('up', None))
            elif seq == '[B':
                STATE.action_queue.put(('down', None))
            elif seq == '[C':
                STATE.action_queue.put(('enter', None))
            elif seq == '[D':
                STATE.action_queue.put(('back', None))
        # Enter
        elif char in ('\n', '\r'):
            STATE.action_queue.put(('enter', None))
        # Actions
        elif char == 'd':
            STATE.action_queue.put(('delete', None))
        elif char == 'f':
            STATE.action_queue.put(('favorite', None))
        elif char == 'b':
            STATE.action_queue.put(('backup', None))
        elif char == 'L':
            STATE.action_queue.put(('view_logs', None))
        elif char == 'c':
            STATE.action_queue.put(('clear_logs', None))
        elif char == 'e' and STATE.active_tab == 4 and STATE.module_view == "bat":
            STATE.action_queue.put(('module_edit', None))

terminal_input = TerminalInput()

# ═══════════════════════════════════════════════════════════
#  UI COMPONENTS
# ═══════════════════════════════════════════════════════════
class UI:
    @staticmethod
    def clear():
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def make_header(title: str, subtitle: str = ""):
        tabs = ["Accounts", "Add Acc", "Themes", "Backup", "Modules", "About"]
        tab_str = ""
        for i, t in enumerate(tabs):
            if i == STATE.active_tab:
                tab_str += f"[bold {Theme.BG} on {Theme.BLUE}] {i+1}:{t} [/]"
            else:
                tab_str += f"[{Theme.COMMENT}] {i+1}:{t} [/]"

        subtitle_part = f"  [dim {Theme.COMMENT}]{subtitle}[/]" if subtitle else ""

        return Panel(
            Text.from_markup(
                f"[bold {Theme.BLUE}][/][bold {Theme.BG} on {Theme.BLUE}]  ⚡ HYDRA v4.1 [/]"
                f"[bold {Theme.BLUE}][/]  {tab_str}{subtitle_part}"
            ),
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        )

    @staticmethod
    def make_footer():
        accounts = account_manager.list()
        online_count = sum(1 for _, d in accounts if Path(f"{d['session']}.session").exists())
        mod_count = len(module_scanner.modules)
        return Panel(
            Text.from_markup(
                f"[{Theme.COMMENT}]TAB[/][{Theme.BLUE}]:1-6  [/]"
                f"[{Theme.COMMENT}]j/k[/][{Theme.BLUE}]:nav  [/]"
                f"[{Theme.COMMENT}]l/ENTER[/][{Theme.BLUE}]:select  [/]"
                f"[{Theme.COMMENT}]h[/][{Theme.BLUE}]:back  [/]"
                f"[{Theme.COMMENT}]r[/][{Theme.BLUE}]:refresh  [/]"
                f"[{Theme.COMMENT}]q[/][{Theme.BLUE}]:quit  [/]"
                f"[{Theme.COMMENT}]│  [/]"
                f"[{Theme.GREEN}]●[/][{Theme.COMMENT}] {online_count}/{len(accounts)} ready[/]"
                f"[{Theme.COMMENT}] │  Mods:[/][{Theme.YELLOW}] {mod_count}[/]"
                f"[{Theme.COMMENT}] │  Theme:[/][{Theme.BLUE}] {Theme.get_current_name()}[/]"
            ),
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        )

    @staticmethod
    def make_notifications():
        if not STATE.notifications:
            return Panel(
                f"[{Theme.COMMENT}]No notifications[/]",
                title=f"[{Theme.YELLOW}] 󰵙 [/]",
                border_style=Theme.BORDER,
                box=SIMPLE,
                padding=(0, 1),
                height=3
            )

        lines = []
        for n in list(STATE.notifications)[-3:]:
            color = {"info": Theme.BLUE, "success": Theme.GREEN,
                     "warning": Theme.YELLOW, "error": Theme.RED}.get(n["level"], Theme.BLUE)
            lines.append(f"[{color}]{n['time']}[/] [{color}]{n['msg']}[/]")

        return Panel(
            "\n".join(lines),
            title=f"[{Theme.YELLOW}] 󰵙 Notifications [/]",
            title_align="left",
            border_style=Theme.BORDER,
            box=SIMPLE,
            padding=(0, 1),
            height=5
        )

    @staticmethod
    def info(text: str):
        console.print(f"[dim {Theme.COMMENT}]ℹ {text}[/]")

    @staticmethod
    def success(text: str):
        console.print(f"[bold {Theme.GREEN}]✓ {text}[/]")

    @staticmethod
    def warning(text: str):
        console.print(f"[bold {Theme.YELLOW}]⚠ {text}[/]")

    @staticmethod
    def error(text: str):
        console.print(f"[bold {Theme.RED}]✗ {text}[/]")

    @staticmethod
    def prompt_symbol() -> str:
        return f"[bold {Theme.BLUE}]❯[/]"


# ═══════════════════════════════════════════════════════════
#  TAB 1: ACCOUNTS DASHBOARD
# ═══════════════════════════════════════════════════════════

def make_accounts_tab():
    accounts = account_manager.list()

    if not accounts:
        return Group(
            UI.make_notifications(),
            Panel(
                f"[bold {Theme.FG}]No accounts yet[/]\n"
                f"[{Theme.COMMENT}]Go to tab [bold]2[/] (Add Account) to add your first account[/]",
                box=DOUBLE_EDGE,
                border_style=Theme.BORDER,
                padding=(2, 4),
                height=10
            )
        )

    cards = []
    for i, (name, data) in enumerate(accounts):
        session_exists = Path(f"{data['session']}.session").exists()
        is_selected = (i == STATE.selected_account)

        if session_exists:
            status_icon = f"[bold {Theme.GREEN}]●[/]"
            status_text = f"[bold {Theme.GREEN}]READY[/]"
            border_color = Theme.GREEN if is_selected else Theme.BORDER
        else:
            status_icon = f"[bold {Theme.RED}]●[/]"
            status_text = f"[bold {Theme.RED}]MISSING[/]"
            border_color = Theme.RED if is_selected else Theme.BORDER

        star = f"[bold {Theme.YELLOW}]★[/]" if data.get("favorite") else f"[dim {Theme.BORDER}]☆[/]"

        method_colors = {"qr": Theme.CYAN, "classic": Theme.COMMENT}
        method_badge = f"[bold {method_colors.get(data.get('login_method', 'classic'), Theme.COMMENT)}]" \
                       f"{data.get('login_method', 'classic').upper()}[/]"

        select_marker = f"[bold {Theme.BLUE}]▶[/] " if is_selected else "  "

        content = Group(
            Text.from_markup(
                f"{select_marker}{status_icon}  [bold {Theme.FG}]{name}[/]  {star}"
            ),
            Text.from_markup(
                f"     [{Theme.COMMENT}]phone[/]  [{Theme.FG}]{data.get('phone', '—')}[/]"
            ),
            Text.from_markup(
                f"     [{Theme.COMMENT}]user[/]   [@{data.get('username', '—')}]({Theme.FG})"
            ),
            Text.from_markup(
                f"     [{Theme.COMMENT}]method[/] {method_badge}"
            ),
            Text.from_markup(
                f"     [{Theme.COMMENT}]since[/]  [{Theme.COMMENT}]{data.get('created_at', '—')[:10]}[/]"
            ),
            Align.right(Text.from_markup(status_text))
        )

        cards.append(Panel(
            content,
            box=ROUNDED,
            border_style=border_color,
            padding=(1, 2),
            height=10
        ))

    selected_name = accounts[STATE.selected_account][0] if accounts else None
    action_panel = Panel(
        Text.from_markup(
            f"[{Theme.COMMENT}]Selected:[/] [bold {Theme.BLUE}]{selected_name}[/]  │  "
            f"[{Theme.COMMENT}]l/ENTER[/][{Theme.BLUE}]:launch  [/]"
            f"[{Theme.COMMENT}]d[/][{Theme.BLUE}]:delete  [/]"
            f"[{Theme.COMMENT}]f[/][{Theme.BLUE}]:favorite  [/]"
            f"[{Theme.COMMENT}]b[/][{Theme.BLUE}]:backup[/]"
        ),
        box=SIMPLE,
        border_style=Theme.SURFACE,
        padding=(0, 1),
        height=3
    ) if selected_name else None

    result = [UI.make_notifications(), Columns(cards, equal=True, expand=True)]
    if action_panel:
        result.append(action_panel)

    return Group(*result)


# ═══════════════════════════════════════════════════════════
#  TAB 2: ADD ACCOUNT
# ═══════════════════════════════════════════════════════════

def make_add_account_tab():
    if STATE.add_flow_step > 0:
        return make_add_account_flow()

    methods = [
        ("classic", "📱 Classic Login", "Phone number + SMS code", Theme.BLUE, "Most reliable method"),
        ("qr", "📷 QR-Code Login", "Scan with Telegram app", Theme.CYAN, "No phone number needed"),
    ]

    cards = []
    for i, (key, title, desc, color, hint) in enumerate(methods):
        is_selected = (i == STATE.selected_add_method)
        border = color if is_selected else Theme.BORDER
        marker = f"[bold {Theme.BLUE}]▶[/] " if is_selected else "  "

        cards.append(Panel(
            Text.from_markup(
                f"{marker}[bold {color}]{title}[/]\n\n"
                f"  [{Theme.COMMENT}]{desc}[/]\n"
                f"  [{Theme.COMMENT}]{hint}[/]\n\n"
                f"  [dim]{'Press l or ENTER to select' if is_selected else ''}[/]"
            ),
            box=DOUBLE_EDGE if is_selected else ROUNDED,
            border_style=border,
            padding=(1, 2),
            height=12
        ))

    return Group(
        UI.make_notifications(),
        Panel(
            f"[bold {Theme.BLUE}]➕ Add New Account[/]  [dim](j/k to choose, l/ENTER to confirm)[/]",
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        ),
        Columns(cards, equal=True, expand=True)
    )


def make_add_account_flow():
    step = STATE.add_flow_step

    if step == 1:
        return Group(
            UI.make_notifications(),
            Panel(
                f"[bold {Theme.BLUE}]➕ Add Account — Step 1/3[/]",
                box=SIMPLE,
                border_style=Theme.SURFACE,
                padding=(0, 1),
                height=3
            ),
            Panel(
                Text.from_markup(
                    f"[{Theme.COMMENT}]Enter a name for this account[/]\n"
                    f"[{Theme.COMMENT}]Example: Main, Work, Backup[/]\n\n"
                    f"[{Theme.COMMENT}]Type the name and press ENTER[/]"
                ),
                box=ROUNDED,
                border_style=Theme.BLUE,
                padding=(2, 4),
                height=8
            )
        )
    elif step == 2:
        method = "QR" if STATE.add_use_qr else "Classic"
        return Group(
            UI.make_notifications(),
            Panel(
                f"[bold {Theme.BLUE}]➕ Add Account — Step 2/3[/]  [dim]({method})[/]",
                box=SIMPLE,
                border_style=Theme.SURFACE,
                padding=(0, 1),
                height=3
            ),
            Panel(
                Text.from_markup(
                    f"[{Theme.COMMENT}]Account:[/] [bold {Theme.FG}]{STATE.add_data.get('name', '?')}[/]\n\n"
                    f"[{Theme.COMMENT}]Enter phone number[/]\n"
                    f"[{Theme.COMMENT}]Format: +79XXXXXXXXX[/]\n\n"
                    f"[{Theme.COMMENT}]Type and press ENTER[/]"
                ),
                box=ROUNDED,
                border_style=Theme.BLUE,
                padding=(2, 4),
                height=10
            )
        )
    elif step == 3:
        return Group(
            UI.make_notifications(),
            Panel(
                f"[bold {Theme.BLUE}]➕ Add Account — Step 3/3[/]",
                box=SIMPLE,
                border_style=Theme.SURFACE,
                padding=(0, 1),
                height=3
            ),
            Panel(
                Text.from_markup(
                    f"[{Theme.COMMENT}]Account:[/] [bold {Theme.FG}]{STATE.add_data.get('name', '?')}[/]\n"
                    f"[{Theme.COMMENT}]Phone:[/] [bold {Theme.FG}]{STATE.add_data.get('phone', '?')}[/]\n\n"
                    f"[{Theme.COMMENT}]Enter SMS code[/]\n"
                    f"[{Theme.COMMENT}]Sent to your phone[/]\n\n"
                    f"[{Theme.COMMENT}]Type code and press ENTER[/]"
                ),
                box=ROUNDED,
                border_style=Theme.YELLOW,
                padding=(2, 4),
                height=11
            )
        )

    return make_add_account_tab()


# ═══════════════════════════════════════════════════════════
#  TAB 3: THEME SELECTOR
# ═══════════════════════════════════════════════════════════

def make_themes_tab():
    theme_cards = []
    themes_list = Theme.list_themes()
    for i, (key, name) in enumerate(themes_list):
        is_selected = (i == STATE.selected_theme)
        colors = THEMES[key]

        preview = ""
        for c in [colors["BLUE"], colors["GREEN"], colors["RED"], colors["YELLOW"], colors["PURPLE"]]:
            preview += f"[bold {c}]█[/]"

        marker = f"[bold {Theme.BLUE}]▶[/] " if is_selected else "  "
        border = Theme.BLUE if is_selected else Theme.BORDER

        theme_cards.append(Panel(
            Text.from_markup(
                f"{marker}[bold {Theme.FG}]{name}[/]\n"
                f"  {preview}\n"
                f"  [dim {Theme.COMMENT}]{key}[/]"
            ),
            box=DOUBLE_EDGE if is_selected else ROUNDED,
            border_style=border,
            padding=(1, 2),
            height=5
        ))

    current = Theme.get_current_name()
    return Group(
        UI.make_notifications(),
        Panel(
            f"[bold {Theme.BLUE}]🎨 Theme Selector[/]  [dim](j/k to navigate, l/ENTER to apply)[/]",
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        ),
        Columns(theme_cards, equal=True, expand=True),
        Panel(
            f"[{Theme.COMMENT}]Current theme:[/] [bold {Theme.BLUE}]{current}[/]",
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        )
    )


# ═══════════════════════════════════════════════════════════
#  TAB 4: BACKUP & LOGS
# ═══════════════════════════════════════════════════════════

def make_backup_logs_tab():
    accounts = account_manager.list()
    total = len(accounts)
    backups = sorted(BACKUP_DIR.glob("accounts_*.json")) if BACKUP_DIR.exists() else []
    backup_count = len(backups)

    backup_items = []
    if backups:
        for i, bp in enumerate(backups[-5:]):
            size = bp.stat().st_size
            size_str = f"{size/1024:.1f} KB" if size > 1024 else f"{size} B"
            date_str = bp.stem.replace("accounts_", "")
            backup_items.append(f"  [{Theme.BLUE}]{date_str}[/]  [{Theme.COMMENT}]{size_str}[/]")
    else:
        backup_items.append(f"  [{Theme.COMMENT}]No backups yet[/]")

    log_size = 0
    log_lines = 0
    if LOG_FILE.exists():
        log_size = LOG_FILE.stat().st_size
        try:
            with open(LOG_FILE, 'r') as f:
                log_lines = sum(1 for _ in f)
        except:
            pass

    log_size_str = f"{log_size/1024:.1f} KB" if log_size > 1024 else f"{log_size} B"

    stats_table = Table(
        show_header=True,
        header_style=f"bold {Theme.BLUE}",
        border_style=Theme.BORDER,
        box=SIMPLE
    )
    stats_table.add_column("Metric", width=20)
    stats_table.add_column("Value", width=15)
    stats_table.add_row("Total Accounts", f"[bold {Theme.FG}]{total}[/]")
    stats_table.add_row("Backups", f"[bold {Theme.PURPLE}]{backup_count}[/]")
    stats_table.add_row("Log Size", f"[bold {Theme.YELLOW}]{log_size_str}[/]")
    stats_table.add_row("Log Lines", f"[bold {Theme.YELLOW}]{log_lines}[/]")
    stats_table.add_row("MCUB Ready", f"[bold {Theme.GREEN if MCUB_READY else Theme.RED}]{'YES' if MCUB_READY else 'NO'}[/]")
    stats_table.add_row("Log File", f"[{Theme.COMMENT}]{LOG_FILE}[/]")

    actions = Panel(
        Text.from_markup(
            f"[{Theme.COMMENT}]Actions:[/]\n"
            f"  [{Theme.BLUE}]b[/] [{Theme.COMMENT}]Create backup now[/]\n"
            f"  [{Theme.BLUE}]L[/] [{Theme.COMMENT}]View last 20 log lines[/]\n"
            f"  [{Theme.BLUE}]c[/] [{Theme.COMMENT}]Clear old logs[/]"
        ),
        border_style=Theme.BORDER,
        box=SIMPLE,
        padding=(1, 2)
    )

    backups_panel = Panel(
        "\n".join(backup_items),
        title=f"[{Theme.PURPLE}] 📦 Recent Backups [/]",
        title_align="left",
        border_style=Theme.BORDER,
        box=SIMPLE,
        padding=(1, 2)
    )

    return Group(
        UI.make_notifications(),
        Panel(
            f"[bold {Theme.BLUE}]💾 Backup & Logs[/]",
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        ),
        stats_table,
        backups_panel,
        actions
    )


# ═══════════════════════════════════════════════════════════
#  TAB 5: MODULES (DEBUG)
# ═══════════════════════════════════════════════════════════

def make_modules_tab():
    if STATE.module_view == "bat" and STATE.current_module:
        return make_module_bat_view()

    mods = module_scanner.modules
    if not mods:
        return Group(
            UI.make_notifications(),
            Panel(
                f"[bold {Theme.FG}]No modules found[/]\n"
                f"[{Theme.COMMENT}]Check folders: modules/ and modules/mcub_mods/[/]",
                box=DOUBLE_EDGE,
                border_style=Theme.BORDER,
                padding=(2, 4),
                height=10
            )
        )

    cards = []
    for i, mod in enumerate(mods):
        is_selected = (i == STATE.selected_module)
        border = Theme.BLUE if is_selected else Theme.BORDER
        marker = f"[bold {Theme.BLUE}]▶[/] " if is_selected else "  "

        type_color = Theme.GREEN if mod["type"] == "Hydra" else Theme.CYAN
        cmd_count = len(mod["commands"])
        size_str = f"{mod['size']/1024:.1f} KB" if mod['size'] > 1024 else f"{mod['size']} B"

        content = Text.from_markup(
            f"{marker}[bold {Theme.FG}]{mod['name']}[/]  "
            f"[bold {type_color}]{mod['type']}[/]\n"
            f"  [{Theme.COMMENT}]ver[/]   [{Theme.FG}]{mod['version']}[/]\n"
            f"  [{Theme.COMMENT}]auth[/]  [{Theme.FG}]{mod['author']}[/]\n"
            f"  [{Theme.COMMENT}]cmds[/]  [{Theme.YELLOW}]{cmd_count}[/]\n"
            f"  [{Theme.COMMENT}]size[/]  [{Theme.COMMENT}]{size_str} | {mod['lines']} lines[/]\n"
            f"  [{Theme.COMMENT}]file[/]  [{Theme.COMMENT}]{mod['fname']}[/]"
        )

        cards.append(Panel(
            content,
            box=DOUBLE_EDGE if is_selected else ROUNDED,
            border_style=border,
            padding=(1, 2),
            height=9
        ))

    selected_mod = mods[STATE.selected_module] if mods else None
    action_panel = None
    if selected_mod:
        action_panel = Panel(
            Text.from_markup(
                f"[{Theme.COMMENT}]Selected:[/] [bold {Theme.BLUE}]{selected_mod['name']}[/]  │  "
                f"[{Theme.COMMENT}]l/ENTER[/][{Theme.BLUE}]:bat view  [/]"
                f"[{Theme.COMMENT}]e[/][{Theme.BLUE}]:edit (nano)  [/]"
                f"[{Theme.COMMENT}]r[/][{Theme.BLUE}]:rescan[/]"
            ),
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        )

    result = [UI.make_notifications()]
    # Разбиваем на колонки по 2-3 в ряд
    if len(cards) <= 4:
        result.append(Columns(cards, equal=True, expand=True))
    else:
        # Показываем окно из 6 модулей вокруг selected
        start = max(0, STATE.selected_module - 2)
        end = min(len(cards), start + 6)
        if end - start < 6:
            start = max(0, end - 6)
        visible = cards[start:end]
        result.append(Columns(visible, equal=True, expand=True))
        if len(cards) > 6:
            result.append(Panel(
                f"[{Theme.COMMENT}]Showing {start+1}-{end} of {len(cards)}  │  j/k to scroll[/]",
                box=SIMPLE, border_style=Theme.SURFACE, padding=(0,1), height=2
            ))
    if action_panel:
        result.append(action_panel)

    return Group(*result)


def make_module_bat_view():
    mod = STATE.current_module
    if not mod:
        STATE.module_view = "list"
        return make_modules_tab()

    try:
        with open(mod["file"], 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
    except Exception as e:
        code = f"# Error reading file: {e}"

    # Прокрутка: показываем окно в 40 строк
    lines = code.split('\n')
    total_lines = len(lines)
    scroll = STATE.module_bat_scroll
    visible_lines = lines[scroll:scroll + 40]
    visible_code = '\n'.join(visible_lines)

    syntax = Syntax(
        visible_code,
        "python",
        theme="monokai",
        line_numbers=True,
        start_line=scroll + 1,
        word_wrap=False,
        background_color=Theme.BG,
    )

    header = Panel(
        Text.from_markup(
            f"[bold {Theme.BLUE}]📦 {mod['name']}[/] "
            f"[dim]v{mod['version']}[/] | "
            f"[dim]{mod['author']}[/] | "
            f"[bold {Theme.GREEN if mod['type']=='Hydra' else Theme.CYAN}]{mod['type']}[/]"
        ),
        box=SIMPLE,
        border_style=Theme.BLUE,
        padding=(0, 1),
        height=3
    )

    info = (
        f"[{Theme.COMMENT}]File:[/]     [{Theme.FG}]{mod['file']}[/]\n"
        f"[{Theme.COMMENT}]Lines:[/]    [{Theme.FG}]{mod['lines']}[/]\n"
        f"[{Theme.COMMENT}]Size:[/]     [{Theme.FG}]{mod['size']} B[/]\n"
        f"[{Theme.COMMENT}]Commands:[/] [{Theme.YELLOW}]{', '.join(mod['commands']) if mod['commands'] else 'none'}[/]\n"
        f"[{Theme.COMMENT}]Desc:[/]     [{Theme.FG}]{mod['description'][:120]}[/]"
    )
    info_panel = Panel(info, box=SIMPLE, border_style=Theme.BORDER, padding=(0, 1), height=6)

    code_panel = Panel(
        syntax,
        box=ROUNDED,
        border_style=Theme.BORDER,
        padding=(0, 0),
        height=42
    )

    scroll_hint = f"[{Theme.COMMENT}]Line {scroll+1}-{min(scroll+40, total_lines)} of {total_lines}[/]"
    actions = Panel(
        Text.from_markup(
            f"[{Theme.COMMENT}]h[/][{Theme.BLUE}]:back  [/]"
            f"[{Theme.COMMENT}]↑/k[/][{Theme.BLUE}]:scroll up  [/]"
            f"[{Theme.COMMENT}]↓/j[/][{Theme.BLUE}]:scroll down  [/]"
            f"[{Theme.COMMENT}]e[/][{Theme.BLUE}]:edit (nano)  [/]"
            f"[{Theme.COMMENT}]r[/][{Theme.BLUE}]:refresh[/]  {scroll_hint}"
        ),
        box=SIMPLE,
        border_style=Theme.SURFACE,
        padding=(0, 1),
        height=3
    )

    return Group(header, info_panel, code_panel, actions)


# ═══════════════════════════════════════════════════════════
#  TAB 6: ABOUT / INFO
# ═══════════════════════════════════════════════════════════

def make_about_tab():
    uptime = time.time() - start_time
    hours, rem = divmod(int(uptime), 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    info_table = Table(
        show_header=False,
        border_style=Theme.BORDER,
        box=SIMPLE
    )
    info_table.add_column("Key", style=f"bold {Theme.COMMENT}", width=20)
    info_table.add_column("Value", style=Theme.FG)

    info_table.add_row("Version", f"[bold {Theme.BLUE}]Hydra v4.1[/]")
    info_table.add_row("Edition", f"[bold {Theme.CYAN}]Cython + MCUB + Debug[/]")
    info_table.add_row("Python", f"[{Theme.FG}]{sys.version.split()[0]}[/]")
    info_table.add_row("Platform", f"[{Theme.FG}]{sys.platform}[/]")
    info_table.add_row("Uptime", f"[bold {Theme.GREEN}]{uptime_str}[/]")
    info_table.add_row("MCUB", f"[bold {Theme.GREEN if MCUB_READY else Theme.RED}]{'Ready' if MCUB_READY else 'Not installed'}[/]")

    shortcuts = Panel(
        Text.from_markup(
            f"[{Theme.COMMENT}]Keyboard shortcuts:[/]\n"
            f"  [{Theme.BLUE}]1-6[/] [{Theme.COMMENT}]Switch tabs[/]\n"
            f"  [{Theme.BLUE}]j/k[/]  [{Theme.COMMENT}]Navigate down/up[/]\n"
            f"  [{Theme.BLUE}]g/G[/]  [{Theme.COMMENT}]Go to first/last item[/]\n"
            f"  [{Theme.BLUE}]l/ENTER[/] [{Theme.COMMENT}]Select / Launch / Confirm[/]\n"
            f"  [{Theme.BLUE}]h[/]   [{Theme.COMMENT}]Go back / Cancel[/]\n"
            f"  [{Theme.BLUE}]d[/]   [{Theme.COMMENT}]Delete account[/]\n"
            f"  [{Theme.BLUE}]f[/]   [{Theme.COMMENT}]Toggle favorite[/]\n"
            f"  [{Theme.BLUE}]b[/]   [{Theme.COMMENT}]Create backup[/]\n"
            f"  [{Theme.BLUE}]L[/]   [{Theme.COMMENT}]View logs[/]\n"
            f"  [{Theme.BLUE}]c[/]   [{Theme.COMMENT}]Clear logs[/]\n"
            f"  [{Theme.BLUE}]r[/]   [{Theme.COMMENT}]Refresh[/]\n"
            f"  [{Theme.BLUE}]q[/]   [{Theme.COMMENT}]Quit[/]"
        ),
        border_style=Theme.BORDER,
        box=SIMPLE,
        padding=(1, 2)
    )

    return Group(
        UI.make_notifications(),
        Panel(
            f"[bold {Theme.BLUE}]ℹ About Hydra[/]",
            box=SIMPLE,
            border_style=Theme.SURFACE,
            padding=(0, 1),
            height=3
        ),
        Panel(
            f"[bold {Theme.BLUE}]{DRAGON}[/]",
            border_style=Theme.BORDER,
            box=SIMPLE,
            padding=(1, 2)
        ),
        info_table,
        shortcuts
    )


# ═══════════════════════════════════════════════════════════
#  LAYOUT BUILDER
# ═══════════════════════════════════════════════════════════

def make_layout():
    header = UI.make_header("HYDRA v4.1", "Account Manager + Debug")
    footer = UI.make_footer()

    tabs = [make_accounts_tab, make_add_account_tab, make_themes_tab,
            make_backup_logs_tab, make_modules_tab, make_about_tab]
    content = tabs[STATE.active_tab]()

    return Group(header, content, footer)


# ═══════════════════════════════════════════════════════════
#  LOGIN FUNCTIONS
# ═══════════════════════════════════════════════════════════

def _relax_protection(client) -> None:
    """Telethon-MCUB стартует в protection mode 'strict', который блочит
    account.GetPasswordRequest — без него вход с 2FA невозможен.
    'safe' по-прежнему блочит удаление аккаунта/сброс сессий, но вход пускает."""
    if hasattr(client, "set_protection_mode"):
        try:
            client.set_protection_mode("safe")
        except Exception:
            pass

def generate_qr_terminal(url: str) -> bool:
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)

        console.print()
        console.print(Panel(
            f"[bold {Theme.FG}]Scan this QR code in Telegram[/]",
            box=ROUNDED,
            border_style=Theme.CYAN,
            padding=(1, 2)
        ))
        qr.print_ascii(invert=True)
        return True
    except ImportError:
        UI.warning("qrcode not installed: pip install qrcode[pil]")
        console.print(f"[{Theme.CYAN}]{url}[/]")
        return False


async def login_qr_code(client, phone=None):
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        return me

    qr_login = await client.qr_login()

    for attempt in range(1, 4):
        UI.clear()
        console.print(f"[bold {Theme.BLUE}]{DRAGON}[/]")
        console.print(f"[bold {Theme.CYAN}]📷 QR LOGIN[/]  [dim {Theme.COMMENT}]Attempt {attempt}/3[/]")
        console.print()

        url = qr_login.url
        console.print(f"[dim {Theme.COMMENT}]URL:[/] [link={url}]{url[:50]}...[/link]")
        console.print()

        if not generate_qr_terminal(url):
            console.print(f"[{Theme.CYAN}]{url}[/]")

        console.print()
        panel = Panel(
            f"[bold {Theme.YELLOW}]⏳ Waiting for scan... 30s[/]",
            box=ROUNDED,
            border_style=Theme.YELLOW
        )
        with Live(
            panel,
            refresh_per_second=1,
            console=console
        ) as live:
            try:
                me = await qr_login.wait(30)
                if me:
                    live.update(Panel(
                        f"[bold {Theme.GREEN}]✓ Login successful: {me.first_name}[/]",
                        box=ROUNDED,
                        border_style=Theme.GREEN
                    ))
                    await asyncio.sleep(1)
                    return me
            except asyncio.TimeoutError:
                live.update(Panel(
                    f"[bold {Theme.YELLOW}]⌛ QR expired, refreshing...[/]",
                    box=ROUNDED,
                    border_style=Theme.YELLOW
                ))
                await qr_login.recreate()
                await asyncio.sleep(1)
            except SessionPasswordNeededError:
                live.stop()
                console.print(Rule(f"[bold {Theme.YELLOW}]2FA REQUIRED[/]", style=Theme.BORDER))
                password = Prompt.ask(
                    f"[bold {Theme.YELLOW}]🔐 2FA Password[/]",
                    password=True
                )
                await client.sign_in(password=password)
                me = await client.get_me()
                return me
            except Exception as e:
                live.stop()
                UI.error(f"Login error: {e}")
                return None

    UI.error("Failed to login via QR after 3 attempts")
    return None


async def login_new_account(client, phone):
    await client.connect()

    if not await client.is_user_authorized():
        try:
            await client.send_code_request(phone)
            UI.success(f"Code sent to {phone}")
        except Exception as e:
            UI.error(f"Failed to send code: {e}")
            return None

    for attempt in range(1, 4):
        UI.clear()
        console.print(f"[bold {Theme.BLUE}]{DRAGON}[/]")
        console.print(f"[bold {Theme.BLUE}]📱 CLASSIC LOGIN[/]  [dim {Theme.COMMENT}]Attempt {attempt}/3[/]")
        console.print()

        console.print(Panel(
            f"[bold {Theme.BLUE}]Enter verification code[/]\n"
            f"[dim {Theme.COMMENT}]Sent to: {phone}[/]",
            box=HEAVY_EDGE,
            border_style=Theme.BLUE,
            padding=(1, 2)
        ))

        code = Prompt.ask(UI.prompt_symbol() + f" [bold {Theme.FG}]Code[/]")

        try:
            await client.sign_in(phone=phone, code=code)
            me = await client.get_me()
            UI.success(f"Welcome, {me.first_name}!")
            return me

        except SessionPasswordNeededError:
            console.print(Rule(f"[bold {Theme.YELLOW}]2FA REQUIRED[/]", style=Theme.BORDER))
            password = Prompt.ask(
                UI.prompt_symbol() + f" [bold {Theme.YELLOW}]🔐 2FA Password[/]",
                password=True
            )
            await client.sign_in(password=password)
            me = await client.get_me()
            UI.success(f"Welcome, {me.first_name}!")
            return me

        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            UI.error("Invalid or expired code!")
            await asyncio.sleep(1)

        except Exception as e:
            UI.error(f"{e}")
            return None

    UI.error("Attempts exhausted")
    return None


def get_client_kwargs(session_name, proxy_enabled=False):
    kwargs = {
        "device_model": "Hydra Dragon X1",
        "system_version": "Android 14",
        "app_version": "Hydra 4.1 MCUB"
    }
    if proxy_enabled and hasattr(config, 'PROXY') and config.PROXY:
        kwargs["proxy"] = (config.PROXY["addr"], config.PROXY["port"], config.PROXY["secret"])
        kwargs["connection"] = connection.ConnectionTcpMTProxyIntermediate
    return kwargs


# ═══════════════════════════════════════════════════════════
#  ACCOUNT ACTIONS
# ═══════════════════════════════════════════════════════════

async def action_launch_account():
    accounts = account_manager.list()
    if not accounts or STATE.selected_account >= len(accounts):
        STATE.add_notification("No account selected", "warning")
        return

    name, data = accounts[STATE.selected_account]
    session_file = Path(f"{data['session']}.session")

    if not session_file.exists():
        STATE.add_notification(f"Session missing for {name}", "error")
        return

    account_manager.update_last_used(name)
    STATE.result = (name, data)
    STATE.running = False
    STATE.add_notification(f"Launching {name}...", "success")


async def action_delete_account():
    accounts = account_manager.list()
    if not accounts or STATE.selected_account >= len(accounts):
        STATE.add_notification("No account selected", "warning")
        return

    name, data = accounts[STATE.selected_account]

    UI.clear()
    console.print(f"[bold {Theme.BLUE}]{DRAGON}[/]")
    console.print()

    if Confirm.ask(
        f"[bold {Theme.RED}]Delete account '{name}' and its session?[/]",
        default=False
    ):
        account_manager.remove(name)
        STATE.selected_account = max(0, STATE.selected_account - 1)
        STATE.add_notification(f"Account '{name}' deleted", "success")
    else:
        STATE.add_notification("Delete cancelled", "info")


async def action_toggle_favorite():
    accounts = account_manager.list()
    if not accounts or STATE.selected_account >= len(accounts):
        STATE.add_notification("No account selected", "warning")
        return

    name, _ = accounts[STATE.selected_account]
    is_fav = account_manager.toggle_favorite(name)
    icon = "★" if is_fav else "☆"
    STATE.add_notification(f"{icon} Account '{name}' {'starred' if is_fav else 'unstarred'}", "success")


async def action_backup():
    account_manager._create_backup()
    backups = len(list(BACKUP_DIR.glob("accounts_*.json")))
    STATE.add_notification(f"Backup created! ({backups} total)", "success")


async def action_view_logs():
    if not LOG_FILE.exists():
        STATE.add_notification("Log file not found", "warning")
        return

    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        last_lines = lines[-20:] if len(lines) > 20 else lines

        UI.clear()
        console.print(f"[bold {Theme.BLUE}]📋 Last Log Entries[/]")
        console.print(Rule(style=Theme.BORDER))

        for line in last_lines:
            line = line.strip()
            if "ERROR" in line:
                console.print(f"[{Theme.RED}]{line}[/]")
            elif "WARNING" in line:
                console.print(f"[{Theme.YELLOW}]{line}[/]")
            else:
                console.print(f"[{Theme.COMMENT}]{line}[/]")

        console.print()
        Prompt.ask(f"[{Theme.COMMENT}]Press ENTER to return[/]")
        STATE.need_refresh = True
    except Exception as e:
        STATE.add_notification(f"Failed to read logs: {e}", "error")


async def action_clear_logs():
    try:
        if LOG_FILE.exists():
            LOG_FILE.write_text("")
            STATE.add_notification("Logs cleared", "success")
        else:
            STATE.add_notification("No log file to clear", "info")
    except Exception as e:
        STATE.add_notification(f"Failed to clear logs: {e}", "error")


# ═══════════════════════════════════════════════════════════
#  ADD ACCOUNT FLOW (with normal terminal input)
# ═══════════════════════════════════════════════════════════

async def action_start_add(use_qr: bool = False):
    STATE.add_use_qr = use_qr
    STATE.add_flow_step = 1
    STATE.add_data = {}
    STATE.add_notification(f"Started {'QR' if use_qr else 'classic'} login flow", "info")


async def run_add_account_dialog():
    """Выполняется вне TUI — с нормальным вводом"""
    terminal_input.pause()
    UI.clear()
    console.print(f"[bold {Theme.BLUE}]{DRAGON}[/]")

    try:
        if STATE.add_flow_step == 1:
            console.print(Panel(
                f"[bold {Theme.BLUE}]Step 1/3 — Account Name[/]",
                border_style=Theme.BLUE, box=ROUNDED, padding=(1, 2)
            ))
            name = Prompt.ask(UI.prompt_symbol() + " [bold]Name[/] (e.g. Main, Work)")
            if account_manager.exists(name):
                STATE.add_notification(f"Account '{name}' already exists!", "error")
                STATE.add_flow_step = 0
                return
            STATE.add_data['name'] = name
            if STATE.add_use_qr:
                await _run_qr_flow()
            else:
                STATE.add_flow_step = 2

        elif STATE.add_flow_step == 2:
            console.print(Panel(
                f"[bold {Theme.BLUE}]Step 2/3 — Phone Number[/]\n"
                f"[dim]Account: {STATE.add_data.get('name')}[/]",
                border_style=Theme.BLUE, box=ROUNDED, padding=(1, 2)
            ))
            phone = Prompt.ask(UI.prompt_symbol() + " [bold]Phone[/] (+79XXXXXXXXX)")
            STATE.add_data['phone'] = phone
            STATE.add_flow_step = 3

            # Pre-connect and send code
            name = STATE.add_data['name']
            proxy_enabled = hasattr(config, 'PROXY_ENABLED') and config.PROXY_ENABLED
            client_kwargs = get_client_kwargs(name.lower().replace(' ', '_'), proxy_enabled)
            ClientClass = UnifiedTelegramClient if MCUB_READY else TelegramClient
            client = ClientClass(
                f"hydra_{name.lower().replace(' ', '_')}",
                config.api_id, config.api_hash,
                **client_kwargs
            )
            _relax_protection(client)
            try:
                await client.connect()
                await client.send_code_request(phone)
                STATE.add_data['client'] = client
                STATE.add_notification(f"Code sent to {phone}", "success")
            except Exception as e:
                STATE.add_notification(f"Failed to send code: {e}", "error")
                STATE.add_flow_step = 0
                return

        elif STATE.add_flow_step == 3:
            console.print(Panel(
                f"[bold {Theme.YELLOW}]Step 3/3 — SMS Code[/]\n"
                f"[dim]Phone: {STATE.add_data.get('phone')}[/]",
                border_style=Theme.YELLOW, box=ROUNDED, padding=(1, 2)
            ))
            code = Prompt.ask(UI.prompt_symbol() + " [bold]Code[/]")
            await _finish_classic_login(code)

    finally:
        terminal_input.resume()
        STATE.need_refresh = True


async def _finish_classic_login(code: str):
    name = STATE.add_data.get('name', '')
    phone = STATE.add_data.get('phone', '')
    client = STATE.add_data.get('client')

    if not client:
        STATE.add_notification("Client not initialized", "error")
        STATE.add_flow_step = 0
        return

    try:
        await client.sign_in(phone=phone, code=code)
        me = await client.get_me()
        _save_account(name, phone, me, "classic")
        STATE.add_notification(f"Account '{name}' added!", "success")
    except SessionPasswordNeededError:
        password = Prompt.ask(
            UI.prompt_symbol() + " [bold {Theme.YELLOW}]🔐 2FA Password[/]",
            password=True
        )
        await client.sign_in(password=password)
        me = await client.get_me()
        _save_account(name, phone, me, "classic")
        STATE.add_notification(f"Account '{name}' added!", "success")
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        STATE.add_notification("Invalid code! Try again.", "error")
        return  # остаёмся на шаге 3
    except Exception as e:
        STATE.add_notification(f"Error: {e}", "error")
    STATE.add_flow_step = 0
    STATE.add_data = {}


def _save_account(name, phone, me, method):
    account_manager.add(
        name=name,
        phone=phone or me.phone or "",
        session=f"hydra_{name.lower().replace(' ', '_')}",
        username=me.username or "",
        first_name=me.first_name or "",
        login_method=method
    )


async def _run_qr_flow():
    name = STATE.add_data.get('name', '')
    proxy_enabled = hasattr(config, 'PROXY_ENABLED') and config.PROXY_ENABLED
    client_kwargs = get_client_kwargs(name.lower().replace(' ', '_'), proxy_enabled)
    ClientClass = UnifiedTelegramClient if MCUB_READY else TelegramClient
    client = ClientClass(
        f"hydra_{name.lower().replace(' ', '_')}",
        config.api_id, config.api_hash,
        **client_kwargs
    )
    _relax_protection(client)
    try:
        me = await login_qr_code(client)
        if me:
            _save_account(name, "", me, "qr")
            STATE.add_notification(f"Account '{name}' added via QR!", "success")
        else:
            STATE.add_notification("QR login failed", "error")
    except Exception as e:
        STATE.add_notification(f"QR error: {e}", "error")
    STATE.add_flow_step = 0
    STATE.add_data = {}


# ═══════════════════════════════════════════════════════════
#  THEME ACTIONS
# ═══════════════════════════════════════════════════════════

async def action_apply_theme():
    themes = Theme.list_themes()
    if STATE.selected_theme < len(themes):
        key, name = themes[STATE.selected_theme]
        Theme.set_theme(key)
        STATE.add_notification(f"Theme changed to {name}", "success")


# ═══════════════════════════════════════════════════════════
#  MODULE ACTIONS
# ═══════════════════════════════════════════════════════════

async def action_module_enter():
    mods = module_scanner.modules
    if not mods or STATE.selected_module >= len(mods):
        return
    STATE.current_module = mods[STATE.selected_module]
    STATE.module_view = "bat"
    STATE.module_bat_scroll = 0
    STATE.add_notification(f"BAT view: {STATE.current_module['name']}", "info")


async def action_module_back():
    if STATE.module_view == "bat":
        STATE.module_view = "list"
        STATE.current_module = None
        STATE.module_bat_scroll = 0
    else:
        STATE.active_tab = 0


async def action_module_scroll(dy: int):
    if STATE.module_view == "bat" and STATE.current_module:
        max_scroll = max(0, STATE.current_module.get("lines", 0) - 40)
        STATE.module_bat_scroll = max(0, min(max_scroll, STATE.module_bat_scroll + dy))


async def action_module_edit():
    if not STATE.current_module:
        return
    fpath = STATE.current_module["file"]
    editor = os.environ.get("EDITOR", "nano")
    terminal_input.pause()
    UI.clear()
    console.print(f"[bold {Theme.BLUE}]Opening {fpath} in {editor}...[/]")
    os.system(f"{editor} \"{fpath}\"")
    terminal_input.resume()
    STATE.need_refresh = True
    STATE.add_notification(f"Edited {STATE.current_module['name']}", "success")


async def action_module_rescan():
    module_scanner.scan()
    STATE.selected_module = 0
    STATE.add_notification(f"Scanned {len(module_scanner.modules)} modules", "success")


# ═══════════════════════════════════════════════════════════
#  INPUT / ACTION PROCESSOR
# ═══════════════════════════════════════════════════════════

async def process_actions():
    while STATE.running:
        try:
            action, data = STATE.action_queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.05)
            continue

        if action == 'quit':
            if STATE.active_tab == 4 and STATE.module_view == "bat":
                await action_module_back()
            else:
                STATE.running = False
        elif action == 'refresh':
            if STATE.active_tab == 4:
                await action_module_rescan()
            STATE.need_refresh = True
        elif action == 'tab':
            if data != STATE.active_tab:
                if STATE.add_flow_step > 0:
                    STATE.add_flow_step = 0
                    STATE.add_data = {}
                    STATE.add_notification("Add account cancelled", "info")
                if STATE.module_view == "bat":
                    STATE.module_view = "list"
                    STATE.current_module = None
                STATE.active_tab = data
                STATE.selected_add_method = 0
                STATE.selected_theme = 0
                STATE.selected_module = 0
                STATE.need_refresh = True
        elif action == 'up' or action == 'k':
            if STATE.active_tab == 0:
                accounts = account_manager.list()
                if accounts:
                    STATE.selected_account = max(0, STATE.selected_account - 1)
            elif STATE.active_tab == 1 and STATE.add_flow_step == 0:
                STATE.selected_add_method = max(0, STATE.selected_add_method - 1)
            elif STATE.active_tab == 2:
                STATE.selected_theme = max(0, STATE.selected_theme - 1)
            elif STATE.active_tab == 4:
                if STATE.module_view == "bat":
                    await action_module_scroll(-5)
                else:
                    STATE.selected_module = max(0, STATE.selected_module - 1)
            STATE.need_refresh = True
        elif action == 'down' or action == 'j':
            if STATE.active_tab == 0:
                accounts = account_manager.list()
                if accounts:
                    STATE.selected_account = min(len(accounts) - 1, STATE.selected_account + 1)
            elif STATE.active_tab == 1 and STATE.add_flow_step == 0:
                STATE.selected_add_method = min(1, STATE.selected_add_method + 1)
            elif STATE.active_tab == 2:
                themes = Theme.list_themes()
                STATE.selected_theme = min(len(themes) - 1, STATE.selected_theme + 1)
            elif STATE.active_tab == 4:
                if STATE.module_view == "bat":
                    await action_module_scroll(5)
                else:
                    mods = module_scanner.modules
                    STATE.selected_module = min(len(mods) - 1, STATE.selected_module + 1)
            STATE.need_refresh = True
        elif action == 'first' or action == 'g':
            if STATE.active_tab == 0:
                STATE.selected_account = 0
            elif STATE.active_tab == 1 and STATE.add_flow_step == 0:
                STATE.selected_add_method = 0
            elif STATE.active_tab == 2:
                STATE.selected_theme = 0
            elif STATE.active_tab == 4 and STATE.module_view != "bat":
                STATE.selected_module = 0
            STATE.need_refresh = True
        elif action == 'last' or action == 'G':
            if STATE.active_tab == 0:
                accounts = account_manager.list()
                if accounts:
                    STATE.selected_account = len(accounts) - 1
            elif STATE.active_tab == 1 and STATE.add_flow_step == 0:
                STATE.selected_add_method = 1
            elif STATE.active_tab == 2:
                themes = Theme.list_themes()
                STATE.selected_theme = len(themes) - 1
            elif STATE.active_tab == 4 and STATE.module_view != "bat":
                mods = module_scanner.modules
                STATE.selected_module = len(mods) - 1
            STATE.need_refresh = True
        elif action == 'enter' or action == 'l':
            if STATE.active_tab == 0:
                await action_launch_account()
            elif STATE.active_tab == 1 and STATE.add_flow_step == 0:
                if STATE.selected_add_method == 0:
                    await action_start_add(use_qr=False)
                else:
                    await action_start_add(use_qr=True)
            elif STATE.active_tab == 2:
                await action_apply_theme()
            elif STATE.active_tab == 4:
                if STATE.module_view == "list":
                    await action_module_enter()
            STATE.need_refresh = True
        elif action == 'back' or action == 'h':
            if STATE.active_tab == 4:
                await action_module_back()
            elif STATE.add_flow_step > 0:
                STATE.add_flow_step = 0
                STATE.add_data = {}
                STATE.add_notification("Add account cancelled", "info")
            STATE.need_refresh = True
        elif action == 'delete':
            if STATE.active_tab == 0:
                await action_delete_account()
            STATE.need_refresh = True
        elif action == 'favorite':
            if STATE.active_tab == 0:
                await action_toggle_favorite()
            STATE.need_refresh = True
        elif action == 'backup':
            await action_backup()
            STATE.need_refresh = True
        elif action == 'view_logs':
            await action_view_logs()
            STATE.need_refresh = True
        elif action == 'clear_logs':
            await action_clear_logs()
            STATE.need_refresh = True
        elif action == 'module_edit':
            if STATE.active_tab == 4:
                await action_module_edit()
            STATE.need_refresh = True


# ═══════════════════════════════════════════════════════════
#  MAIN HYDRA BOOT
# ═══════════════════════════════════════════════════════════

async def boot_hydra(account_name, account_data):
    UI.clear()
    console.print(f"[bold {Theme.BLUE}]{DRAGON}[/]")
    console.print(f"[bold {Theme.BLUE}]⚡ HYDRA[/] [bold {Theme.CYAN}]{account_name}[/]")
    console.print()

    cython_mode = compile_cython()

    proxy_enabled = hasattr(config, 'PROXY_ENABLED') and config.PROXY_ENABLED
    client_kwargs = get_client_kwargs(account_data['session'], proxy_enabled)

    ClientClass = UnifiedTelegramClient if MCUB_READY else TelegramClient

    client = ClientClass(
        account_data['session'], config.api_id, config.api_hash,
        **client_kwargs
    )
    _relax_protection(client)

    Path('modules').mkdir(exist_ok=True)
    Path('data').mkdir(exist_ok=True)

    if MCUB_READY:
        patch_adapter_for_unified_client()

    try:
        with console.status(f"[bold {Theme.BLUE}]Connecting to Telegram...[/]", spinner="arc"):
            await client.start()
        me = await client.get_me()
    except Exception as e:
        UI.error(f"Connection failed: {e}")
        return

    UI.success(f"Welcome back, {me.first_name}!")
    console.print()

    # ── единый движок: hydra_kernel + compat для всех родных модулей ──
    import importlib
    dispatcher = importlib.import_module("modules.mcub")
    dispatcher.setup(client)
    UI.success(f"🧩 Engine ready (prefix={getattr(config, 'prefix', '.') or '.'})")

    console.print()
    with Progress(
        SpinnerColumn(spinner_name="arc", style=Theme.BLUE),
        TextColumn("{task.description}", style=f"bold {Theme.BLUE}"),
        BarColumn(bar_width=30, complete_style=Theme.GREEN, finished_style=Theme.BLUE),
        TextColumn("{task.percentage:>3.0f}%", style="bold"),
        MofNCompleteColumn(),
        TimeRemainingColumn(elapsed_when_finished=True),
        console=console,
    ) as progress:
        task = progress.add_task("Loading modules...", total=1)
        records, errors = await dispatcher.wait_ready()
        progress.update(task, completed=1, description="Modules loaded")
    for name, err in errors:
        UI.error(f"{name}: {err}")
    success = len(records)
    total = len(records) + len(errors)

    console.print()
    UI.success(
        f"{success}/{total} modules loaded  "
        f"[dim](boot: {getattr(dispatcher, 'BOOT_TIME', 0.0):.2f}s)[/]"
    )
    console.print()

    console.print(table_status(me, cython_mode, success, True))
    console.print(render_modules_table(records, errors))

    console.print()
    console.print(Panel(
        f"[bold {Theme.GREEN}]🐉 HYDRA IS RUNNING[/]  [dim]Type {config.prefix}help for commands[/]\n"
        f"[bold {Theme.YELLOW}]e[/] editor   [bold {Theme.YELLOW}]r[/] reload modules   "
        f"[bold {Theme.YELLOW}]q[/] quit",
        box=DOUBLE_EDGE,
        border_style=Theme.GREEN,
        padding=(1, 2)
    ))
    console.print()

    def _redraw(recs, errs):
        UI.clear()
        console.print(table_status(me, cython_mode, len(recs), True))
        console.print(render_modules_table(recs, errs))
        console.print(Panel(
            f"[bold {Theme.YELLOW}]e[/] editor   [bold {Theme.YELLOW}]r[/] reload   "
            f"[bold {Theme.YELLOW}]q[/] quit",
            box=ROUNDED, border_style=Theme.BORDER,
        ))

    stop = asyncio.Event()

    async def _hotkeys():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not stop.is_set():
                if select.select([sys.stdin], [], [], 0.2)[0]:
                    key = sys.stdin.read(1).lower()
                    if key == "q":
                        stop.set()
                        return
                    if key == "r":
                        recs, errs = await dispatcher.reload_all()
                        for n, e in errs:
                            UI.error(f"{n}: {e}")
                        UI.success(
                            f"reloaded {len(recs)} modules "
                            f"(boot: {dispatcher.BOOT_TIME:.2f}s)"
                        )
                        _redraw(recs, errs)
                        tty.setcbreak(fd)
                    elif key == "e":
                        termios.tcsetattr(fd, termios.TCSADRAIN, old)
                        subprocess.run(
                            [sys.executable, "-m", "hydra_kernel.tui", "modules"]
                        )
                        recs, errs = await dispatcher.reload_all()
                        _redraw(recs, errs)
                        tty.setcbreak(fd)
                await asyncio.sleep(0)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    hotkey_task = asyncio.create_task(_hotkeys())
    stop_task = asyncio.create_task(stop.wait())
    disco_task = asyncio.create_task(client.run_until_disconnected())
    try:
        await asyncio.wait(
            {stop_task, disco_task}, return_when=asyncio.FIRST_COMPLETED
        )
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for t in (hotkey_task, stop_task, disco_task):
            t.cancel()
        UI.clear()
        console.print(f"[bold {Theme.BLUE}]{DRAGON}[/]")
        console.print(f"[bold {Theme.BLUE}]👋 Goodbye, dragon rider.[/]")
        await client.disconnect()


def _boot_seconds() -> float:
    try:
        import importlib

        return float(getattr(importlib.import_module("modules.mcub"), "BOOT_TIME", 0.0))
    except Exception:
        return 0.0


def table_status(me, cython, count, mcub_ready):
    t = Table(
        title=f'[bold {Theme.BLUE}]SYSTEM STATUS[/]',
        box=ROUNDED,
        border_style=Theme.BORDER,
        show_header=False,
        padding=(0, 2)
    )
    t.add_column('Param', style=f'bold {Theme.COMMENT}', width=12)
    t.add_column('Value', style=Theme.FG)

    display_name = f"{me.first_name or ''}"
    if me.username:
        display_name += f"  [@{me.username}]"

    t.add_row("Account", f"[bold {Theme.BLUE}]{display_name}[/]")
    t.add_row("ID", f"[dim]{me.id}[/]")
    t.add_row("Core", f"[bold {Theme.YELLOW if cython else Theme.FG}]" \
              f"{'CYTHON' if cython else 'PYTHON'}[/]")
    t.add_row("MCUB", f"[bold {Theme.GREEN if mcub_ready else Theme.RED}]" \
              f"{'READY' if mcub_ready else 'OFF'}[/]")
    t.add_row("Modules", f"[bold {Theme.BLUE}]{count}[/]")
    t.add_row("Boot", f"[bold {Theme.CYAN}]{_boot_seconds():.2f}s[/]")
    t.add_row("Prefix", f"[bold {Theme.ORANGE}]{config.prefix}[/]")

    return Panel(t, box=ROUNDED, border_style=Theme.BORDER, padding=(1, 1))


_FW_STYLE = {
    "hydra": Theme.BLUE,
    "mcub": Theme.ORANGE,
    "core": Theme.CYAN,
    "setup": Theme.PURPLE,
    "hikka": Theme.GREEN,
    "heroku": Theme.YELLOW,
    "dragon": Theme.RED,
    "noop": Theme.COMMENT,
}


def render_modules_table(records, errors):
    """Настоящая таблица: имя / framework / версия / статус (фаза 6)."""
    t = Table(
        title='[bold {0}]MODULES[/]'.format(Theme.BLUE),
        box=ROUNDED,
        border_style=Theme.BORDER,
        show_header=True,
        header_style=f"bold {Theme.COMMENT}",
    )
    t.add_column('#', style=f'dim {Theme.COMMENT}', width=4, justify='right')
    t.add_column('Module', style=Theme.FG)
    t.add_column('Framework', width=10)
    t.add_column('Version', width=9, style=f'dim {Theme.COMMENT}')
    t.add_column('Status', width=8)

    rows = sorted(records, key=lambda r: r.name)
    for i, rec in enumerate(rows, 1):
        fw = getattr(rec, "framework", "?") or "?"
        fw_style = _FW_STYLE.get(fw, Theme.FG)
        version = str(getattr(getattr(rec, "manifest", None), "version", "") or "")
        t.add_row(
            str(i),
            rec.name,
            f"[bold {fw_style}]{fw}[/]",
            version,
            f"[bold {Theme.GREEN}]OK[/]",
        )
    for name, err in errors:
        t.add_row(
            "", f"[{Theme.RED}]{name}[/]", "-", "-",
            f"[bold {Theme.RED}]FAIL[/]",
        )
    return Panel(t, box=ROUNDED, border_style=Theme.BORDER, padding=(1, 1))


def compile_cython():
    pyx_file = Path("utils/loader.pyx")
    if not pyx_file.exists():
        return False
    so_files = list(Path("utils").glob("loader*.so"))
    if not so_files or pyx_file.stat().st_mtime > so_files[0].stat().st_mtime:
        os.system("cd utils && cythonize -i -3 loader.pyx 2>&1 | grep -v 'warning' | grep -v 'fallthrough'")
    return len(list(Path("utils").glob("loader*.so"))) > 0


# ═══════════════════════════════════════════════════════════
#  MAIN ENTRY
# ═══════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description='Hydra UserBot v4.1')
    parser.add_argument("--web", action="store_true", help="Web login via QR-code")
    parser.add_argument("--mcub", action="store_true", help="Enable MCUB mode")
    args = parser.parse_args()

    STATE.use_web = args.web

    terminal_input.start()
    action_task = asyncio.create_task(process_actions())

    try:
        while STATE.running:
            # Если нужен диалог (add account flow) — выходим из TUI
            if STATE.add_flow_step > 0:
                await run_add_account_dialog()
                continue

            with Live(console=console, screen=True, refresh_per_second=10) as live:
                while STATE.running and STATE.add_flow_step == 0:
                    if STATE.need_refresh:
                        live.update(make_layout())
                        STATE.need_refresh = False
                    await asyncio.sleep(0.05)
    finally:
        terminal_input.stop()
        action_task.cancel()
        try:
            await action_task
        except asyncio.CancelledError:
            pass

    if STATE.result:
        await boot_hydra(*STATE.result)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        UI.clear()
        console.print(f"[bold {Theme.BLUE}]{DRAGON}[/]")
        console.print(f"[bold {Theme.BLUE}]👋 Goodbye![/]")
