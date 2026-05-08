import os

with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

# I see `show_admin_console` expects just `peer_id: int`. So `MockMsg` is actually wrong there!
# We should revert it back to `await show_admin_console(peer_id)`.
content = content.replace('await show_admin_console(MockMsg(vk_id, peer_id))', 'await show_admin_console(peer_id)')

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
