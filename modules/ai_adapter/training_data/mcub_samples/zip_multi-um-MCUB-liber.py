# github: https://github.com/hairpin01/repo-MCUB-fork/liber/
# Channel: https://t.me/LinuxGram2
# -------------------- Meta data ---------------------------
# requires:
# author: Hairpin00
# version: 1.0.1
# description: ru Модуль для массовой выгрузки нескольких модулей за раз / en Module for unloading multiple modules at once
# ----------------------- End ------------------------------

import os
import sys

def register(kernel):
    client = kernel.client
    language = kernel.config.get('language', 'en')

    strings = {
        'en': {
            'usage': '❌ <b>Usage:</b> <code>{prefix}ulm module1, module2, module3</code>',
            'no_modules': '❌ <b>No modules specified</b>',
            'summary': 'Success: {success} | Failed: {failed}\n<b>Results:</b>\n{results}',
            'result_success': '<b>{module}</b>: unloaded',
            'result_not_found': '<b>{module}</b>: not found',
            'result_error': '❌ <b>{module}</b>: error: {error}',
            'log_message': 'Bulk module unload completed: {success} successful, {failed} errors'
        },
        'ru': {
            'usage': '❌ <b>Использование:</b> <code>{prefix}ulm module1, module2, module3</code>',
            'no_modules': '❌ <b>Не указаны модули для выгрузки</b>',
            'summary': 'Успешно: {success} | Не удалось: {failed}\n<b>Результаты:</b>\n{results}',
            'result_success': '<b>{module}</b>: выгружен',
            'result_not_found': '<b>{module}</b>: не найден',
            'result_error': '❌ <b>{module}</b>: ошибка: {error}',
            'log_message': 'Массовая выгрузка модулей завершена: {success} успешно, {failed} ошибок'
        }
    }

    lang_strings = strings.get(language, strings['en'])

    def t(key, **kwargs):
        if key not in lang_strings:
            return key
        return lang_strings[key].format(**kwargs)

    @kernel.register.command('ulm', alias=['multiunload', 'unloadmulti'])
    # ru Выгрузить несколько модулей за раз (через запятую) / en Unload multiple modules at once (comma-separated)
    async def unload_multiple_handler(event):
        args = event.text.split(maxsplit=1)

        if len(args) < 2:
            await event.edit(
                t('usage', prefix=kernel.custom_prefix),
                parse_mode='html'
            )
            return

        modules_input = args[1]
        modules_list = [m.strip() for m in modules_input.split(',')]

        if not modules_list:
            await event.edit(t('no_modules'), parse_mode='html')
            return

        success_count = 0
        failed_count = 0
        results = []

        for module_name in modules_list:
            if not module_name:
                continue

            if module_name not in kernel.loaded_modules:
                results.append(t('result_not_found', module=module_name))
                failed_count += 1
                continue

            try:
                kernel.unregister_module_commands(module_name)

                file_path = os.path.join(kernel.MODULES_LOADED_DIR, f"{module_name}.py")
                if os.path.exists(file_path):
                    os.remove(file_path)

                if module_name in sys.modules:
                    del sys.modules[module_name]

                if module_name in kernel.loaded_modules:
                    del kernel.loaded_modules[module_name]

                results.append(t('result_success', module=module_name))
                success_count += 1

            except Exception as e:
                kernel.logger.error(f"Ошибка выгрузки модуля {module_name}: {e}")
                error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
                results.append(t('result_error', module=module_name, error=error_msg))
                failed_count += 1

        summary = t('summary',
                   success=success_count,
                   failed=failed_count,
                   results="\n".join(results))

        if success_count > 0:
            if hasattr(kernel, "logger"):
                kernel.logger.info(f"> {t('log_message', success=success_count, failed=failed_count)}")

        await event.edit(summary, parse_mode='html')
