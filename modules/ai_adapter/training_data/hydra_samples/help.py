from utils.misc import edit_or_reply, fast_animation
from modules.lang import translator
import difflib
import time


class HelpSystem:
    def __init__(self):
        self.prefix = self.get_prefix()
        self.command_usage = {}
        
    def get_prefix(self):
        try:
            from config import prefix
            return prefix
        except:
            return "."

    def log_command_usage(self, command_name):
        if command_name not in self.command_usage:
            self.command_usage[command_name] = 0
        self.command_usage[command_name] += 1

    async def show_main_help(self, event):
        from utils.loader import modules_help
        
        loading_msg = await edit_or_reply(event, "📚")
        await fast_animation(loading_msg, "📚", f"📚 {translator.get_text(event.sender_id, 'loading')}")
        
        if not modules_help:
            await loading_msg.edit(f"<b>🔧 {translator.get_text(event.sender_id, 'no_modules_loaded')}</b>", parse_mode='HTML')
            return

        self.log_command_usage("help")

        core_modules = ['loader', 'help', 'start', 'ping', 'terminal', 'serverinfo', 'lang']
        user_modules = [name for name in modules_help.keys() if name not in core_modules]

        total_commands = sum(len(cmds) for cmds in modules_help.values())
        total_modules = len(modules_help)

        modules_list = ""
        for mod_name in sorted(core_modules):
            if mod_name in modules_help:
                commands = modules_help[mod_name]
                cmd_list = [f"<code>{cmd}</code>" for cmd in sorted(commands.keys())]
                modules_list += f"- <b>{mod_name}</b> (<code>{len(commands)}</code>)\n"
                modules_list += f"  {', '.join(cmd_list[:3])}"
                if len(commands) > 3:
                    modules_list += f" +{len(commands) - 3}"
                modules_list += "\n"

        if user_modules:
            modules_list += f"\n<b>🔶 {translator.get_text(event.sender_id, 'user_modules')}</b> (<code>{len(user_modules)}</code>)\n"
            for mod_name in sorted(user_modules):
                commands = modules_help[mod_name]
                cmd_list = [f"<code>{cmd}</code>" for cmd in sorted(commands.keys())[:2]]
                modules_list += f"- <b>{mod_name}</b> (<code>{len(commands)}</code>)\n"
                modules_list += f"  {', '.join(cmd_list)}"
                if len(commands) > 2:
                    modules_list += f" +{len(commands) - 2}"
                modules_list += "\n"

        current_lang = translator.get_current_language(event.sender_id)
        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎📚 {translator.get_text(event.sender_id, 'help_title')}</b>

<b>📊 {translator.get_text(event.sender_id, 'overview')}</b>
<blockquote expandable>- <b>{translator.get_text(event.sender_id, 'modules')}:</b> <code>{total_modules}</code>
- <b>{translator.get_text(event.sender_id, 'commands')}:</b> <code>{total_commands}</code>
- <b>{translator.get_text(event.sender_id, 'prefix')}:</b> <code>{self.prefix}</code></blockquote>

<b>🔷 {translator.get_text(event.sender_id, 'main_modules')}</b> (<code>{len([m for m in core_modules if m in modules_help])}</code>)
<blockquote expandable>{modules_list}</blockquote>

<b>🎯 {translator.get_text(event.sender_id, 'quick_help')}</b>
<blockquote expandable><code>{self.prefix}help all</code> - {translator.get_text(event.sender_id, 'all')} {translator.get_text(event.sender_id, 'commands')}
<code>{self.prefix}help &lt;module&gt;</code> - {translator.get_text(event.sender_id, 'module_help')}  
<code>{self.prefix}help &lt;command&gt;</code> - {translator.get_text(event.sender_id, 'command_help')}
<code>{self.prefix}find &lt;text&gt;</code> - {translator.get_text(event.sender_id, 'search_commands')}</blockquote>

<b>🌐 {translator.get_text(event.sender_id, 'language')}</b>
<blockquote expandable>{translator.get_text(event.sender_id, 'current_language_display')}: <code>{current_lang.upper()}</code>
<code>{self.prefix}lang ru</code> - Русский
<code>{self.prefix}lang en</code> - English</blockquote>

<blockquote expandable>💡 {translator.get_text(event.sender_id, 'use_command_for_help')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')

    async def show_all_commands(self, event):
        from utils.loader import modules_help
        
        loading_msg = await edit_or_reply(event, "📋")
        await fast_animation(loading_msg, "📋", f"📋 {translator.get_text(event.sender_id, 'loading')}")
        
        if not modules_help:
            await loading_msg.edit(f"<b>❌ {translator.get_text(event.sender_id, 'error')}: {translator.get_text(event.sender_id, 'no_modules_found')}</b>", parse_mode='HTML')
            return

        self.log_command_usage("help_all")

        command_count = 0
        commands_text = ""
        for module_name, commands in sorted(modules_help.items()):
            commands_text += f"<b>📦 {module_name.upper()}</b>\n"
            for cmd, desc in sorted(commands.items()):
                command_count += 1
                commands_text += f"- <code>{self.prefix}{cmd}</code> - {desc}\n"
            commands_text += "\n"

        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎📋 {translator.get_text(event.sender_id, 'all_commands')}</b>

<blockquote expandable>{commands_text}</blockquote>

<b>📊 {translator.get_text(event.sender_id, 'total')}:</b> <code>{command_count}</code> {translator.get_text(event.sender_id, 'commands')}

<blockquote expandable>💡 {translator.get_text(event.sender_id, 'complete_command_reference')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')

    async def show_module_help(self, event, module_name):
        from utils.loader import modules_help
        
        loading_msg = await edit_or_reply(event, "📦")
        await fast_animation(loading_msg, "📦", f"📦 {translator.get_text(event.sender_id, 'loading')}")
        
        exact_module = None
        if module_name in modules_help:
            exact_module = module_name
        else:
            matches = difflib.get_close_matches(module_name, modules_help.keys(), n=1)
            if matches:
                exact_module = matches[0]

        if not exact_module:
            available = ", ".join([f"<code>{m}</code>" for m in sorted(modules_help.keys())[:6]])
            text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎❌ {translator.get_text(event.sender_id, 'error')}</b>

<b>🚫 {translator.get_text(event.sender_id, 'module')} <code>{module_name}</code> {translator.get_text(event.sender_id, 'not_found')}</b>

<b>✅ {translator.get_text(event.sender_id, 'available_modules')}:</b>
<blockquote expandable>{available}</blockquote>

<blockquote expandable>💡 {translator.get_text(event.sender_id, 'use')} <code>{self.prefix}help</code> {translator.get_text(event.sender_id, 'to_see')} {translator.get_text(event.sender_id, 'all')} {translator.get_text(event.sender_id, 'modules')}</blockquote>"""
            
            await loading_msg.edit(text, parse_mode='HTML')
            return

        self.log_command_usage(f"help_{exact_module}")

        commands = modules_help[exact_module]
        
        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎📦 {exact_module.upper()}</b>

<b>📝 {translator.get_text(event.sender_id, 'module_details')}</b>
<blockquote expandable><b>🔧 {translator.get_text(event.sender_id, 'commands')}:</b> <code>{len(commands)}</code></blockquote>

"""

        for cmd, desc in sorted(commands.items()):
            text += f"""- <b>{self.prefix}{cmd}</b>
<blockquote expandable>{desc}</blockquote>
"""

        text += f"""<b>💡 {translator.get_text(event.sender_id, 'usage')}</b>
<blockquote expandable><code>{self.prefix}{list(commands.keys())[0]}</code> - {translator.get_text(event.sender_id, 'try')} {translator.get_text(event.sender_id, 'command')}</blockquote>

<b>🔙 {translator.get_text(event.sender_id, 'navigation')}</b>
<blockquote expandable><code>{self.prefix}help</code> - {translator.get_text(event.sender_id, 'main_menu')}</blockquote>

<blockquote expandable>📚 {translator.get_text(event.sender_id, 'module')} {translator.get_text(event.sender_id, 'documentation')} {translator.get_text(event.sender_id, 'and')} {translator.get_text(event.sender_id, 'usage')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')

    async def show_command_help(self, event, command_name):
        from utils.loader import modules_help
        
        loading_msg = await edit_or_reply(event, "🔍")
        await fast_animation(loading_msg, "🔍", f"🔍 {translator.get_text(event.sender_id, 'loading')}")
        
        found = []
        for module_name, commands in modules_help.items():
            if command_name in commands:
                found.append({
                    'module': module_name,
                    'description': commands[command_name]
                })

        if not found:
            all_commands = []
            for mod_name, commands in modules_help.items():
                for cmd in commands.keys():
                    all_commands.append(cmd)
            
            matches = difflib.get_close_matches(command_name, all_commands, n=3)
            if matches:
                suggestion_text = f"\n\n<b>💡 {translator.get_text(event.sender_id, 'did_you_mean')}?</b>\n" + "\n".join([f"- <code>{self.prefix}{cmd}</code>" for cmd in matches])
            else:
                suggestion_text = f"\n\n<b>💡 {translator.get_text(event.sender_id, 'use')} <code>{self.prefix}help</code> {translator.get_text(event.sender_id, 'for_commands')}</b>"
                
            await loading_msg.edit(f"<b>❌ {translator.get_text(event.sender_id, 'command')} <code>{command_name}</code> {translator.get_text(event.sender_id, 'not_found')}</b>{suggestion_text}", parse_mode='HTML')
            return

        self.log_command_usage(f"cmd_{command_name}")

        if len(found) == 1:
            item = found[0]
            text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎🔧 {self.prefix}{command_name.upper()}</b>

<b>📦 {translator.get_text(event.sender_id, 'module')}:</b> <code>{item['module']}</code>
<b>📖 {translator.get_text(event.sender_id, 'description')}:</b> {item['description']}

<b>🚀 {translator.get_text(event.sender_id, 'usage')}</b>
<blockquote expandable><code>{self.prefix}{command_name}</code></blockquote>

<b>🔗 {translator.get_text(event.sender_id, 'related')}</b>
<blockquote expandable><code>{self.prefix}help {item['module']}</code> - {translator.get_text(event.sender_id, 'module')} {translator.get_text(event.sender_id, 'help')}</blockquote>

<blockquote expandable>💡 {translator.get_text(event.sender_id, 'command')} {translator.get_text(event.sender_id, 'usage')} {translator.get_text(event.sender_id, 'and')} {translator.get_text(event.sender_id, 'details')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""
        else:
            text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎🔧 {self.prefix}{command_name.upper()}</b>

<b>📋 {translator.get_text(event.sender_id, 'available')} {translator.get_text(event.sender_id, 'in')} <code>{len(found)}</code> {translator.get_text(event.sender_id, 'modules')}:</b>

"""
            for item in found:
                text += f"""- <b>{item['module']}</b>
<blockquote expandable>{item['description']}</blockquote>
"""

            text += f"""<blockquote expandable>🔄 {translator.get_text(event.sender_id, 'command')} {translator.get_text(event.sender_id, 'available')} {translator.get_text(event.sender_id, 'in')} {translator.get_text(event.sender_id, 'multiple')} {translator.get_text(event.sender_id, 'modules')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')

    async def show_modules_stats(self, event):
        from utils.loader import modules_help
        
        loading_msg = await edit_or_reply(event, "📊")
        await fast_animation(loading_msg, "📊", f"📊 {translator.get_text(event.sender_id, 'loading')}")
        
        if not modules_help:
            await loading_msg.edit(f"<b>📊 {translator.get_text(event.sender_id, 'no')} {translator.get_text(event.sender_id, 'modules')}</b>", parse_mode='HTML')
            return

        self.log_command_usage("modules")

        core_modules = ['loader', 'help', 'start', 'ping', 'terminal', 'serverinfo', 'lang']
        user_modules = [name for name in modules_help.keys() if name not in core_modules]
        
        total_commands = sum(len(cmds) for cmds in modules_help.values())

        top_modules_text = ""
        sorted_modules = sorted(modules_help.items(), key=lambda x: len(x[1]), reverse=True)
        
        for i, (module_name, commands) in enumerate(sorted_modules[:5], 1):
            icon = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔷" if module_name in core_modules else "🔶"
            top_modules_text += f"{icon} <b>{module_name}</b> - <code>{len(commands)}</code> {translator.get_text(event.sender_id, 'commands')}\n"

        popular_commands_text = ""
        if self.command_usage:
            popular_commands = sorted(self.command_usage.items(), key=lambda x: x[1], reverse=True)[:3]
            for cmd, count in popular_commands:
                if not cmd.startswith('help_') and not cmd.startswith('cmd_'):
                    popular_commands_text += f"- <code>{self.prefix}{cmd}</code> - <code>{count}</code> {translator.get_text(event.sender_id, 'uses')}\n"

        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎📊 {translator.get_text(event.sender_id, 'statistics').upper()}</b>

<b>📈 {translator.get_text(event.sender_id, 'overview')}</b>
<blockquote expandable>- <b>{translator.get_text(event.sender_id, 'core')} {translator.get_text(event.sender_id, 'modules')}:</b> <code>{len([m for m in core_modules if m in modules_help])}</code>
- <b>{translator.get_text(event.sender_id, 'user_custom')} {translator.get_text(event.sender_id, 'modules')}:</b> <code>{len(user_modules)}</code>
- <b>{translator.get_text(event.sender_id, 'total')} {translator.get_text(event.sender_id, 'modules')}:</b> <code>{len(modules_help)}</code>
- <b>{translator.get_text(event.sender_id, 'total')} {translator.get_text(event.sender_id, 'commands')}:</b> <code>{total_commands}</code></blockquote>

<b>🏆 {translator.get_text(event.sender_id, 'top')} {translator.get_text(event.sender_id, 'modules').upper()}</b>
<blockquote expandable>{top_modules_text}</blockquote>"""

        if popular_commands_text:
            text += f"""\n<b>⭐ {translator.get_text(event.sender_id, 'popular_commands').upper()}</b>
<blockquote expandable>{popular_commands_text}</blockquote>"""

        text += f"""\n<b>🔄 {translator.get_text(event.sender_id, 'last_update')}:</b> <code>{time.strftime('%H:%M:%S')}</code>

<blockquote expandable>📈 {translator.get_text(event.sender_id, 'system_statistics')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')

    async def find_commands(self, event, search_term):
        from utils.loader import modules_help
        
        loading_msg = await edit_or_reply(event, "🔍")
        await fast_animation(loading_msg, "🔍", f"🔍 {translator.get_text(event.sender_id, 'loading')}")
        
        found = []
        for module_name, commands in modules_help.items():
            for cmd_name, description in commands.items():
                if (search_term.lower() in cmd_name.lower() or 
                    search_term.lower() in description.lower()):
                    found.append({
                        'module': module_name,
                        'command': cmd_name,
                        'description': description
                    })

        if not found:
            text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎🔍 {translator.get_text(event.sender_id, 'search_commands')}</b>

<b>❌ {translator.get_text(event.sender_id, 'no_search_results')} <code>{search_term}</code></b>

<blockquote expandable>💡 {translator.get_text(event.sender_id, 'try_other_terms')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""
            
            await loading_msg.edit(text, parse_mode='HTML')
            return

        self.log_command_usage(f"find_{search_term}")

        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎🔍 {translator.get_text(event.sender_id, 'search_commands').upper()}</b>

<b>📊 {translator.get_text(event.sender_id, 'found')} <code>{len(found)}</code> {translator.get_text(event.sender_id, 'results')}</b>

"""

        modules_dict = {}
        for item in found:
            if item['module'] not in modules_dict:
                modules_dict[item['module']] = []
            modules_dict[item['module']].append(item)

        for module_name, items in sorted(modules_dict.items()):
            text += f"<b>📦 {module_name.upper()}</b>\n"
            for item in items[:4]:
                text += f"- <code>{self.prefix}{item['command']}</code> - {item['description']}\n"
            if len(items) > 4:
                text += f"  ... {translator.get_text(event.sender_id, 'and')} <code>{len(items) - 4}</code> {translator.get_text(event.sender_id, 'more_results')}\n"
            text += "\n"

        text += f"""<blockquote expandable>🔎 {translator.get_text(event.sender_id, 'search_results')} {translator.get_text(event.sender_id, 'for_your_query')} <code>{search_term}</code></blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')

    async def show_popular_commands(self, event):
        loading_msg = await edit_or_reply(event, "⭐")
        await fast_animation(loading_msg, "⭐", f"⭐ {translator.get_text(event.sender_id, 'loading')}")
        
        if not self.command_usage:
            text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎⭐ {translator.get_text(event.sender_id, 'popular_commands')}</b>

<b>📊 {translator.get_text(event.sender_id, 'no_usage_data_yet')}</b>

<blockquote expandable>💡 {translator.get_text(event.sender_id, 'commands_will_appear_here')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

            await loading_msg.edit(text, parse_mode='HTML')
            return

        self.log_command_usage("popular")

        real_commands = {cmd: count for cmd, count in self.command_usage.items() 
                        if not cmd.startswith('help_') and not cmd.startswith('cmd_') and not cmd.startswith('find_')}
        
        if not real_commands:
            await loading_msg.edit(f"<b>⭐ {translator.get_text(event.sender_id, 'no_command_usage_data')}</b>", parse_mode='HTML')
            return

        popular = sorted(real_commands.items(), key=lambda x: x[1], reverse=True)[:8]

        popular_text = ""
        for i, (cmd, count) in enumerate(popular, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            popular_text += f"{medal} <code>{self.prefix}{cmd}</code> - <b>{count}</b> {translator.get_text(event.sender_id, 'uses')}\n"

        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎⭐ {translator.get_text(event.sender_id, 'popular_commands').upper()}</b>

<blockquote expandable>{popular_text}</blockquote>

<blockquote expandable>📊 {translator.get_text(event.sender_id, 'most_frequently_used_commands')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')


help_system = HelpSystem()


async def help_handler(event):
    args = event.text.split()
    
    if len(args) == 1:
        await help_system.show_main_help(event)
    elif len(args) == 2:
        arg = args[1].lower()
        if arg == "all":
            await help_system.show_all_commands(event)
        elif arg in ["modules", "stats", "statistics"]:
            await help_system.show_modules_stats(event)
        elif arg == "popular":
            await help_system.show_popular_commands(event)
        else:
            from utils.loader import modules_help
            is_command = any(arg in commands for commands in modules_help.values())
            if is_command:
                await help_system.show_command_help(event, arg)
            else:
                await help_system.show_module_help(event, arg)
    else:
        await help_system.find_commands(event, " ".join(args[1:]))


async def modules_handler(event):
    await help_system.show_modules_stats(event)


async def find_handler(event):
    args = event.text.split(maxsplit=1)
    if len(args) == 1:
        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎❌ {translator.get_text(event.sender_id, 'error')}</b>

<b>🚫 {translator.get_text(event.sender_id, 'specify_search_term')}</b>

<b>💡 {translator.get_text(event.sender_id, 'usage')}:</b>
<blockquote expandable><code>.find &lt;text&gt;</code></blockquote>

<blockquote expandable>🔍 {translator.get_text(event.sender_id, 'search_commands_by_name_or_description')}</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""
        
        await edit_or_reply(event, text, parse_mode='HTML')
        return
    await help_system.find_commands(event, args[1])


async def popular_handler(event):
    await help_system.show_popular_commands(event)


async def allcmds_handler(event):
    await help_system.show_all_commands(event)


modules_help = {
    "help": {
        "help": "Показать главное меню помощи со всеми функциями",
        "help all": "Показать все команды в детальном списке", 
        "help [module]": "Показать детальную документацию модуля",
        "help [command]": "Показать справку по конкретной команде",
        "modules": "Показать детальную системную статистику",
        "find": "Поиск команд по имени/описанию",
        "popular": "Показать самые используемые команды",
        "allcmds": "Альтернатива для 'help all'"
    }
}
