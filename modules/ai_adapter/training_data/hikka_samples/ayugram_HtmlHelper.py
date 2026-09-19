# meta developer: @C00l9r
# meta name: HtmlHelper
# meta version: 9.0.0
# meta banner: https://yufic.ru/api/hc/?a=HtmlHelper&b=@C00l9r
# requires: requests beautifulsoup4

import io
import os
import re
import base64
import zipfile
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class HtmlHelperMod(loader.Module):
    """Получает исходный код веб-страницы (HTML, CSS, JS, изображения)."""

    strings = {
        "name": "HtmlHelper",
        "processing": "<emoji document_id=5429411030960711866>💬</emoji> <b>Получаю HTML сайта...</b>",
        "no_url": "<emoji document_id=5260342697075416641>❌</emoji> <b>Укажите URL сайта после команды.</b>\n<code>.html https://example.com</code>",
        "fetch_error": "<emoji document_id=5260342697075416641>❌</emoji> <b>Не удалось получить код сайта.</b>\n<b>Ошибка:</b> <code>{}</code>",
        "caption": "<emoji document_id=5257965810634202885>📁</emoji> <b>Исходный код сайта</b> <code>{}</code>",
    }

    strings_ru = {
        "_cls_doc": "Получает исходный код веб-страницы (HTML, CSS, JS, изображения).",
        "_cmd_doc_html": "<ссылка> - Получить исходный код сайта"
    }

    async def _ultra_download(self, url, resource_type="html"):
        """Ультра-агрессивное скачивание с обходом всех защит"""
        # Разные User-Agents для обхода блокировок
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)',
        ]
        
        # Разные методы обхода
        methods = [
            {'verify': False, 'timeout': 20, 'allow_redirects': True},
            {'verify': True, 'timeout': 25, 'allow_redirects': True},
            {'verify': False, 'timeout': 30, 'allow_redirects': False},
            {'verify': True, 'timeout': 15, 'allow_redirects': True, 'proxies': {}},
        ]
        
        for ua_index, user_agent in enumerate(user_agents):
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document' if resource_type == 'html' else resource_type,
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            }
            
            # Добавляем специфичные заголовки для разных типов ресурсов
            if resource_type == 'css':
                headers['Accept'] = 'text/css,*/*;q=0.1'
            elif resource_type == 'js':
                headers['Accept'] = 'application/javascript,*/*;q=0.8'
            elif resource_type == 'image':
                headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
            
            for method_index, method in enumerate(methods):
                try:
                    response = await utils.run_sync(
                        requests.get, url, 
                        headers=headers,
                        **method
                    )
                    
                    if response.status_code == 200:
                        # Для изображений возвращаем бинарные данные
                        if resource_type == 'image':
                            return response.content
                        else:
                            return response.text
                    
                    # Обход 403/429
                    elif response.status_code in [403, 429]:
                        # Пробуем добавить реферер
                        headers['Referer'] = url
                        continue
                        
                    # Обход 404 - пробуем альтернативные пути
                    elif response.status_code == 404:
                        # Пробуем без query параметров
                        parsed = urlparse(url)
                        if parsed.query:
                            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                            continue
                            
                except Exception as e:
                    if ua_index == len(user_agents) - 1 and method_index == len(methods) - 1:
                        return None
                    continue
                
        return None

    async def _extract_everything(self, html_code, base_url):
        """Извлекает ВСЕ что возможно найти на странице"""
        soup = BeautifulSoup(html_code, 'html.parser')
        resources = {
            'css': [],
            'js': [], 
            'images': [],
            'fonts': [],
            'videos': [],
            'other': []
        }
        
        log = ["🚀 <b>НАЧАЛО ЭКСТРАКЦИИ ВСЕХ РЕСУРСОВ</b>"]
        
        # 1. СТАНДАРТНЫЕ ТЕГИ
        log.append("\n📄 <b>1. СТАНДАРТНЫЕ HTML ТЕГИ:</b>")
        
        # CSS через link
        css_links = soup.find_all('link', rel='stylesheet')
        log.append(f"   CSS links: {len(css_links)}")
        for link in css_links:
            href = link.get('href')
            if href:
                full_url = urljoin(base_url, href)
                content = await self._ultra_download(full_url, 'css')
                if content:
                    resources['css'].append({
                        'url': full_url,
                        'content': content,
                        'type': 'link_css',
                        'original': href
                    })
        
        # JS через script
        js_scripts = soup.find_all('script', src=True)
        log.append(f"   JS scripts: {len(js_scripts)}")
        for script in js_scripts:
            src = script.get('src')
            if src:
                full_url = urljoin(base_url, src)
                content = await self._ultra_download(full_url, 'js')
                if content:
                    resources['js'].append({
                        'url': full_url,
                        'content': content,
                        'type': 'script_js', 
                        'original': src
                    })
        
        # Изображения
        images = soup.find_all('img', src=True)
        log.append(f"   Images: {len(images)}")
        for img in images:
            src = img.get('src')
            if src and not src.startswith('data:'):
                full_url = urljoin(base_url, src)
                content = await self._ultra_download(full_url, 'image')
                if content:
                    # Конвертируем в base64 для встраивания
                    b64_content = base64.b64encode(content).decode('utf-8')
                    resources['images'].append({
                        'url': full_url,
                        'content': b64_content,
                        'type': 'image',
                        'original': src,
                        'mime': 'image/jpeg'  # Базовое предположение
                    })
        
        # 2. АГРЕССИВНЫЙ ПОИСК ПО РЕГУЛЯРКАМ
        log.append("\n🔎 <b>2. АГРЕССИВНЫЙ РЕГУЛЯРНЫЙ ПОИСК:</b>")
        
        patterns = {
            'css': [
                r'url\([\'"]?([^\)]*\.css[^\)\?]*)(?:\?[^\)]*)?[\'"]?\)',
                r'@import\s+[\'"]([^\'"]*\.css[^\'"]*)[\'"]',
                r'loadCSS\([\'"]?([^\'"]*\.css[^\'"]*)[\'"]?\)',
                r'stylesheet[\'"]?\s*:\s*[\'"]([^\'"]*\.css[^\'"]*)[\'"]',
            ],
            'js': [
                r'src=[\'"]([^\'"]*\.js(?:\?[^\'"]*)?)[\'"]',
                r'require\([\'"]?([^\'"]*\.js[^\'"]*)[\'"]?\)',
                r'import\([\'"]?([^\'"]*\.js[^\'"]*)[\'"]?\)',
                r'loadScript\([\'"]?([^\'"]*\.js[^\'"]*)[\'"]?\)',
                r'script[\'"]?\s*:\s*[\'"]([^\'"]*\.js[^\'"]*)[\'"]',
            ],
            'images': [
                r'url\([\'"]?([^\)]*\.(?:jpg|jpeg|png|gif|webp|svg)[^\)\?]*)(?:\?[^\)]*)?[\'"]?\)',
                r'src=[\'"]([^\'"]*\.(?:jpg|jpeg|png|gif|webp|svg)(?:\?[^\'"]*)?)[\'"]',
                r'background[\'"]?\s*:\s*[\'"]?url\([\'"]?([^\)]*\.(?:jpg|jpeg|png|gif|webp)[^\)]*)[\'"]?\)',
                r'background-image[\'"]?\s*:\s*[\'"]?url\([\'"]?([^\)]*\.(?:jpg|jpeg|png|gif|webp)[^\)]*)[\'"]?\)',
            ]
        }
        
        # Ищем во всем HTML и уже найденных ресурсах
        all_text = html_code + "\n".join([
            r['content'] for r in resources['css'] + resources['js'] 
            if r.get('content')
        ])
        
        for resource_type, type_patterns in patterns.items():
            found_count = 0
            for pattern in type_patterns:
                matches = re.findall(pattern, all_text, re.IGNORECASE)
                for match in matches:
                    if match and not any(match in r.get('original', '') for r in resources[resource_type]):
                        # Нормализуем URL
                        if not match.startswith(('http', '//', 'data:')):
                            full_url = urljoin(base_url, match)
                        else:
                            full_url = match if match.startswith('http') else 'https:' + match
                        
                        # Скачиваем
                        content = await self._ultra_download(full_url, resource_type)
                        if content:
                            resource_data = {
                                'url': full_url,
                                'type': f'regex_{resource_type}',
                                'original': match
                            }
                            
                            if resource_type == 'images':
                                resource_data['content'] = base64.b64encode(content).decode('utf-8')
                                resource_data['mime'] = 'image/jpeg'
                            else:
                                resource_data['content'] = content
                            
                            resources[resource_type].append(resource_data)
                            found_count += 1
            
            log.append(f"   {resource_type.upper()} через regex: {found_count}")
        
        # 3. ДИНАМИЧЕСКИЙ АНАЛИЗ JS КОДА
        log.append("\n⚡ <b>3. ДИНАМИЧЕСКИЙ АНАЛИЗ JS:</b>")
        
        # Анализируем JS код на предмет динамической загрузки
        js_analysis_count = 0
        for js_resource in resources['js']:
            js_code = js_resource['content']
            
            # Ищем fetch/axios/ajax запросы
            dynamic_patterns = [
                r'fetch\([\'"]?([^\'"]*\.(?:css|js)[^\'"]*)[\'"]?\)',
                r'axios\.get\([\'"]?([^\'"]*\.(?:css|js)[^\'"]*)[\'"]?\)',
                r'\$\.get\([\'"]?([^\'"]*\.(?:css|js)[^\'"]*)[\'"]?\)',
                r'load\([\'"]?([^\'"]*\.(?:css|js)[^\'"]*)[\'"]?\)',
                r'import\([\'"]?([^\'"]*\.(?:css|js)[^\'"]*)[\'"]?\)',
            ]
            
            for pattern in dynamic_patterns:
                matches = re.findall(pattern, js_code, re.IGNORECASE)
                for match in matches:
                    if match and not any(match in r.get('original', '') for r in resources['css'] + resources['js']):
                        full_url = urljoin(base_url, match)
                        content = await self._ultra_download(full_url, 'css' if match.endswith('.css') else 'js')
                        if content:
                            target_type = 'css' if match.endswith('.css') else 'js'
                            resources[target_type].append({
                                'url': full_url,
                                'content': content,
                                'type': f'js_dynamic_{target_type}',
                                'original': match
                            })
                            js_analysis_count += 1
        
        log.append(f"   Ресурсов через JS анализ: {js_analysis_count}")
        
        # 4. ВСТРОЕННЫЕ РЕСУРСЫ
        log.append("\n💎 <b>4. ВСТРОЕННЫЕ РЕСУРСЫ:</b>")
        
        # Встроенные стили
        inline_styles = soup.find_all('style')
        for style in inline_styles:
            if style.string:
                resources['css'].append({
                    'url': 'inline_style',
                    'content': style.string,
                    'type': 'inline_css',
                    'original': 'inline'
                })
        
        # Встроенные скрипты
        inline_scripts = [s for s in soup.find_all('script') if s.string and not s.get('src')]
        for script in inline_scripts:
            resources['js'].append({
                'url': 'inline_script',
                'content': script.string,
                'type': 'inline_js',
                'original': 'inline'
            })
        
        log.append(f"   Встроенных стилей: {len(inline_styles)}")
        log.append(f"   Встроенных скриптов: {len(inline_scripts)}")
        
        # ИТОГИ
        log.append(f"\n📊 <b>ИТОГИ ЭКСТРАКЦИИ:</b>")
        for resource_type, items in resources.items():
            log.append(f"   {resource_type.upper()}: {len(items)}")
        
        return resources, log

    def _create_complete_html(self, original_html, all_resources):
        """Создает полный HTML со ВСЕМИ ресурсами"""
        soup = BeautifulSoup(original_html, 'html.parser')
        
        # Удаляем ВСЕ внешние ресурсы
        for tag in soup.find_all(['link', 'script', 'img']):
            if tag.get('src') or tag.get('href'):
                tag.decompose()
        
        # Добавляем ВЕСЬ CSS
        if all_resources['css']:
            combined_css = "/* === COMBINED CSS === */\n\n"
            for i, css in enumerate(all_resources['css']):
                combined_css += f"/* --- {i+1}. {css['type']}: {css['url']} --- */\n"
                combined_css += css['content'] + "\n\n"
            
            style_tag = soup.new_tag('style')
            style_tag.string = combined_css
            
            if not soup.head:
                soup.html.insert(0, soup.new_tag('head'))
            soup.head.append(style_tag)
        
        # Добавляем ВЕСЬ JS
        if all_resources['js']:
            for i, js in enumerate(all_resources['js']):
                script_tag = soup.new_tag('script')
                comment = f"\n/* JS {i+1}. {js['type']}: {js['url']} */\n"
                script_tag.string = comment + js['content']
                
                if not soup.body:
                    soup.append(soup.new_tag('body'))
                soup.body.append(script_tag)
        
        # Заменяем изображения на base64
        if all_resources['images']:
            for i, img in enumerate(all_resources['images']):
                # Создаем новый img тег с base64
                new_img = soup.new_tag('img')
                new_img['src'] = f"data:image/jpeg;base64,{img['content']}"
                new_img['alt'] = f"Extracted image {i+1}"
                
                if soup.body:
                    soup.body.append(new_img)
        
        return str(soup)

    @loader.command(ru_doc="<ссылка> - Получить исходный код сайта")
    async def html(self, message: Message):
        """<url> - Get complete website source with all resources"""
        args = utils.get_args_raw(message)
        
        if not args:
            await utils.answer(message, self.strings("no_url"))
            return

        url = args.strip()
        if not url.startswith("http"):
            url = "https://" + url

        message = await utils.answer(message, self.strings("processing"))

        try:
            # Скачиваем основную страницу
            html_code = await self._ultra_download(url, 'html')
            if not html_code:
                await utils.answer(message, self.strings("fetch_error").format("Не удалось скачать HTML"))
                return
                
            base_url = url
        except Exception as e:
            await utils.answer(message, self.strings("fetch_error").format(e))
            return

        # ЭКСТРАКЦИЯ ВСЕГО
        all_resources, extraction_log = await self._extract_everything(html_code, base_url)
        
        # Создаем полный HTML
        complete_html = self._create_complete_html(html_code, all_resources)
        
        # Отправляем файл
        file_to_send = io.BytesIO(complete_html.encode('utf-8'))
        file_to_send.name = f"complete_site_{hash(url) % 10000}.html"
        caption = self.strings("caption").format(url)

        await self.client.send_file(
            message.to_id,
            file_to_send,
            caption=caption,
            reply_to=message.reply_to_msg_id,
        )
        
        # Отправляем МЕГА-ЛОГИ
        log_header = (
            f"🚀 <b>HTML HELPER - ПОЛНЫЙ ОТЧЕТ</b>\n\n"
            f"<b>Целевой URL:</b> <code>{url}</code>\n"
            f"<b>Размер HTML:</b> {len(html_code):,} chars\n"
            f"<b>Итоговый размер:</b> {len(complete_html):,} chars\n\n"
        )
        
        # Статистика по ресурсам
        stats = "<b>📊 СТАТИСТИКА РЕСУРСОВ:</b>\n"
        for resource_type, items in all_resources.items():
            stats += f"   {resource_type.upper()}: {len(items)}\n"
        
        full_log = log_header + stats + "\n" + "\n".join(extraction_log)
        
        # Разбиваем длинные логи
        if len(full_log) > 4000:
            parts = [full_log[i:i+4000] for i in range(0, len(full_log), 4000)]
            for part in parts:
                await self.client.send_message(
                    message.to_id,
                    part,
                    reply_to=message.reply_to_msg_id,
                )
        else:
            await self.client.send_message(
                message.to_id,
                full_log,
                reply_to=message.reply_to_msg_id,
            )
        
        if message.out:
            await message.delete()