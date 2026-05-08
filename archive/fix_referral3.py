with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("""                elif cmd == "get_referral":
            # Direct link""", """        elif cmd == "get_referral":
            # Direct link""")

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
