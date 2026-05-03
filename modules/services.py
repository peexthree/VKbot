import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, generate_pdf, get_fsm_step,  upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, active_tasks, cover_cache

labeler = BotLabeler()

@labeler.message(text=["✦ Услуги", "Услуги", "✦ УСЛУГИ 🛒"])
async def show_services(message: Message):
    import json
    vk_id = message.from_id
    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

    services = [
        {"key": "🃏 КАРТА ДНЯ", "price_text": "Бесплатно", "desc": "Ежедневный прогноз для корректировки реальности."},
        {"key": "🔮 ВОПРОС СУДЬБЕ", "price_text": "50 РУБ или 5 бонусов", "desc": "Снятие блокировки и мгновенный ответ на твой вопрос."},
        {"key": "👺 АНТИТАРО", "price_text": "50 РУБ или 5 бонусов", "desc": "Жесткий разбор иллюзий и самообмана."},
        {"key": "🌘 ТЕНЬ (РАЗОВАЯ)", "price_text": "70 РУБ или 7 бонусов", "desc": "Разбор твоих скрытых качеств и подавленных талантов."},
        {"key": "💰 ДЕНЬГИ (РАЗОВАЯ)", "price_text": "90 РУБ или 9 бонусов", "desc": "Анализ твоих финансовых блоков и точек роста."},
        {"key": "👄 СЕКС (РАЗОВАЯ)", "price_text": "100 РУБ или 10 бонусов", "desc": "Детальный разбор твоей сексуальности и влечения."},
        {"key": "🏁 ФИНАЛ (РАЗОВАЯ)", "price_text": "120 РУБ или 12 бонусов", "desc": "Главный итог и вектор твоего развития."},
        {"key": "👨‍❤️‍👨 СИНАСТРИЯ (СОВМЕСТИМОСТЬ)", "price_text": "150 РУБ или 15 бонусов", "desc": "Жесткий разбор мэтча с партнером."},
        {"key": "📦 БАНДЛ", "price_text": "300 РУБ или 30 бонусов", "desc": "Полный доступ ко всем тайнам твоей матрицы (Секс, Деньги, Тень, Финал)."},
        {"key": "🛰 ТАРИФ 1 (99 РУБ)", "price_text": "99 РУБ", "desc": "ТАРИФ 1: Неделя. Ежедневные транзиты на 7 дней.", "rubles_only": True},
        {"key": "🛰 ТАРИФ 2 (290 РУБ)", "price_text": "290 РУБ", "desc": "ТАРИФ 2: Месяц. Ежедневные транзиты на 30 дней.", "rubles_only": True},
        {"key": "🛰 VIP БАНДЛ (590 РУБ)", "price_text": "590 РУБ", "desc": "VIP БАНДЛ. Полный доступ ко всем тайнам + месяц транзитов.", "rubles_only": True}
    ]

    await message.answer("ВЫБЕРИТЕ УСЛУГУ В КАТАЛОГЕ:")

    for svc in services:
        await asyncio.sleep(0.5)

        btn_label = svc["key"]

        keyboard_obj = {
            "inline": True,
            "buttons": [[{"action": {"type": "text", "label": btn_label}, "color": "secondary"}]]
        }
        kb_json = json.dumps(keyboard_obj, ensure_ascii=False)

        rub_notice = "\n*Оплата возможна только реальными рублями." if svc.get("rubles_only") else ""
        msg_text = f"✦ {btn_label} ✦\nЦена: {svc['price_text']}\n\n{svc['desc']}{rub_notice}"

        try:
            await message.answer(msg_text, keyboard=kb_json)
        except Exception as e:
            print(f"Error sending service block {svc['key']}: {e}")
            await message.answer(msg_text)

    await asyncio.sleep(0.5)
    # Использовать базовую клавиатуру-навигатор
    nav_kb = get_dynamic_keyboard(user)
    await message.answer("ДЛЯ ВОЗВРАТА ВОСПОЛЬЗУЙСЯ МЕНЮ", keyboard=nav_kb)

@labeler.message(text=["✦ СЕКС (РАЗОВАЯ)", "✦ ДЕНЬГИ (РАЗОВАЯ)", "✦ ТЕНЬ (РАЗОВАЯ)", "✦ ФИНАЛ (РАЗОВАЯ)", "👄 СЕКС", "💰 ДЕНЬГИ", "🌘 ТЕНЬ", "🏁 ФИНАЛ"])
async def handle_section_request(message: Message):
    vk_id = message.from_id
    if vk_id in active_tasks:
        return

    user = await get_user(vk_id)
    if not user:
        return

    purchased = user.get("purchased_sections", {})
    text_lower = message.text.lower()

    section_map = {
        "секс": "sex",
        "деньги": "money",
        "тень": "shadow",
        "финал": "final"
    }

    target_section = None
    for key in section_map:
        if key in text_lower:
            target_section = section_map[key]
            break

    if not target_section or not purchased.get(target_section):
        return

    active_tasks.add(vk_id)
    try:

        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
        messages = [
            "Соединяюсь с космосом...",
            "Раскладываю карты. Надеюсь, ты сегодня не грешил...",
            "Анализирую твою карму (и сообщения бывшим)..."
        ]
        for msg in messages:
            await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
            import asyncio
            await asyncio.sleep(2)


        date = user.get("birth_date", "неизвестно")
        time = user.get("birth_time", "неизвестно")
        city = user.get("birth_city", "неизвестно")
        first_name = purchased.get("first_name", "")

        from ai_service import generate_section, generate_voice_intro, generate_audio_prediction
        core_profile = user.get("core_profile", "")
        sex_val = purchased.get("sex_val", 0)
        active_skin = user.get("active_skin", "olesya") if user else "olesya"

        # Generate and send Voice Intro first
        intro_text = await generate_voice_intro(target_section, first_name, skin=active_skin)
        if intro_text:
            audio_bytes = await generate_audio_prediction(intro_text)
            if audio_bytes and audio_bytes != b"dummy_audio_data":
                try:
                    from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  VoiceMessageUploader
                    uploader = VoiceMessageUploader(bot.api)
                    audio_att = await uploader.upload(audio_bytes, peer_id=vk_id)
                    await bot.api.messages.send(peer_id=vk_id, message="", attachment=audio_att, random_id=0)
                except Exception as e:
                    print(f"Error uploading/sending audio intro: {e}")

        result_text = await generate_section(target_section, date, time, city, core_profile, first_name, sex_val, skin=active_skin)

        if not result_text:
            kb_json = await get_sections_keyboard(vk_id, user)
            await message.answer("Ошибка генерации.", keyboard=kb_json)
            return

        if first_name:
            result_text = f"{first_name},\n\n" + result_text

        # Consume the section
        purchased[target_section] = False
        await update_user(vk_id, {"purchased_sections": purchased})

        if target_section in ["sex", "money", "shadow", "final"]:
            import re
            import random
            match = re.search(r"ID_?ТАРО:\s*(\d+)", result_text)
            if match:
                num = int(match.group(1))
                if 0 <= num <= 77:
                    card_id = str(num)
                else:
                    card_id = str(random.randint(0, 77))
            else:
                card_id = str(random.randint(0, 77))

            print(f"[DEBUG] Parsed Card ID: {card_id}")

            # Increment total_cards_received
            user = await get_user(vk_id)
            if user:
                unlocked_cards = user.get("unlocked_cards", {})
                if isinstance(unlocked_cards, list):
                    unlocked_cards = {k: "Первое касание" for k in unlocked_cards}

                if card_id not in unlocked_cards:
                    from ai_service import generate_text
                    grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
                    signature = await generate_text(grimoire_prompt, skin=active_skin)
                    unlocked_cards[card_id] = signature if signature else "Первое касание"

                current_total = user.get("total_cards_received", 0)
                await update_user(vk_id, {"total_cards_received": current_total + 1, "unlocked_cards": unlocked_cards})

            photo_attachment = None
            try:
                photo_attachment = await upload_local_photo(bot.api, f"{card_id}.jpeg")
            except Exception as e:
                print(f"Failed to upload tarot card {card_id}: {e}")

            # Убираем техническую строку с ID_ТАРО из финального текста
            display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", result_text).strip()

            try:
                pdf_filename = f"archive_{vk_id}_{target_section}.pdf"
                generate_pdf(display_text, pdf_filename)
                from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  DocMessagesUploader
                doc_uploader = DocMessagesUploader(bot.api)
                doc_attachment = await doc_uploader.upload(title="Твой_архив.pdf", file_source=pdf_filename, peer_id=vk_id)
                await bot.api.messages.send(peer_id=vk_id, message="Твой персональный архив. Скачай, чтобы не потерять.", attachment=doc_attachment, random_id=0)
                import os
                if os.path.exists(pdf_filename):
                    os.remove(pdf_filename)
            except Exception as e:
                print(f"Failed to process pdf for {target_section}: {e}")

            # Split display_text if the section header exists (e.g. "СЕКС", "ДЕНЬГИ", "ТЕНЬ", "ФИНАЛ")
            section_header = target_section_ru = {
                "sex": "СЕКС",
                "money": "ДЕНЬГИ",
                "shadow": "ТЕНЬ",
                "final": "ФИНАЛ"
            }[target_section]

            parts = re.split(rf"(?i)\b{section_header}\b", display_text, maxsplit=1)

            intro = ""
            main_part = display_text

            if len(parts) > 1:
                intro = parts[0].strip()
                main_part = f"{section_header}\n" + parts[1].strip()

            kb_json = await get_sections_keyboard(vk_id, user)

            from modules.utils import SKIN_ASSETS
            skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"))
            if skin_att:
                await message.answer(attachment=skin_att)
                await asyncio.sleep(0.5)

            if intro:
                await message.answer(intro)

                await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
                await asyncio.sleep(4)

                try:
                    await message.answer(main_part, keyboard=kb_json)
                except Exception as e:
                    print(f"Error sending message with keyboard: {e}")
                    await message.answer(main_part)
            else:
                try:
                    await message.answer(display_text, keyboard=kb_json)
                except Exception as inner_e:
                    print(f"Error sending message with attachment and keyboard: {inner_e}")
                    await message.answer(display_text)

            if photo_attachment:
                await message.answer("", attachment=photo_attachment)

            if target_section == "final":
                # Generate summary for memory
                from ai_service import generate_text
                summary_prompt = (
                    f"Сделай очень короткую выжимку (психологический профиль, 2-3 предложения) "
                    f"из этого текста: {result_text[:1000]}. Это нужно для системной памяти бота."
                )
                active_skin = user.get("active_skin", "olesya") if user else "olesya"
                core_profile = await generate_text(summary_prompt, skin=active_skin)
                if core_profile:
                    await update_user(vk_id, {"core_profile": core_profile})
        else:
            kb_json = await get_sections_keyboard(vk_id, user)
            try:
                await message.answer(result_text, keyboard=kb_json)
            except Exception as e:
                print(f"Error sending text with keyboard: {e}")
                await message.answer(result_text)

    finally:
        active_tasks.discard(vk_id)

@labeler.message(text=["Синастрия (Совместимость)", "✦ Синастрия (Совместимость)", "👨‍❤️‍👨 СИНАСТРИЯ (СОВМЕСТИМОСТЬ)", "👨‍❤️‍👨 СИНАСТРИЯ"])
async def synastry_handler(message: Message):
    import json
    vk_id = message.from_id
    if vk_id in active_tasks:
        return

    user = await get_user(vk_id)
    if not user:
        return

    text = message.text.strip()
    if not text or text.lower() in ["начать", "start", "/start", "лайн голос"] or (text.startswith("✦") and "Синастрия" not in text) and "СИНАСТРИЯ" not in text:
        return

    state_dict = await get_fsm_step(vk_id)
    if state_dict is not None and "step" in state_dict:
        return

    active_tasks.add(vk_id)
    try:
        balance = user.get("balance", 0)
        amount_needed = 150
        if balance >= amount_needed:
            new_balance = balance - amount_needed
            await update_user(vk_id, {"balance": new_balance})

            # Start Synastry FSM
            await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_name"}))
            await message.answer("СИНАСТРИЯ АКТИВИРОВАНА.\n\nВведите ИМЯ вашего партнера:")
        else:
            keyboard_obj = {
                "inline": True,
                "buttons": [[{
                    "action": {"type": "vkpay", "hash": f"action=pay-to-group&group_id=219181948&amount={amount_needed}"}
                }]]
            }
            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
            msg_text = f"РАЗДЕЛ СИНАСТРИЯ - Цена: {amount_needed} РУБ.\nЖесткий разбор мэтча с партнером.\n\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ."

            photo_attachment = None
            try:
                from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  PhotoMessageUploader
                uploader = PhotoMessageUploader(bot.api)
                filepath = "cards/sin.jpeg"
                import aiofiles
                async with aiofiles.open(filepath, "rb") as f:
                    data = await f.read()
                    photo_attachment = await uploader.upload(data)
            except Exception as e:
                print(f"[ERROR] Failed to load image sin.jpeg from local storage: {e}")

            if photo_attachment:
                try:
                    await message.answer(msg_text, attachment=photo_attachment, keyboard=kb_json)
                except Exception:
                    await message.answer(msg_text, attachment=photo_attachment)
            else:
                try:
                    await message.answer(msg_text, keyboard=kb_json)
                except Exception:
                    await message.answer(msg_text)
    finally:
        active_tasks.discard(vk_id)

async def is_waiting_synastry_name(message: Message) -> bool:
    if message.text and (message.text.lower() in ["начать", "start", "/start", "лайн голос"] or message.text.startswith("✦")):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_name"

@labeler.message(func=is_waiting_synastry_name)
async def process_synastry_name(message: Message):
    vk_id = message.from_id
    if vk_id in active_tasks:
        return

    active_tasks.add(vk_id)
    try:
        import json
        partner_name = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_date", "partner_name": partner_name}))
        await message.answer(f"Имя {partner_name} принято. Теперь введите ДАТУ РОЖДЕНИЯ партнера (например, 15.04.1990):")
    finally:
        active_tasks.discard(vk_id)

async def is_waiting_synastry_date(message: Message) -> bool:
    if message.text and (message.text.lower() in ["начать", "start", "/start", "лайн голос"] or message.text.startswith("✦")):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_date"

@labeler.message(func=is_waiting_synastry_date)
async def process_synastry_date(message: Message):
    vk_id = message.from_id
    if vk_id in active_tasks:
        return

    user = await get_user(vk_id)
    if not user:
        return

    active_tasks.add(vk_id)
    try:
        partner_date = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")

        # Clear state
        await set_user_state(vk_id, "")


        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
        messages = [
            "Соединяюсь с космосом...",
            "Раскладываю карты. Надеюсь, ты сегодня не грешил...",
            "Анализирую твою карму (и сообщения бывшим)..."
        ]
        for msg in messages:
            await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
            import asyncio
            await asyncio.sleep(2)


        date = user.get("birth_date", "неизвестно")
        time = user.get("birth_time", "неизвестно")
        city = user.get("birth_city", "неизвестно")
        purchased = user.get("purchased_sections", {})
        first_name = purchased.get("first_name", "")
        sex_val = purchased.get("sex_val", 0)
        core_profile = user.get("core_profile", "")

        from ai_service import generate_section, generate_voice_intro, generate_audio_prediction

        # 1. Voice intro
        active_skin = user.get("active_skin", "olesya") if user else "olesya"
        intro_text = await generate_voice_intro("synastry", first_name, partner_name, skin=active_skin)
        if intro_text:
            audio_bytes = await generate_audio_prediction(intro_text)
            if audio_bytes and audio_bytes != b"dummy_audio_data":
                try:
                    from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  VoiceMessageUploader
                    uploader = VoiceMessageUploader(bot.api)
                    audio_att = await uploader.upload(audio_bytes, peer_id=vk_id)
                    await bot.api.messages.send(peer_id=vk_id, message="", attachment=audio_att, random_id=0)
                except Exception as e:
                    print(f"Error uploading/sending audio intro: {e}")

        # 2. Main text
        result_text = await generate_section("synastry", date, time, city, core_profile, first_name, sex_val, partner_name=partner_name, partner_date=partner_date, skin=active_skin)

        if not result_text:
            result_text = "Система не смогла рассчитать совместимость."
        else:
            if first_name:
                result_text = f"{first_name},\n\n" + result_text

        kb_json = await get_sections_keyboard(vk_id, user)

        # Try to parse tarot id
        import re
        import random
        match = re.search(r"ID_?ТАРО:\s*(\d+)", result_text)
        if match:
            num = int(match.group(1))
            if 0 <= num <= 77:
                card_id = str(num)
            else:
                card_id = str(random.randint(0, 77))
        else:
            card_id = str(random.randint(0, 77))

        # Increment total_cards_received
        user = await get_user(vk_id)
        if user:
            unlocked_cards = user.get("unlocked_cards", {})
            if isinstance(unlocked_cards, list):
                unlocked_cards = {k: "Первое касание" for k in unlocked_cards}

            if card_id not in unlocked_cards:
                from ai_service import generate_text
                grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
                signature = await generate_text(grimoire_prompt, skin=active_skin)
                unlocked_cards[card_id] = signature if signature else "Первое касание"

            current_total = user.get("total_cards_received", 0)
            await update_user(vk_id, {"total_cards_received": current_total + 1, "unlocked_cards": unlocked_cards})

        photo_attachment = None
        try:
            from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  PhotoMessageUploader
            photo_attachment = await upload_local_photo(bot.api, f"{card_id}.jpeg")
        except Exception as e:
            print(f"Failed to upload tarot card {card_id}: {e}")

        display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", result_text).strip()

        try:
            pdf_filename = f"archive_{vk_id}_synastry.pdf"
            generate_pdf(display_text, pdf_filename)
            from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  DocMessagesUploader
            doc_uploader = DocMessagesUploader(bot.api)
            doc_attachment = await doc_uploader.upload(title="Твой_архив.pdf", file_source=pdf_filename, peer_id=vk_id)
            await bot.api.messages.send(peer_id=vk_id, message="Твой персональный архив. Скачай, чтобы не потерять.", attachment=doc_attachment, random_id=0)
            import os
            if os.path.exists(pdf_filename):
                os.remove(pdf_filename)
        except Exception as e:
            print(f"Failed to process pdf for synastry: {e}")

        parts = re.split(rf"(?i)\bСИНАСТРИЯ\b", display_text, maxsplit=1)
        intro = ""
        main_part = display_text

        if len(parts) > 1:
            intro = parts[0].strip()
            main_part = f"СИНАСТРИЯ\n" + parts[1].strip()

        from modules.utils import SKIN_ASSETS
        skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"))
        if skin_att:
            await message.answer(attachment=skin_att)
            await asyncio.sleep(0.5)

        if intro:
            await message.answer(intro)
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
            await asyncio.sleep(4)
            try:
                await message.answer(main_part, keyboard=kb_json)
            except:
                await message.answer(main_part)
        else:
            try:
                await message.answer(display_text, keyboard=kb_json)
            except:
                await message.answer(display_text)

        if photo_attachment:
            await message.answer("", attachment=photo_attachment)

    finally:
        active_tasks.discard(vk_id)
