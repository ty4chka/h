"""Проверка языковых паков в окружении боевого `m.py`.

`m.py` импортирует `utils.misc` ещё до старта ядра, поэтому в `sys.modules`
оказывается настоящий `utils/strings.py` (а не shim MCUB-адаптера). Раньше при
пустом `core.langpacks` любой модуль вида `# name: system` падал на загрузке:

    ValueError: Strings: no valid locale data found. Requested: ru,
                fallback: en, available: []

Скрипт воспроизводит этот порядок импортов и проверяет, что:

1. `core.langpacks` отдаёт паки (get_langpacks/get_module_strings);
2. `utils.strings.Strings` с паком модуля и без пака не роняет загрузку;
3. `modules/protect.py` (`# name: system`) грузится и отвечает на команду.

Запуск: python3 tools/langpacks_check.py (используется сборкой).
"""

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import utils  # noqa: E402,F401 - как в m.py: реальный пакет до модулей
import utils.strings as strings_module  # noqa: E402
from core import langpacks  # noqa: E402
from hydra_kernel import Hydra  # noqa: E402


def check_packs() -> None:
    assert strings_module.__file__.endswith("utils/strings.py"), strings_module.__file__

    packs = langpacks.get_langpacks()
    assert packs.get("ru"), f"нет ru-пака: {list(packs)}"
    assert langpacks.get_available_locales(), "нет доступных локалей"

    system_strings = langpacks.get_module_strings("system", "ru")
    assert system_strings.get("restart_done"), "нет строк модуля system"
    assert system_strings.get("buttons"), "глобальные группы не попали в строки модуля"

    kernel = types.SimpleNamespace(config={"language": "ru"})
    strings = strings_module.Strings(kernel, {"name": "system"})
    assert strings("buttons")("close"), "группа buttons пуста"
    assert "Перезапуск" in strings("restart_done"), strings("restart_done")

    # Незнакомый модуль и пустой data-словарь больше не роняют загрузку:
    # MCUB-fork кидает ValueError, Hydra отдаёт _MissingKey/get(default).
    assert strings_module.Strings("ru", {"name": "нет_такого_модуля"}).get("k", "def") == "def"
    assert strings_module.Strings("ru", {}).get("k", "def") == "def"


async def check_protect_module() -> None:
    h = Hydra(owner_id=1000)
    await h.start()
    try:
        path = ROOT / "modules" / "protect.py"
        source = path.read_text(encoding="utf-8")
        record = await h.loader.load_source(
            "protect", source, framework="mcub", file_path=str(path)
        )
        assert record.name == "protect", record.name
        await h.transport.inject(500, ".api_protection", sender_id=1000, outgoing=True)
        assert h.transport.sent and h.transport.sent[-1].text.strip() != ".api_protection", \
            ".api_protection не ответил"
    finally:
        await h.stop()


def main() -> int:
    check_packs()
    asyncio.run(check_protect_module())
    print("langpacks check: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
