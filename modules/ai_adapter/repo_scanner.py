"""
Repo Scanner - Скачивает ВСЕ .py файлы из указанных репозиториев
"""

import aiohttp
import asyncio
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

from ai_adapter.ast_analyzer import ModuleASTAnalyzer

# Репозитории для сканирования (через GitHub API)
REPOS = [
    "hikariatama/ftg",
    "GeekTG/FTG-Modules", 
    "IOPjjkl/Hizuko",
    "Netfoll/UserBot-Fork",
    "coddrago/Heroku",
    "AmanoTeam/UserLixo",
    "DeBotCommunity/DeBot",
]

async def scan_repo(session, repo):
    """Сканирует репозиторий рекурсивно"""
    collected = []
    
    async def scan_path(path=""):
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    items = await resp.json()
                    if not isinstance(items, list):
                        items = [items]
                    
                    for item in items:
                        if item["type"] == "file" and item["name"].endswith(".py"):
                            # Скачиваем .py файл
                            code_url = item["download_url"]
                            async with session.get(code_url) as code_resp:
                                if code_resp.status == 200:
                                    code = await code_resp.text()
                                    collected.append({
                                        "name": item["name"],
                                        "code": code,
                                        "repo": repo
                                    })
                            await asyncio.sleep(0.1)
                        
                        elif item["type"] == "dir" and not item["name"].startswith("."):
                            await scan_path(item["path"])
                            
        except Exception as e:
            print(f"    ⚠️ {e}")
    
    await scan_path()
    return collected

async def main():
    training_dir = Path("training_data")
    for sub in ["hikka_samples", "mcub_samples", "hydra_samples"]:
        (training_dir / sub).mkdir(parents=True, exist_ok=True)
    
    print("🌐 СКАНИРОВАНИЕ РЕПОЗИТОРИЕВ")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        total = 0
        
        for repo in REPOS:
            print(f"\n📦 {repo}...")
            modules = await scan_repo(session, repo)
            
            for mod in modules:
                # Определяем тип
                analyzer = ModuleASTAnalyzer(mod["code"])
                detected = analyzer.analyze().get("module_type", "hikka")
                
                folder = f"{detected}_samples"
                name = f"{repo.replace('/', '_')}_{mod['name']}"
                target = training_dir / folder / name
                
                if not target.exists():
                    target.write_text(mod["code"], encoding='utf-8')
                    total += 1
            
            print(f"    ✅ +{len(modules)} модулей (всего: {total})")
            await asyncio.sleep(0.5)
    
    print("\n" + "=" * 50)
    print(f"✅ ВСЕГО СОБРАНО: {total} модулей")

asyncio.run(main())
