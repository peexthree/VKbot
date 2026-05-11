import re

with open('modules/profile.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the line 'from modules.bot_init import bot'
content = re.sub(r'from modules\.bot_init import bot\n', '', content)

with open('modules/profile.py', 'w', encoding='utf-8') as f:
    f.write(content)
