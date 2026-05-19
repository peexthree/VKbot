import re

with open('modules/payments/callbacks.py', 'r') as f:
    content = f.read()

# Fix the recursion issue by restoring the correct bot.api.messages.edit inside safe_edit
old_str = """    try:
        await safe_edit(peer_id=peer_id,
            message=message,
            conversation_message_id=conversation_message_id,
            keyboard=keyboard,
            attachment=attachment,
            **kwargs
        )"""

new_str = """    try:
        await bot.api.messages.edit(
            peer_id=peer_id,
            message=message,
            conversation_message_id=conversation_message_id,
            keyboard=keyboard,
            attachment=attachment,
            **kwargs
        )"""

content = content.replace(old_str, new_str)

with open('modules/payments/callbacks.py', 'w') as f:
    f.write(content)
