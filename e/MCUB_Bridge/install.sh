#!/data/data/com.termux/files/usr/bin/bash
# Установка MCUB Engine в Hydra UserBot (Termux)
# Запуск: bash install.sh /путь/к/Hydra
set -e

HYDRA="${1:-.}"
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "🧩 MCUB Engine installer"
echo "   Источник: $SRC"
echo "   Цель:     $HYDRA"

[ -f "$HYDRA/main.py" ] || { echo "❌ main.py не найден в $HYDRA — укажи корень Hydra"; exit 1; }

cp -r "$SRC/mcub_engine" "$HYDRA/"
echo "✅ mcub_engine/"

cp -r "$SRC/core_inline" "$HYDRA/"
mkdir -p "$HYDRA/core/lib/types"
cp "$SRC/core/lib/types/"*.py "$HYDRA/core/lib/types/"
cp "$SRC/core/lib/loader/module_base.py"   "$HYDRA/core/lib/loader/"
cp "$SRC/core/lib/loader/module_config.py" "$HYDRA/core/lib/loader/"
cp "$SRC/core/lib/loader/decorators.py"    "$HYDRA/core/lib/loader/"
echo "✅ core/ + core_inline/"

cp "$SRC/modules/mcub.py" "$HYDRA/modules/"
echo "✅ modules/mcub.py"

if [ -f "$HYDRA/modules/hloader.py" ]; then
    cp "$HYDRA/modules/hloader.py" "$HYDRA/modules/hloader.py.bak"
    cp "$SRC/modules/hloader.py" "$HYDRA/modules/hloader.py"
    echo "✅ modules/hloader.py (старый сохранён как hloader.py.bak)"
fi

mkdir -p "$HYDRA/modules/mcub_mods" "$HYDRA/data"
echo ""
echo "🎉 Готово! Перезапусти Hydra."
echo "   Установка модулей: reply на .py + .mload"
echo "   Кнопки работают как команды: .cb 1, .cb 2, ..."
