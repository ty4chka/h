"""Cython-компиляция горячих модулей ядра в нативные .so (in-place).

    python3 tools/build_native.py

После сборки импорты hydra_kernel.pkg.scanner / resolver / api.lang
подхватывают .so вместо .py (расширения имеют приоритет у импортёра).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    "hydra_kernel/pkg/scanner.py",
    "hydra_kernel/pkg/resolver.py",
    "hydra_kernel/api/lang.py",
]


def main() -> int:
    try:
        from Cython.Build import cythonize
        from setuptools import Extension, setup
    except ImportError:
        print("SKIP: cython/setuptools не установлены")
        return 0

    import os

    os.chdir(ROOT)
    exts = [Extension(t[:-3].replace("/", "."), [t]) for t in TARGETS]
    sys.argv = ["build_native.py", "build_ext", "--inplace"]
    setup(  # type: ignore[call-arg]
        ext_modules=cythonize(exts, language_level="3", quiet=True),
    )
    print("NATIVE OK:", ", ".join(TARGETS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
