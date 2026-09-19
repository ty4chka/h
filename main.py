"""Точка входа Hydra: поднимает ядро, грузит модули и открывает GUI-редактор.

    python3 main.py            — запуск с TUI-редактором
    python3 main.py --no-tui   — без GUI (headless)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hydra_kernel import Hydra, __version__


async def boot() -> tuple:
    try:
        import config

        owner = getattr(config, "OWNER_ID", 0) or 1000
    except ImportError:
        owner = 1000
    hydra = Hydra(owner_id=owner)
    await hydra.start()
    records, errors = await hydra.loader.load_dir("modules", framework="auto", exclude=("mcub", "__init__"), allow_unsafe=True)
    # Go-модули (hrul-сборка): gocore/bin/*
    go_names: list = []
    if Path("gocore/bin").is_dir():
        from hydra_kernel.pkg.go_loader import GoLoader

        hydra.go_loader = GoLoader(hydra)
        try:
            go_names = await hydra.go_loader.load_dir("gocore/bin")
        except Exception as e:  # noqa: BLE001 - Go-часть опциональна
            print(f"⚠️ go-модули не загружены: {e}")
    return hydra, records, errors, go_names


def main() -> int:
    hydra, records, errors, go_names = asyncio.run(boot())
    for name, err in errors:
        print(f"⚠️ модуль {name} не загружен: {err}")
    go_part = f" · go: {len(go_names)}" if go_names else ""
    status = f"v{__version__} · модулей: {len(records)}{go_part} · язык: {hydra.config.get('language')}"
    print(f"🧬 Hydra {status}")
    if "--no-tui" in sys.argv:
        return 0
    import curses

    from hydra_kernel.tui.app import run_tui

    return curses.wrapper(run_tui, "modules", status)


if __name__ == "__main__":
    sys.exit(main())
