import re

with open('modules/payments/callbacks.py', 'r') as f:
    content = f.read()

# Create safe_edit wrapper and add it at the top level
safe_edit_func = """
async def safe_edit(peer_id, message, conversation_message_id=None, keyboard=None, attachment=None, **kwargs):
    \"\"\"Обертка для безопасного редактирования с защитой от Flood Control.\"\"\"
    await asyncio.sleep(0.4) # Reasonable delay
    try:
        await bot.api.messages.edit(
            peer_id=peer_id,
            message=message,
            conversation_message_id=conversation_message_id,
            keyboard=keyboard,
            attachment=attachment,
            **kwargs
        )
    except Exception as e:
        if "9" in str(e) or "Flood control" in str(e):
            logger.warning(f"Flood control in safe_edit, waiting 1.5s...")
            await asyncio.sleep(1.5)
        # Fallback to send
        logger.debug(f"safe_edit failed ({e}), falling back to send.")
        try:
            # Try to delete the old message
            from modules.utils.ui import delete_bot_message
            if conversation_message_id:
                await delete_bot_message(bot.api, peer_id, cmid=conversation_message_id)
        except Exception:
            pass
        await bot.api.messages.send(
            peer_id=peer_id,
            message=message,
            keyboard=keyboard,
            attachment=attachment,
            random_id=0,
            **kwargs
        )
"""

if "def safe_edit(" not in content:
    content = content.replace("from vkbottle.bot import BotLabeler", "from vkbottle.bot import BotLabeler\n" + safe_edit_func)

# Replace all direct await bot.api.messages.edit( with await safe_edit( in message_event_handler
# We will do this carefully.
import re
content = re.sub(
    r'await bot\.api\.messages\.edit\(\s*peer_id=peer_id,',
    r'await safe_edit(peer_id=peer_id,',
    content
)

with open('modules/payments/callbacks.py', 'w') as f:
    f.write(content)
