# The admin_console issue
import os

with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('await show_admin_console(peer_id)', 'await show_admin_console(MockMsg(vk_id, peer_id))')

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
