with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

# Wait, the replacement failed because I forgot that the text was copied exactly from the old version or there's another block.
# Let's see the current file
import re
new_ref_logic = """        elif cmd == "get_referral":
            # Direct link to group 219181948 sending text ПЕЧАТЬ-{vk_id}
            ref_link = f"https://vk.com/im?sel=-219181948&text=ПЕЧАТЬ-{vk_id}"
            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"Твоя персональная ссылка для друзей:\\n{ref_link}\\n\\nОтправь этот код/ссылку новому адепту. Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд.",
                random_id=0
            )"""

content = re.sub(r'elif cmd == "get_referral":.*?random_id=0\n            \)', new_ref_logic, content, flags=re.DOTALL)

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
