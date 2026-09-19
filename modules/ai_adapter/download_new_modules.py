"""
Скачивание модулей из новых источников
"""

import aiohttp
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from ai_adapter.ast_analyzer import ModuleASTAnalyzer

# Новые источники
SOURCES = {
    "codrago_modules": [
        "pmban", "ascii_face", "send", "modlist", "randomizer", "loli",
        "speedtest", "hentai", "emojidown", "id", "DelMessTools", "DoxTool",
        "lastfm", "promoclaimer", "autoclicker", "randnum", "passwordgen",
        "compliments", "figlet"
    ],
    "fheta": [
        "https://raw.githubusercontent.com/Fixyres/FModules/refs/heads/main/FHeta.py"
    ],
    "mofko": [
        "https://api.fixyres.com/module/mofko/MofkoModules/РАТКОВiрусиЭпштеiнHeta.py"
    ]
}

class NewModuleCollector:
    def __init__(self, training_dir: Path):
        self.training_dir = training_dir
        self.codrago_base = "https://mods.codrago.life/modules/"
        
        for sub in ["hikka_samples", "mcub_samples", "hydra_samples"]:
            (self.training_dir / sub).mkdir(parents=True, exist_ok=True)
    
    async def download_file(self, url: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except:
            pass
        return ""
    
    async def collect_all(self):
        print("🌐 СБОР МОДУЛЕЙ ИЗ НОВЫХ ИСТОЧНИКОВ")
        print("=" * 50)
        
        total = 0
        
        # 1. Codrago модули
        print("\n📦 CODRAGO MODULES:")
        for name in SOURCES["codrago_modules"]:
            url = f"{self.codrago_base}{name}.py"
            print(f"    📥 {name}...", end=" ")
            
            code = await self.download_file(url)
            if code:
                analyzer = ModuleASTAnalyzer(code)
                detected = analyzer.analyze().get("module_type", "hikka")
                
                folder = f"{detected}_samples"
                target = self.training_dir / folder / f"codrago_{name}.py"
                target.write_text(code, encoding='utf-8')
                total += 1
                print(f"✅ ({detected})")
            else:
                print("❌")
            
            await asyncio.sleep(0.3)
        
        # 2. FHeta модуль
        print("\n📦 FHETA MODULE:")
        for url in SOURCES["fheta"]:
            name = url.split("/")[-1]
            print(f"    📥 {name}...", end=" ")
            
            code = await self.download_file(url)
            if code:
                analyzer = ModuleASTAnalyzer(code)
                detected = analyzer.analyze().get("module_type", "hikka")
                
                folder = f"{detected}_samples"
                target = self.training_dir / folder / f"fheta_{name}"
                target.write_text(code, encoding='utf-8')
                total += 1
                print(f"✅ ({detected})")
            else:
                print("❌")
        
        # 3. Mofko модуль
        print("\n📦 MOFKO MODULE:")
        for url in SOURCES["mofko"]:
            name = "MofkoHeta.py"
            print(f"    📥 {name}...", end=" ")
            
            code = await self.download_file(url)
            if code:
                analyzer = ModuleASTAnalyzer(code)
                detected = analyzer.analyze().get("module_type", "hikka")
                
                folder = f"{detected}_samples"
                target = self.training_dir / folder / "mofko_heta.py"
                target.write_text(code, encoding='utf-8')
                total += 1
                print(f"✅ ({detected})")
            else:
                print("❌")
        
        print("\n" + "=" * 50)
        print(f"✅ ВСЕГО ДОБАВЛЕНО: {total} модулей")
        
        # Статистика
        print("\n📊 ОБЩАЯ СТАТИСТИКА:")
        for folder in ["hikka_samples", "mcub_samples", "hydra_samples"]:
            count = len(list((self.training_dir / folder).glob("*.py")))
            print(f"    {folder}: {count}")

async def main():
    training_dir = Path("training_data")
    collector = NewModuleCollector(training_dir)
    await collector.collect_all()

if __name__ == "__main__":
    asyncio.run(main())
