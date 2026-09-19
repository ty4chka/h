#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hydra UserBot - Cython Setup
Для компиляции ядра в Termux/Android
"""

import os
import sys
from pathlib import Path
from setuptools import setup, Extension
from Cython.Build import cythonize

# Определяем платформу
IS_TERMUX = os.path.exists('/data/data/com.termux')
IS_ANDROID = IS_TERMUX

# Настройки компиляции для Termux/Android
if IS_TERMUX:
    # Оптимизации для ARM процессоров
    extra_compile_args = [
        '-O3',                    # Максимальная оптимизация
        '-march=armv8-a',         # ARMv8 архитектура
        '-mtune=cortex-a53',      # Оптимизация для Cortex-A53
        '-ffast-math',            # Быстрая математика
        '-fno-strict-aliasing',   # Отключаем строгий алиасинг
        '-DANDROID',              # Флаг Android
        '-DTERMUX',               # Флаг Termux
    ]
    
    extra_link_args = [
        '-Wl,--as-needed',
    ]
else:
    # Для обычного Linux/Windows
    extra_compile_args = [
        '-O3',
        '-march=native',
        '-ffast-math',
    ]
    extra_link_args = []

# Определяем расширения
extensions = [
    Extension(
        "utils.loader",
        sources=["utils/loader.pyx"],
        language="c",
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    )
]

# Настройки Cython
compiler_directives = {
    'language_level': "3",           # Python 3
    'boundscheck': False,            # Отключаем проверку границ (быстрее)
    'wraparound': False,             # Отключаем проверку индексов
    'cdivision': True,               # C-деление (быстрее)
    'embedsignature': True,          # Сохраняем сигнатуры
    'annotation_typing': False,      # Отключаем аннотации типов
    'initializedcheck': False,       # Отключаем проверку инициализации
    'nonecheck': False,              # Отключаем проверку на None
}

def clean_old_builds():
    """Очистка старых сборок"""
    import shutil
    
    dirs_to_clean = ['build', 'dist', '__pycache__']
    files_to_clean = ['utils/loader.c', 'utils/loader.html']
    
    for d in dirs_to_clean:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"    🧹 Удалено: {d}")
    
    for f in files_to_clean:
        if os.path.exists(f):
            os.remove(f)
            print(f"    🧹 Удалено: {f}")
    
    # Удаляем старые .so файлы
    for so_file in Path("utils").glob("loader*.so"):
        so_file.unlink()
        print(f"    🧹 Удалено: {so_file}")

def check_dependencies():
    """Проверка зависимостей"""
    print("\n    📦 Проверка зависимостей...")
    
    deps = {
        'Cython': 'cython',
        'setuptools': 'setuptools',
    }
    
    missing = []
    for module, package in deps.items():
        try:
            __import__(module)
            print(f"    ✅ {module} найден")
        except ImportError:
            print(f"    ❌ {module} не найден")
            missing.append(package)
    
    if missing:
        print(f"\n    ⚠️  Установите зависимости:")
        print(f"    pip install {' '.join(missing)}")
        
        if IS_TERMUX:
            print(f"\n    📱 Для Termux также нужно:")
            print("    pkg install clang python-dev")
        
        return False
    
    return True

def main():
    """Главная функция"""
    print("""
    ╔══════════════════════════════════╗
    ║     HYDRA CYTHON COMPILER        ║
    ║         Termux Edition           ║
    ╚══════════════════════════════════╝
    """)
    
    # Проверяем платформу
    if IS_TERMUX:
        print(f"    📱 Платформа: Termux/Android")
    else:
        print(f"    💻 Платформа: {sys.platform}")
    
    # Проверяем зависимости
    if not check_dependencies():
        return 1
    
    # Проверяем наличие исходника
    if not os.path.exists("utils/loader.pyx"):
        print("    ❌ utils/loader.pyx не найден!")
        return 1
    
    print(f"\n    🔧 Настройки компиляции:")
    print(f"    📌 extra_compile_args: {extra_compile_args}")
    
    # Спрашиваем про очистку
    if os.path.exists("build") or os.path.exists("utils/loader.so"):
        response = input("\n    🧹 Очистить старые сборки? [y/N]: ").lower()
        if response in ['y', 'yes', 'да']:
            clean_old_builds()
    
    print("\n    ⚙️  Компиляция Hydra Core...")
    print("    Это может занять 10-30 секунд...\n")
    
    try:
        # Запускаем компиляцию
        setup(
            name="Hydra Core",
            version="2.0.0",
            description="Hydra UserBot Cython Core",
            author="Hydra Team",
            ext_modules=cythonize(
                extensions,
                compiler_directives=compiler_directives,
                nthreads=2,  # Используем 2 потока для компиляции
                quiet=False,
                language_level="3",
            ),
            zip_safe=False,
            script_args=['build_ext', '--inplace'],
        )
        
        # Проверяем результат
        so_files = list(Path("utils").glob("loader*.so"))
        
        if so_files:
            import subprocess
            result = subprocess.run(['file', str(so_files[0])], capture_output=True, text=True)
            
            print(f"""
    ╔══════════════════════════════════╗
    ║      ✅ КОМПИЛЯЦИЯ УСПЕШНА       ║
    ╚══════════════════════════════════╝
    
    📦 Выходной файл: {so_files[0]}
    📊 Размер: {so_files[0].stat().st_size / 1024:.1f} KB
    🏗️  Тип: {result.stdout.strip() if result.returncode == 0 else 'Shared Object'}
    
    🚀 Теперь запускайте: python main.py
    """)
            return 0
        else:
            print("\n    ❌ .so файл не создан!")
            return 1
            
    except Exception as e:
        print(f"\n    💥 Ошибка компиляции: {e}")
        
        if IS_TERMUX:
            print("""
    📱 Советы для Termux:
    1. Установите clang: pkg install clang
    2. Установите python-dev: pkg install python-dev
    3. Попробуйте: CFLAGS="-O3" python setup.py build_ext --inplace
            """)
        
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
