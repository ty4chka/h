import platform
import os
import sys
from utils.misc import edit_or_reply, fast_animation
from modules.lang import translator

async def serverinfo_handler(event):
    try:
        loading_msg = await edit_or_reply(event, "🖥")
        await fast_animation(loading_msg, "🖥", f"🖥 {translator.get_text(event.sender_id, 'loading')}")
        
        system_info = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎🖥 {translator.get_text(event.sender_id, 'server_title')}</b>

<b>💻 {translator.get_text(event.sender_id, 'os')}:</b> <code>{platform.system()} {platform.release()}</code>
<b>🏗 {translator.get_text(event.sender_id, 'architecture')}:</b> <code>{platform.architecture()[0]}</code>
<b>🐍 {translator.get_text(event.sender_id, 'python_version')}:</b> <code>{platform.python_version()}</code>
<b>📁 {translator.get_text(event.sender_id, 'directory')}:</b> <code>{os.getcwd()}</code>"""

        try:
            import psutil
            
            try:
                memory = psutil.virtual_memory()
                memory_info = f"""
<b>💾 {translator.get_text(event.sender_id, 'memory')}:</b>
<blockquote expandable>- <b>{translator.get_text(event.sender_id, 'total_memory')}:</b> <code>{round(memory.total / (1024**3), 1)} GB</code>
- <b>{translator.get_text(event.sender_id, 'available_memory')}:</b> <code>{round(memory.available / (1024**3), 1)} GB</code>
- <b>{translator.get_text(event.sender_id, 'usage')}:</b> <code>{memory.percent}%</code></blockquote>"""
            except:
                memory_info = f"\n<b>💾 {translator.get_text(event.sender_id, 'memory')}:</b> <i>{translator.get_text(event.sender_id, 'not_available')}</i>"

            try:
                disk = psutil.disk_usage('/')
                disk_info = f"""
<b>💽 {translator.get_text(event.sender_id, 'disk')}:</b>
<blockquote expandable>- <b>{translator.get_text(event.sender_id, 'total_disk')}:</b> <code>{round(disk.total / (1024**3), 1)} GB</code>
- <b>{translator.get_text(event.sender_id, 'used_disk')}:</b> <code>{round(disk.used / (1024**3), 1)} GB</code>  
- <b>{translator.get_text(event.sender_id, 'free_disk')}:</b> <code>{round(disk.free / (1024**3), 1)} GB</code>
- <b>{translator.get_text(event.sender_id, 'usage')}:</b> <code>{disk.percent}%</code></blockquote>"""
            except:
                disk_info = f"\n<b>💽 {translator.get_text(event.sender_id, 'disk')}:</b> <i>{translator.get_text(event.sender_id, 'not_available')}</i>"

            try:
                cpu_info = f"""
<b>⚡ {translator.get_text(event.sender_id, 'cpu')}:</b>
<blockquote expandable>- <b>{translator.get_text(event.sender_id, 'cores')}:</b> <code>{psutil.cpu_count(logical=True)}</code>
- <b>{translator.get_text(event.sender_id, 'usage')}:</b> <code>{psutil.cpu_percent(interval=1)}%</code></blockquote>"""
            except:
                cpu_info = f"\n<b>⚡ {translator.get_text(event.sender_id, 'cpu')}:</b> <i>{translator.get_text(event.sender_id, 'not_available')}</i>"

            system_info += cpu_info + memory_info + disk_info
            
        except ImportError:
            system_info += f"""\n\n<b>💡 {translator.get_text(event.sender_id, 'install')} psutil:</b>
<blockquote expandable><code>pip install psutil</code></blockquote>"""

        system_info += f"""\n\n<blockquote expandable>🖥 {translator.get_text(event.sender_id, 'server_hardware_info')}</blockquote>"""
        
        await loading_msg.edit(system_info, parse_mode='HTML')
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

async def sysinfo_handler(event):
    loading_msg = await edit_or_reply(event, "📱")
    await fast_animation(loading_msg, "📱", f"📱 {translator.get_text(event.sender_id, 'loading')}")
    
    info = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎📱 {translator.get_text(event.sender_id, 'system')} {translator.get_text(event.sender_id, 'info')}</b>

<b>🏗 {translator.get_text(event.sender_id, 'platform')}:</b> <code>{platform.platform()}</code>
<b>🐍 {translator.get_text(event.sender_id, 'python_version')}:</b> <code>{platform.python_version()}</code>
<b>📦 {translator.get_text(event.sender_id, 'implementation')}:</b> <code>{platform.python_implementation()}</code>

<b>📁 {translator.get_text(event.sender_id, 'current')} {translator.get_text(event.sender_id, 'directory')}:</b> <code>{os.getcwd()}</code>
<b>👤 {translator.get_text(event.sender_id, 'user')}:</b> <code>{os.getenv('USER', translator.get_text(event.sender_id, 'unknown'))}</code>
<b>📟 {translator.get_text(event.sender_id, 'hostname')}:</b> <code>{platform.node()}</code>

<blockquote expandable>💡 {translator.get_text(event.sender_id, 'basic_system_info')}</blockquote>

<b>🔧 {translator.get_text(event.sender_id, 'for_more_info')}:</b> <code>.serverinfo</code>"""
    
    await loading_msg.edit(info, parse_mode='HTML')

modules_help = {
    "serverinfo": {
        "serverinfo": "Показать детальную информацию о сервере",
        "sysinfo": "Показать базовую системную информацию"
    }
}
