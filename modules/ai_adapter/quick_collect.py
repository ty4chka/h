import aiohttp
import asyncio
from pathlib import Path

# ПРЯМЫЕ RAW ССЫЛКИ НА ИЗВЕСТНЫЕ МОДУЛИ (без API!)
RAW_URLS = [
    # FTG модули
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
    "https://raw.githubusercontent.com/hikariatama/ftg/master/backuper.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/speller.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/spotify.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/youtube.py",
    "https://raw.githubusercontent.com/hikariatama/ftg/master/voicechat.py",
    
    # Nalinor модули
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/membersquery.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/speedtest.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/swmute.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/msgrate.py",
    "https://raw.githubusercontent.com/iamnalinor/FTG-modules/main/lavhost.py",
    
    # Heroku модули
    "https://raw.githubusercontent.com/coddrago/Heroku/main/ping.py",
    "https://raw.githubusercontent.com/coddrago/Heroku/main/info.py",
    "https://raw.githubusercontent.com/coddrago/Heroku/main/help.py",
    
    # DeBot модули (Hydra)
    "https://raw.githubusercontent.com/DeBotCommunity/DeBot/main/modules/ping.py",
    "https://raw.githubusercontent.com/DeBotCommunity/CryptoBalance/main/crypto_balance.py",
    "https://raw.githubusercontent.com/DeBotCommunity/System-Info/main/system_info.py",
    "https://raw.githubusercontent.com/DeBotCommunity/InfoFromUser/main/user_info.py",
    "https://raw.githubusercontent.com/DeBotCommunity/CryptoRates/main/crypto_rates.py",
    "https://raw.githubusercontent.com/DeBotCommunity/MagicDownloader/main/magic_downloader.py",
    
    # MCUB модули
    "https://raw.githubusercontent.com/hairpin01/MCUB-fork/main/modules/ping.py",
    "https://raw.githubusercontent.com/hairpin01/MCUB-fork/main/modules/info.py",
]

async def download():
    training_dir = Path("training_data")
    
    async with aiohttp.ClientSession() as session:
        for url in RAW_URLS:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        code = await resp.text()
                        name = url.split("/")[-1]
                        
                        # Определяем тип по URL
                        if "mcub" in url.lower():
                            folder = "mcub_samples"
                        elif "debot" in url.lower():
                            folder = "hydra_samples"
                        else:
                            folder = "hikka_samples"
                        
                        target = training_dir / folder / name
                        target.write_text(code, encoding='utf-8')
                        print(f"✅ {name} -> {folder}")
            except Exception as e:
                print(f"❌ {url}: {e}")

asyncio.run(download())
