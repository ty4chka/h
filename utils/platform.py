"""Небольшая кросс-платформенная поверхность ``utils.platform`` из MCUB."""

from __future__ import annotations

import os
import platform as _platform


def is_termux() -> bool:
    return bool(os.environ.get("TERMUX_VERSION")) or os.path.exists("/data/data/com.termux/files/usr")


def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    for path in ("/proc/version", "/proc/sys/kernel/osrelease"):
        try:
            if "microsoft" in open(path, encoding="utf-8").read().lower():
                return True
        except OSError:
            continue
    return False


def is_docker() -> bool:
    return os.path.exists("/.dockerenv")


def get_platform() -> str:
    if is_termux():
        return "termux"
    if is_wsl():
        return "wsl"
    if is_docker():
        return "docker"
    system = _platform.system().lower()
    return system if system in {"linux", "windows", "darwin"} else "unknown"


def is_vds() -> bool:
    return get_platform() == "linux" and not bool(os.environ.get("DISPLAY"))


def get_platform_name() -> str:
    names = {
        "termux": "Termux",
        "wsl": "WSL",
        "docker": "Docker",
        "linux": "Linux",
        "windows": "Windows",
        "darwin": "macOS",
        "unknown": "Unknown",
    }
    return names[get_platform()]


def get_detailed_info() -> dict[str, str]:
    return {
        "platform": get_platform(),
        "system": _platform.system(),
        "release": _platform.release(),
        "machine": _platform.machine(),
        "hostname": _platform.node(),
    }


get_platform_info = get_detailed_info
is_mobile = is_termux
