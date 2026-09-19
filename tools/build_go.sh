#!/bin/sh
# Сборка Go-части ядра (hydracore) и Go-модулей через hrul.
set -e
cd "$(dirname "$0")/.."
(cd gocore && go build -o hydracore .)
chmod +x gocore/hydracore
echo "go core built: gocore/hydracore"
for d in gocore/modules/*/; do
  [ -f "$d/module.hrul" ] || continue
  python3 tools/hrul.py build "$d"
done
