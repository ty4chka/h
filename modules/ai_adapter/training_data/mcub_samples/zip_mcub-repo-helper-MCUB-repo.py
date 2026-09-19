# requires: aiohttp
# author: MCUB Team
# version: 1.1.0
# description: Модуль для загрузки модулей в репозиторий MCUB

import os
import re
import aiohttp
import base64
from urllib.parse import urljoin

def register(kernel):
    client = kernel.client
    prefix = kernel.custom_prefix


    kernel.config.setdefault('upload-user-key', '')
    kernel.config.setdefault('upload-user-name', '')
    kernel.config.setdefault('upload-repo-name', '')

    GITHUB_API = "https://api.github.com"

    async def get_repo_info():
        token = kernel.config.get('upload-user-key', '')
        username = kernel.config.get('upload-user-name', '')
        repo = kernel.config.get('upload-repo-name', '')

        if not all([token, username, repo]):
            return None, "Не настроены ключи доступа. Используйте .mru -e для настройки"

        return {
            'token': token,
            'username': username,
            'repo': repo
        }, None

    async def github_request(method, endpoint, data=None, headers=None):
        repo_info, error = await get_repo_info()
        if error:
            return None, error

        url = urljoin(GITHUB_API, endpoint)

        default_headers = {
            'Authorization': f'token {repo_info["token"]}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'MCUB-Upload-Module'
        }

        if headers:
            default_headers.update(headers)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.request(
                    method,
                    url,
                    json=data,
                    headers=default_headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 204:
                        return True, None

                    response_data = await response.json()

                    if response.status >= 400:
                        error_msg = response_data.get('message', 'Unknown error')
                        return None, f"GitHub API error: {error_msg}"

                    return response_data, None
            except Exception as e:
                return None, f"Request failed: {str(e)}"

    async def get_file_content(path):

        repo_info, error = await get_repo_info()
        if error:
            return None, error

        endpoint = f"/repos/{repo_info['username']}/{repo_info['repo']}/contents/{path}"
        data, error = await github_request('GET', endpoint)

        if error:
            return None, error

        if data and 'content' in data:
            content = base64.b64decode(data['content']).decode('utf-8')
            return content, None

        return "", None

    async def update_file(path, content, message):
        repo_info, error = await get_repo_info()
        if error:
            return None, error

        endpoint = f"/repos/{repo_info['username']}/{repo_info['repo']}/contents/{path}"


        current_data, _ = await github_request('GET', endpoint)
        sha = current_data.get('sha') if current_data else None

        data = {
            'message': message,
            'content': base64.b64encode(content.encode('utf-8')).decode('utf-8')
        }

        if sha:
            data['sha'] = sha

        result, error = await github_request('PUT', endpoint, data)
        return result, error

    async def upload_module_content(file_content, original_filename, module_name, user_id):
        repo_info, error = await get_repo_info()
        if error:
            return False, error, None

        base_name = os.path.basename(original_filename)
        name_without_ext = os.path.splitext(base_name)[0]

        name_without_suffix = re.sub(r'-MCUB-repo$', '', name_without_ext)


        new_filename = f"{name_without_suffix}-MCUB-repo.py"

        commit_message = f"{module_name} – {user_id}-Uploaded the module"


        result, error = await update_file(
            new_filename,
            file_content,
            commit_message
        )

        return result, error, new_filename

    async def update_modules_ini(module_name, user_id):
        content, error = await get_file_content("modules.ini")
        if error and "404" not in error:
            return False, error


        modules = content.strip().split('\n') if content else []

        if module_name in modules:
            return True, "Модуль уже существует в modules.ini"

        modules.append(module_name)

        new_content = '\n'.join(modules) + '\n'
        commit_message = f"Add {module_name} to modules.ini"

        result, error = await update_file("modules.ini", new_content, commit_message)
        return result, error

    async def update_name_ini(repo_name):
        commit_message = f"Update repository name to {repo_name}"
        result, error = await update_file("name.ini", repo_name, commit_message)
        return result, error

    @kernel.register.command('mru')
    # Загрузить модуль в репозиторий MCUB
    # Использование: .mru -s [имя_файла] -n [имя_модуля]
    # или: .mru -e [новое_имя_репозитория]
    async def mru_command(event):
        try:
            args = event.text.split()


            if '-e' in args:
                idx = args.index('-e')
                if idx + 1 >= len(args):
                    await event.edit("❌ Укажите имя репозитория после -e")
                    return

                new_repo = args[idx + 1]


                kernel.config['upload-repo-name'] = new_repo
                kernel.save_config()


                result, error = await update_name_ini(new_repo)

                if error:
                    await event.edit(f"❌ Ошибка обновления репозитория: {error}")
                else:
                    await event.edit(f"✅ Репозиторий обновлен на: {new_repo}")
                return


            if not event.is_reply:
                await event.edit("❌ Ответьте на файл для загрузки")
                return

            reply = await event.get_reply_message()

            if not reply.file:
                await event.edit("❌ В ответе должен быть файл")
                return

            file_name = None
            module_name = None

            if '-s' in args:
                idx = args.index('-s')
                if idx + 1 < len(args):
                    file_name = args[idx + 1]

            if '-n' in args:
                idx = args.index('-n')
                if idx + 1 < len(args):
                    module_name = args[idx + 1]

            if not file_name:
                file_name = reply.file.name or "module.py"

            if not module_name:
                module_name = os.path.splitext(os.path.basename(file_name))[0]

            await event.edit("📥 Скачиваю файл...")

            file_bytes = await reply.download_media(file=bytes)

            if not file_bytes:
                await event.edit("❌ Не удалось скачать файл")
                return

            try:
                file_content = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                await event.edit("❌ Файл должен быть текстовым (UTF-8)")
                return

            await event.edit("⬆️ Загружаю в репозиторий...")

            result, error, uploaded_filename = await upload_module_content(
                file_content,
                file_name,
                module_name,
                event.sender_id
            )

            if error:
                await event.edit(f"❌ Ошибка загрузки файла: {error}")
                return

            await event.edit("📝 Обновляю modules.ini...")

            result2, error2 = await update_modules_ini(module_name, event.sender_id)

            if error2:
                await event.edit(f"⚠️ Файл загружен как {uploaded_filename}, но ошибка обновления modules.ini: {error2}")
                return

            await event.edit(f"✅ Модуль успешно загружен!\n"
                           f"📄 Файл: {uploaded_filename}\n"
                           f"🏷️  Имя в modules.ini: {module_name}\n"
                           f"👤 ID пользователя: {event.sender_id}")

        except Exception as e:
            await kernel.handle_error(e, source="mru_command", event=event)
            await event.edit("❌ Ошибка при загрузке модуля. Проверьте логи.")

    @kernel.register.command('mru-setup')
    # Настройка параметров загрузки
    async def mru_setup_command(event):
        try:
            args = event.text.split()

            if len(args) < 4:
                await event.edit(
                    "📝 Использование:\n"
                    f"{prefix}mru-setup <ключ_github> <имя_пользователя> <репозиторий>\n\n"
                    "Пример:\n"
                    f"{prefix}mru-setup ghp_abc123 username repo-name"
                )
                return

            token = args[1]
            username = args[2]
            repo = args[3]

            kernel.config['upload-user-key'] = token
            kernel.config['upload-user-name'] = username
            kernel.config['upload-repo-name'] = repo
            kernel.save_config()

            await event.edit(f"✅ Настройки сохранены:\n"
                           f"🔑 Ключ: {token[:10]}...\n"
                           f"👤 Пользователь: {username}\n"
                           f"📁 Репозиторий: {repo}")

        except Exception as e:
            await kernel.handle_error(e, source="mru_setup_command", event=event)
            await event.edit("❌ Ошибка при сохранении настроек")
