#!/usr/bin/env python3
"""hrul — сборщик модулей Hydra из нескольких файлов.

Манифест `module.hrul` в папке модуля (key = value, # комментарии):

    name    = echomod        # имя модуля
    lang    = go             # go | python
    version = 2.0.0
    entry   = main.go        # точка входа
    sources = main.go echo.go  # ВСЕ файлы модуля (для go)
    output  = ../bin/echomod   # куда положить артефакт

Команды:
    python3 tools/hrul.py build <папка_модуля> [...]
    python3 tools/hrul.py list <корень_с_модулями>

В отличие от репозиториев MCUB (скачивание .py по modules.ini), hrul —
локальная декларативная сборка: модуль = папка с манифестом, несколько
исходников одного языка собираются в один артефакт (Go-бинарник или
python-пакет), готовый к загрузке GoLoader'ом / Loader'ом ядра.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_manifest(path: Path) -> dict:
    data: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    if "name" not in data or "lang" not in data:
        raise ValueError(f"{path}: в манифесте нужны name и lang")
    return data


def build_go(mdir: Path, m: dict) -> Path:
    sources = m.get("sources", m.get("entry", "main.go")).split()
    out = (mdir / m.get("output", f"../bin/{m['name']}")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["go", "build", "-o", str(out)] + sources
    r = subprocess.run(cmd, cwd=mdir, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"go build: {r.stderr.strip()}")
    os.chmod(out, 0o755)  # go_loader запускает бинарь — нужен +x
    return out


def build_python(mdir: Path, m: dict) -> Path:
    sources = m.get("sources", m.get("entry", "")).split()
    if not sources:
        sources = sorted(p.name for p in mdir.glob("*.py"))
    out = (ROOT / "modules" / m["name"]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for s in sources:
        shutil.copy2(mdir / s, out / s)
    (out / "__init__.py").write_text("", encoding="utf-8")
    return out


def build(mdir: Path) -> Path:
    manifest = mdir / "module.hrul"
    if not manifest.exists():
        raise FileNotFoundError(f"{mdir}: нет module.hrul")
    m = parse_manifest(manifest)
    if m["lang"] == "go":
        return build_go(mdir, m)
    if m["lang"] == "python":
        return build_python(mdir, m)
    raise ValueError(f"неизвестный lang: {m['lang']}")


def main(argv: list) -> int:
    if len(argv) < 2 or argv[1] not in ("build", "list"):
        print(__doc__)
        return 2
    if argv[1] == "list":
        base = Path(argv[2]) if len(argv) > 2 else ROOT / "gocore" / "modules"
        for d in sorted(base.iterdir()):
            mf = d / "module.hrul"
            if mf.exists():
                m = parse_manifest(mf)
                print(f"{m['name']} v{m.get('version','0')} [{m['lang']}] — {d}")
        return 0
    for target in argv[2:]:
        mdir = Path(target)
        m = parse_manifest(mdir / "module.hrul")
        out = build(mdir)
        print(f"hrul: {m['name']} v{m.get('version','0')} [{m['lang']}] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
