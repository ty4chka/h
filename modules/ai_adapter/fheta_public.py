"""
FHeta Public Collector - Использует публичные эндпоинты API
"""

import aiohttp
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from ai_adapter.ast_analyzer import ModuleASTAnalyzer

# Популярные запросы
SEARCH_QUERIES = [
    "ping", "info", "help", "weather", "translate", "crypto",
    "notes", "todo", "terminal", "server", "user", "admin",
    "ban", "mute", "warn", "purge", "stats", "backup",
    "youtube", "spotify", "instagram", "tiktok", "github",
    "qr", "carbon", "sticker", "gif", "anime", "manga"
]

class FHetaPublicCollector:
    def __init__(self, training_dir: Path):
        self.training_dir = training_dir
        self.search_url = "https://api.fixyres.com/search"
        self.modules_url = "https://api.fixyres.com/modules"  # Публичный список
        
        for sub in ["hikka_samples", "mcub_samples", "hydra_samples"]:
            (self.training_dir / sub).mkdir(parents=True, exist_ok=True)
    
    async def get_popular_modules(self, limit: int = 100) -> list:
        """Получает популярные модули (публичный эндпоинт)"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "FHeta/9.3.5",
                    "Accept": "application/json"
                }
                # Пробуем получить список модулей
                async with session.get(
                    f"{self.modules_url}?limit={limit}",
                    headers=headers,
                    timeout=30
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list):
                            return data
        except Exception as e:
            print(f"    ⚠️ Error: {e}")
        return []
    
    async def search_modules(self, query: str) -> list:
        """Поиск модулей (публичный)"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "query": query,
                    "inline": "false"
                }
                headers = {
                    "User-Agent": "FHeta/9.3.5",
                    "Accept": "application/json"
                }
                async with session.get(
                    self.search_url,
                    params=params,
                    headers=headers,
                    timeout=30
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list):
                            return data[:10]  # Берём первые 10
        except Exception as e:
            print(f"    ⚠️ {e}")
        return []
    
    async def download_module(self, install_url: str) -> str:
        """Скачивает код модуля"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(install_url, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except:
            pass
        return ""
    
    async def collect_all(self):
        """Сбор модулей"""
        print("🌐 FHETA PUBLIC COLLECTOR")
        print("=" * 50)
        
        total = 0
        seen = set()
        
        # 1. Пробуем получить популярные модули
        print("\n📦 Популярные модули...")
        popular = await self.get_popular_modules(50)
        print(f"    Найдено: {len(popular)}")
        
        # 2. Поиск по запросам
        print(f"\n🔍 Поиск по {len(SEARCH_QUERIES)} запросам...")
        
        for i, query in enumerate(SEARCH_QUERIES[:15]):  # Ограничиваем для скорости
            print(f"    [{i+1:2d}] {query}...", end=" ")
            
            modules = await self.search_modules(query)
            print(f"найдено {len(modules)}")
            
            for mod in modules:
                install_url = mod.get('install', '') or mod.get('url', '')
                if not install_url or install_url in seen:
                    continue
                
                seen.add(install_url)
                
                code = await self.download_module(install_url)
                if not code or len(code) < 100:
                    continue
                
                # Определяем тип
                analyzer = ModuleASTAnalyzer(code)
                detected = analyzer.analyze().get("module_type", "hikka")
                
                # Сохраняем
                folder = f"{detected}_samples"
                name = mod.get('name', f'mod_{total}').replace('/', '_')[:50]
                target = self.training_dir / folder / f"{name}.py"
                
                if not target.exists():
                    metadata = f"# FHeta: {query}\n# Author: {mod.get('author', 'unknown')}\n\n"
                    target.write_text(metadata + code, encoding='utf-8')
                    total += 1
            
            await asyncio.sleep(0.3)
        
        print("\n" + "=" * 50)
        print(f"✅ ВСЕГО СОБРАНО: {total} модулей")
        
        # Статистика по папкам
        print("\n📊 СТАТИСТИКА:")
        for folder in ["hikka_samples", "mcub_samples", "hydra_samples"]:
            count = len(list((self.training_dir /            print(f"    {folder}: {count}")

async def main():
    training_dir = Path("training_data")
    collector = FHetaPublicCollector(training_dir)
    await collector.collect_all()

if __name__ == "__main__":
    asyncio.run(main())
