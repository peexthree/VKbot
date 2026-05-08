import re

with open("modules/profile.py", "r", encoding="utf-8") as f:
    content = f.read()

# I will replace these with Text because they correspond to Text handlers.
# Actually, the user wants "все кнопки работали по callback вместо текста." (except for the bottom keyboard which can't be callback usually, but bottom keyboard here is dynamic_keyboard?).
# wait, if I change Text to Callback, I need to add handlers for the callbacks in modules/payments.py since payments.py is the one handling all GroupEventType.MESSAGE_EVENT.
