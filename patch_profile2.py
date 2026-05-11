import re

with open('modules/profile.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add the import back but inside functions where it's needed or uniquely at the top
content = re.sub(r'from modules\.utils import SKIN_ASSETS, get_sections_keyboard, upload_local_photo, get_fsm_step',
                 'from modules.utils import SKIN_ASSETS, get_sections_keyboard, upload_local_photo, get_fsm_step\nfrom modules.bot_init import bot', content)

with open('modules/profile.py', 'w', encoding='utf-8') as f:
    f.write(content)
