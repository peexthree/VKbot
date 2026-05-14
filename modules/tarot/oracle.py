import json
from loguru import logger
from vkbottle import Keyboard
from database import get_user, update_user
from ai_service import generate_text
from modules.bot_init import bot
from modules.utils import (
    start_dynamic_typing, stop_dynamic_typing, upload_local_photo, get_sections_keyboard
)
from cache import acquire_lock, release_lock, get_tarot_names

async def process_oracle_final(vk_id: int, text: str, card_ids: list, skip_lock: bool = False, **kwargs):
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        conv_msg_id, message_id = kwargs.get("conversation_message_id"), kwargs.get("message_id")
        if conv_msg_id:
            try: await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message="Раскладываю карты...", keyboard=Keyboard(inline=True).get_json())
            except: pass
        elif message_id:
            try: await bot.api.messages.edit(peer_id=vk_id, message_id=message_id, message="Раскладываю карты...", keyboard=Keyboard(inline=True).get_json())
            except: pass

        user = await get_user(vk_id)
        if not user: return
        await start_dynamic_typing(bot.api, vk_id)

        attachments = []
        for cid in card_ids:
            photo = await upload_local_photo(bot.api, f"{cid}.jpeg", peer_id=vk_id)
            if photo: attachments.append(photo)

        tarot_names = await get_tarot_names()
        c_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in card_ids]
        p = user.get("purchased_sections", {})
        gender = "ЖЕНЩИНА" if p.get("sex_val", 0) == 1 else "МУЖЧИНА"
        core, tags = user.get("core_profile", ""), user.get("tags", [])
        prompt = f"КОНТЕКСТ: {gender}. " + (f"Прошлый анализ: {core}. " if core else "") + (f"Фокус: [{', '.join(tags)}]. " if tags else "")
        prompt += f"Пользователь задает вопрос: {text}. Выпали карты: 1. {c_names[0]}, 2. {c_names[1]}, 3. {c_names[2]}. Сначала выведи Карта [N]: [Название] - [Краткий смысл], затем общий синтез."

        res = await generate_text(prompt, skin=user.get("active_skin", "olesya"))
        if not res:
            if conv_msg_id: await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message="Оракул молчит. Попробуй позже.")
            else: await bot.api.messages.send(peer_id=vk_id, message="Оракул молчит. Попробуй позже.", random_id=0)
            return

        unlocked = user.get("unlocked_cards", {}) or {}
        for cid_int in card_ids:
            cid = str(cid_int)
            if cid not in unlocked:
                sig = await generate_text(f"Краткая суть карты {tarot_names.get(cid)}. Мистично, для личного Гримуара.", skin=user.get("active_skin", "olesya"))
                unlocked[cid] = sig if sig else "Первое касание"

        await update_user(vk_id, {"unlocked_cards": unlocked, "total_cards_received": user.get("total_cards_received", 0) + 3})
        kb_json = await get_sections_keyboard(vk_id, user)
        try:
            kb_data = json.loads(kb_json)
            if "buttons" in kb_data: kb_data["buttons"].insert(0, [{"action": {"type": "callback", "payload": json.dumps({"cmd": "gen_pdf", "section": "oracle", "card": str(card_ids[0]) if card_ids else ""}), "label": "СГЕНЕРИРОВАТЬ PDF"}, "color": "secondary"}])
            kb_json = json.dumps(kb_data, ensure_ascii=False)
        except: pass

        att = ",".join(attachments) if attachments else None
        if conv_msg_id:
            try: await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message=res, keyboard=kb_json, attachment=att)
            except: await bot.api.messages.send(peer_id=vk_id, message=res, keyboard=kb_json, random_id=0, attachment=att)
        else: await bot.api.messages.send(peer_id=vk_id, message=res, keyboard=kb_json, random_id=0, attachment=att)
    except Exception as e:
        logger.error(f"Ошибка в Оракуле: {e}")
        err = "Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже."
        if conv_msg_id: await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message=err)
        else: await bot.api.messages.send(peer_id=vk_id, message=err, random_id=0)
    finally:
        await stop_dynamic_typing(vk_id)
        if not skip_lock: await release_lock(vk_id)
