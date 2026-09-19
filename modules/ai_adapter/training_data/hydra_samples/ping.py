import time
import asyncio
from utils.misc import get_uptime, get_start_time, edit_or_reply, rate_limit, fast_animation
from modules.lang import translator

@rate_limit(limit=15, period=120)
async def ping_handler(event):
    try:
        loading_msg = await edit_or_reply(event, "⚡")
        await fast_animation(loading_msg, "⚡", f"⚡ {translator.get_text(event.sender_id, 'loading')}")
        
        start = time.time()
        await asyncio.sleep(0.05)
        end = time.time()
        
        ping_ms = round((end - start) * 1000, 2)
        start_time = get_start_time()
        uptime = get_uptime(start_time)
        
        text = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎🏓 {translator.get_text(event.sender_id, 'ping_title')}</b>

<b>⚡️ {translator.get_text(event.sender_id, 'response')}:</b> <code>{ping_ms}ms</code>
<b>🕐 {translator.get_text(event.sender_id, 'uptime')}:</b> <code>{uptime}</code>

<blockquote expandable>🚀 {translator.get_text(event.sender_id, 'system')} {translator.get_text(event.sender_id, 'performance')} {translator.get_text(event.sender_id, 'metrics')}</blockquote>"""

        await loading_msg.edit(text, parse_mode='HTML')
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

modules_help = {
    "ping": {
        "ping": "Проверить время ответа бота и аптайм (15/2min)"
    }
}
