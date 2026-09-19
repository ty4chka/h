"""
GitHub Collector - Скачивает ВСЕ .py файлы из ВСЕХ репозиториев
"""

import aiohttp
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# ВСЕ РЕПОЗИТОРИИ С МОДУЛЯМИ
ALL_REPOS = [
    # Hikka/FTG модули
    "https://api.github.com/repos/hikariatama/ftg/contents",
    "https://api.github.com/repos/iamnalinor/FTG-modules/contents",
    "https://api.github.com/repos/GeekTG/FTG-Modules/contents",
    "https://api.github.com/repos/IOPjjkl/Hizuko/contents",
    "https://api.github.com/repos/coddrago/Heroku/contents",
    "https://api.github.com/repos/anon97945/hikka-mods/contents",
    "https://api.github.com/repos/apcecoc/GPT-4o-API-for-Hikka-Userbot/contents",
    
    # MCUB модули
    "https://api.github.com/repos/hairpin01/MCUB-fork/contents/modules",
    "https://api.github.com/repos/MItrich/MCUB/contents/modules",
    
    # DeBot модули (Hydra)
    "https://api.github.com/repos/DeBotCommunity/DeBot/contents/modules",
    "https://api.github.com/repos/DeBotCommunity/CryptoCheckBot/contents",
    "https://api.github.com/repos/DeBotCommunity/CryptoBalance/contents",
    "https://api.github.com/repos/DeBotCommunity/System-Info/contents",
    "https://api.github.com/repos/DeBotCommunity/MagicDownloader/contents",
    "https://api.github.com/repos/DeBotCommunity/CryptoRates/contents",
    "https://api.github.com/repos/DeBotCommunity/InfoFromUser/contents",
    "https://api.github.com/repos/DeBotCommunity/Telegram-TTL-Photo-Saver/contents",
    
    # Другие юзерботы
    "https://api.github.com/repos/AmanoTeam/UserLixo/contents",
]

class GitHubCollector:
    def __init__(self, training_dir: Path):
        self.training_dir = training_dir
        self.session = None
        
        for sub in ["hikka_samples", "mcub_samples", "hydra_samples"]:
            (self.training_dir / sub).mkdir(parents=True, exist_ok=True)
    
    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": "Hydra-Collector/1.0"},
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def fetch_api(self, url: str) -> Optional[list]:
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"    ⚠️ {resp.status}")
        except Exception as e:
            print(f"    ❌ {e}")
        return None
    
    async def scan_directory(self, url: str, depth: int = 0) -> int:
        if depth > 2:
            return 0
        
        items = await self.fetch_api(url)
        if not items:
            return 0
        
        collected = 0
        
        for item in items:
            if item["type"] == "file" and item["name"].endswith(".py"):
                code = await self.download_file(item["download_url"])
                if code and len(code) > 100:
                    saved = self.save_module(code, item["name"], item["html_url"])
                    if saved:
                        collected += 1
                        if collected % 10 == 0:
                            print(f"    ✅ {collected} модулей...")
                
                await asyncio.sleep(0.1)
            
            elif item["type"] == "dir" and not item["name"].startswith("."):
                sub = await self.scan_directory(item["url"], depth + 1)
                collected += sub
        
        return collected
    
    async def download_file(self, url: str) -> Optional[str]:
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.text()
        except:
            pass
        return None
    
    def save_module(self, code: str, filename: str, source_url: str) -> bool:
        from .ast_analyzer import ModuleASTAnalyzer
        
        analyzer = ModuleASTAnalyzer(code)
        detected = analyzer.analyze().get("module_type", "hikka")
        
        type_map = {"hikka": "hikka_samples", "mcub": "mcub_samples", "hydra": "hydra_samples"}
        target_dir = type_map.get(detected, "hikka_samples")
        
        safe_name = filename.replace(".py", "").replace("/", "_")[:50]
        target_file = self.training_dir / target_dir / f"{safe_name}.py"
        
        if target_file.exists():
            return False
        
        metadata = f"# SOURCE: {source_url}\n# DATE: {datetime.now().isoformat()}\n\n"
        
        try:
            target_file.write_text(metadata + code, encoding='utf-8')
            return True
        except:
            return False
    
    async def collect_all(self) -> Dict:
        print("🌐 МАССОВЫЙ СБОР МОДУЛЕЙ")
        print("=" * 50)
        print(f"📦 Репозиториев: {len(ALL_REPOS)}\n")
        
        total = 0
        
        for i, api_url in enumerate(ALL_REPOS):
            repo_name = api_url.split("/")[5]
            print(f"[{i+1}/{len(ALL_REPOS)}] {repo_name}...")
            
            collected = await self.scan_directory(api_url)
            total += collected
            
            print(f"    📊 +{collected} (всего: {total})\n")
            await asyncio.sleep(0.5)
        
        print("=" * 50)
        print(f"✅ ВСЕГО СОБРАНО: {total} модулей")
        
        return {"total": total}

async def main():
    training_dir = Path(__file__).parent / "training_data"
    collector = GitHubCollector(training_dir)
    await collector.collect_all()
    await collector.close()

if __name__ == "__main__":
    asyncio.run(main())
