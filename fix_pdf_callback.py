with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

old_kb = """                kb_dict["buttons"].append([{
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "gen_pdf", "section": target_section, "card": card_id}),
                        "label": "СГЕНЕРИРОВАТЬ PDF"
                    },
                    "color": "secondary"
                }])"""

new_kb = """                kb_dict["buttons"].append([{
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "gen_pdf", "section": target_section, "card": card_id}),
                        "label": "СГЕНЕРИРОВАТЬ PDF"
                    },
                    "color": "secondary"
                }])
                kb_dict["buttons"].append([{
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "service_page", "idx": 0}),
                        "label": "Вернуться в услуги"
                    },
                    "color": "primary"
                }])"""

content = content.replace(old_kb, new_kb)

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
