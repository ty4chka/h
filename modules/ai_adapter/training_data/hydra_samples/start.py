import os
from utils.misc import edit_or_reply, fast_animation
from modules.lang import translator

PHOTO_URL = "https://i.ibb.co/QjpBGFjV/hydra-bot.jpg"

async def start_handler(event):
    try:
        loading_msg = await edit_or_reply(event, "🚀")
        await fast_animation(loading_msg, "🚀", f"🚀 {translator.get_text(event.sender_id, 'loading')}")
        
        if event.sender:
            username = event.sender.username or translator.get_text(event.sender_id, 'not_set')
            first_name = event.sender.first_name or translator.get_text(event.sender_id, 'unknown')
            user_id = event.sender.id
        else:
            username = translator.get_text(event.sender_id, 'unknown')
            first_name = translator.get_text(event.sender_id, 'unknown')
            user_id = translator.get_text(event.sender_id, 'unknown')
        
        caption = f"""<b>︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎ ︎  ︎︎ ︎ ⁠⁠⁠︎🚀 Hydra user bot</b>

<blockquote expandable><b>⚡️ {translator.get_text(event.sender_id, 'version')}:</b> <code>1.0.2</code>
<b>👤 {translator.get_text(event.sender_id, 'user')}:</b> {first_name}
<b>📱 {translator.get_text(event.sender_id, 'username')}:</b> @{username}
<b>🆔 ID:</b> <code>{user_id}</code></blockquote>

<b>💻 {translator.get_text(event.sender_id, 'developers')}:</b>
<blockquote expandable>@global_050
@Aubeig</blockquote>

<blockquote expandable>⚡ {translator.get_text(event.sender_id, 'powered_by')} Hydra UserBot</blockquote>"""

        await event.client.send_file(event.chat_id, PHOTO_URL, caption=caption, parse_mode='HTML')
        await event.delete()
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

modules_help = {
    "start": {
        "start": "Start the bot and show information"
    }
}
