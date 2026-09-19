"""
FHeta Collector - С токеном авторизации
"""

import aiohttp
import asyncio
import sys
import json
import uuid
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from ai_adapter.ast_analyzer import ModuleASTAnalyzer

# Популярные запросы
SEARCH_QUERIES = [
    "ping", "info", "help", "weather", "translate", "crypto",
    "notes", "todo", "terminal", "server", "user", "admin",
    "ban", "mute", "warn", "purge", "stats", "backup",
    "youtube", "spotify", "insta", "tiktok", "github",
    "qr", "carbon", "sticker", "gif", "anime", "manga"
]

class FHetaCollector:
    def __init__(self, training_dir: Path):
        self.training_dir = training_dir
        self.api_url = "https://api.fixyres.com/search"
        self.uid = str(uuid.uuid4())[:8]  # Генерируем ID
        
        for sub in ["hikka_samples", "mcub_samples", "hydra_samples"]:
            (self.training_dir / sub).mkdir(parents=True, exist_ok=True)
    
    async def get_token(self, session):
        """Получаем токен через бота"""
        # Пробуем получить токен
        try:
            # Публичный токен (если есть)
            return None
        except:
            return None
    
    async def search_modules(self, query: str, limit: int = 10) -> list:
        """Поиск модулей"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "query": query,
                    "inline": "false",
                    "ood": "false",
                    "user_id": self.uid
                }
                headers = {
                    "User-Agent": "FHeta/9.3.5",
                    "Accept": "application/json"
                }
                async with session.get(self.api_url, params=params, headers=headers, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list):
                            return data[:limit]
                    else:
                        print(f"    ⚠️ Status: {resp.status}")
        except Exception as e:
            print(f"    ⚠️ {e}")
        return []
    
    async def collect_all(self, max_per_query: int = 10):
        """Сбор модулей"""
        print("🌐 СБОР МОДУЛЕЙ ЧЕРЕЗ FHETA API")
        print("=" * 50)
        print(f"📦 Запросов: {len(SEARCH_QUERIES)}\n")
        
        total = 0
        
        for i, query in enumerate(SEARCH_QUERIES):
            print(f"[{i+1:2d}/{len(SEARCH_QUERIES)}] Поиск: {query}...")
            
            modules = await self.search_modules(query, max_per_query)
            
            if modules:
                for mod in modules:
                    name = mod.get('name', 'unknown')
                    author = mod.get('author', 'unknown')
                    print(f"    📦 {name} by {author}")
                    total += len(modules)
            else:
                print(f"    ❌ Нет результатов")
            
            await asyncio.sleep(1)
        
        print("\n" + "=" * 50)
        print(f"✅ ВСЕГО НАЙДЕНО: {total} модулей")

async def main():
    training_dir = Path("training_data")
    collector = FHetaCollector(training_dir)
    await collector.collect_all(max_per_query=5)

if __name__ == "__main__":
    asyncio.run(main())
