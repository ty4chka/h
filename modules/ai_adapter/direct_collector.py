"""
Direct Collector - Прямые RAW ссылки без API
"""

import aiohttp
import asyncio
import sys
from pathlib import Path

# Добавляем путь для импорта
sys.path.insert(0, str(Path.cwd().parent))

from ai_adapter.ast_analyzer import ModuleASTAnalyzer

# ПРЯМЫЕ RAW ССЫЛКИ НА ИЗВЕСТНЫЕ МОДУЛИ
RAW_MODULES = [
    # FTG модули (Hikka)
    "https://raw.githubusercontent.com/hikariatama/ftg/master/ping.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/terminal.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/serverinfo.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/userinfo.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/carbon.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/translate.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/weather.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/crypto.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/notes.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/todo.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/spotify.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/youtube.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/voicechat.py",
    
    # Nalinor модули
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/membersquery.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/speedtest.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/swmute.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/msgrate.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/lavhost.py",
    
    # MCUB модули
    "https://raw.githubusercontent.com/hairpin01/MCUB-fork/main/modules/ping.py",
    "https://raw.githubusercontent.com/hairpin01/MCUB-fork/main/modules/info.py",
    
    # DeBot модули (Hydra)
    "https://raw.githubusercontent.com/DeBotCommunity/DeBot/main/modules/ping.py",
    "https://raw.githubusercontent.com/DeBotCommunity/CryptoBalance/main/crypto_balance.py",
    "https://raw.githubusercontent.com/DeBotCommunity/System-Info/main/system_info.py",
    "https://raw.githubusercontent.com/DeBotCommunity/InfoFromUser/main/user_info.py",
]

async def download():
    training_dir = Path("training_data")
    
    # Создаём папки
    for sub in ["hikka_samples", "mcub_samples", "hydra_samples"]:
        (training_dir / sub).mkdir(parents=True, exist_ok=True)
    
    print("🌐 ПРЯМОЙ СБОР МОДУЛЕЙ")
    print("=" * 50)
    print(f"📦 Ссылок: {len(RAW_MODULES)}\n")
    
    async with aiohttp.ClientSession() as session:
        for i, url in enumerate(RAW_MODULES):
            try:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        code = await resp.text()
                        name = url.split("/")[-1]
                        
                        # Определяем тип через AST
                        analyzer = ModuleASTAnalyzer(code)
                        detected = analyzer.analyze().get("module_type", "hikka")
                        
                        # Определяем папку
                        if "mcub" in url.lower():
                            folder = "mcub_samples"
                        elif "debot" in url.lower():
                            folder = "hydra_samples"
                        else:
                            folder = f"{detected}_samples"
                        
                        target = training_dir / folder / name
                        
                        if not target.exists():
                            target.write_text(code, encoding='utf-8')
                            print(f"  ✅ [{i+1:2d}/{len(RAW_MODULES)}] {name:20} -> {folder}")
                        else:
                            print(f"  ⏭️  [{i+1:2d}/{len(RAW_MODULES)}] {name:20} (уже есть)")
                    else:
                        print(f"  ❌ [{i+1:2d}/{len(RAW_MODULES)}] {url.split('/')[-1]:20} ({resp.status})")
            except Exception as e:
                print(f"  ❌ [{i+1:2d}/{len(RAW_MODULES)}] {url.split('/')[-1]:20} (ошибка)")
    
    print("\n" + "=" * 50)
    print("📊 ИТОГИ:")
    for folder in ["hikka_samples", "mcub_samples", "hydra_samples"]:
        count = len(list((training_dir / folder).glob("*.py")))
        print(f"  {folder}: {count}")
    
    print(f"\n✅ ВСЕГО: {sum(len(list((training_dir / f).glob('*.py'))) for f in ['hikka_samples', 'mcub_samples', 'hydra_samples'])}")

asyncio.run(download())
