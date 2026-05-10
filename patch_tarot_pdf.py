import json
with open("modules/tarot.py", "r") as f:
    content = f.read()

old_kb_card = """        final_kb = await get_sections_keyboard(vk_id, user)

        if conv_msg_id:"""
new_kb_card = """        final_kb = await get_sections_keyboard(vk_id, user)
        try:
            import json
            kb_data = json.loads(final_kb)
            if "buttons" in kb_data:
                kb_data["buttons"].insert(0, [{
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "gen_pdf", "section": "card_of_day", "card": card_id}),
                        "label": "СГЕНЕРИРОВАТЬ PDF"
                    },
                    "color": "secondary"
                }])
            final_kb = json.dumps(kb_data, ensure_ascii=False)
        except Exception:
            pass

        if conv_msg_id:"""
content = content.replace(old_kb_card, new_kb_card)

old_kb_oracle = """        kb_json = await get_sections_keyboard(vk_id, user)

        if conv_msg_id:"""
new_kb_oracle = """        kb_json = await get_sections_keyboard(vk_id, user)
        try:
            import json
            kb_data = json.loads(kb_json)
            if "buttons" in kb_data:
                kb_data["buttons"].insert(0, [{
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "gen_pdf", "section": "oracle", "card": str(card_ids[0]) if card_ids else ""}),
                        "label": "СГЕНЕРИРОВАТЬ PDF"
                    },
                    "color": "secondary"
                }])
            kb_json = json.dumps(kb_data, ensure_ascii=False)
        except Exception:
            pass

        if conv_msg_id:"""
content = content.replace(old_kb_oracle, new_kb_oracle)
with open("modules/tarot.py", "w") as f:
    f.write(content)
