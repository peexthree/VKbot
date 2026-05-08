with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

bad_str = 'message=f"Твоя персональная ссылка для друзей:\n{ref_link}\n\nОтправь этот код/ссылку новому адепту. Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд.",'

good_str = 'message=f"Твоя персональная ссылка для друзей:\\n{ref_link}\\n\\nОтправь этот код/ссылку новому адепту. Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд.",'

content = content.replace(bad_str, good_str)

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
