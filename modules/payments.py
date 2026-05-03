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

async def get_storefront_keyboard(purchased: dict) -> str | None:
    import json
    buttons = []

    if not purchased.get("sex"):
        buttons.append([{"action": {"type": "text", "label": "СЕКС (РАЗОВАЯ)"}, "color": "secondary"}])

    if not purchased.get("money"):
        buttons.append([{"action": {"type": "text", "label": "ДЕНЬГИ (РАЗОВАЯ)"}, "color": "secondary"}])

    if not purchased.get("shadow"):
        buttons.append([{"action": {"type": "text", "label": "ТЕНЬ (РАЗОВАЯ)"}, "color": "secondary"}])

    if not purchased.get("final"):
        buttons.append([{"action": {"type": "text", "label": "ФИНАЛ (РАЗОВАЯ)"}, "color": "secondary"}])

    purchased_count = sum([bool(purchased.get("sex")), bool(purchased.get("money")), bool(purchased.get("shadow")), bool(purchased.get("final"))])
    if purchased_count < 2:
        buttons.append([{"action": {"type": "text", "label": "БАНДЛ"}, "color": "secondary"}])

    # Oracle freemium skip button (always added as an option to purchase)
    buttons.append([{"action": {"type": "text", "label": "ВОПРОС СУДЬБЕ"}, "color": "secondary"}])

    if buttons:
        keyboard_obj = {
            "inline": True,
            "buttons": buttons
        }
        return json.dumps(keyboard_obj, ensure_ascii=False)
    return None

@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
async def message_event_handler(event: dict):
    obj = event.get("object", {})
    vk_id = obj.get("user_id")
    peer_id = obj.get("peer_id")
    event_id = obj.get("event_id")
    payload = obj.get("payload", {})

    if not vk_id or not payload or "oracle_card" not in payload:
        return

    card_id = payload["oracle_card"]

    try:
        import json
        # Stop loading animation
        await bot.api.messages.send_message_event_answer(
            event_id=event_id,
            user_id=vk_id,
            peer_id=peer_id
        )

        state_dict = await get_fsm_step(vk_id)
        if not state_dict or state_dict.get("step") != "oracle_draw":
            return

        drawn_cards = state_dict.get("drawn_cards", [])
        pool = state_dict.get("pool", [])

        if card_id not in drawn_cards:
            drawn_cards.append(card_id)

        if len(drawn_cards) < 3:
            state_dict["drawn_cards"] = drawn_cards
            await set_user_state(vk_id, json.dumps(state_dict))

            from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Callback
            kb = Keyboard(inline=True)

            # Render only available cards
            btn_count = 0
            for c_id in pool:
                if c_id not in drawn_cards:
                    if btn_count > 0 and btn_count % 5 == 0:
                        kb.row()
                    kb.add(Callback("🎴", payload={"oracle_card": c_id}))
                    btn_count += 1

            await bot.api.messages.edit(
                peer_id=peer_id,
                message=f"Выбрано: {len(drawn_cards)}/3...",
                conversation_message_id=obj.get("conversation_message_id"),
                keyboard=kb.get_json()
            )
        else:
            # 3 cards selected
            await set_user_state(vk_id, "") # Clear FSM state

            # To completely remove the keyboard, we need to pass an empty keyboard payload
            empty_kb = Keyboard(inline=True)

            await bot.api.messages.edit(
                peer_id=peer_id,
                message="Выбрано: 3/3. Карты собраны.",
                conversation_message_id=obj.get("conversation_message_id"),
                keyboard=empty_kb.get_json()
            )

            # Trigger process_oracle_final asynchronously to avoid blocking callback
            import asyncio
            asyncio.create_task(process_oracle_final(vk_id, state_dict["question"], drawn_cards))

    except Exception as e:
        print(f"Error in message_event_handler: {e}")

@labeler.raw_event(GroupEventType.VKPAY_TRANSACTION, dataclass=dict)
async def money_transfer_handler(event: dict):
    try:
        group_id = event.get("group_id")
        if group_id != 219181948:
            return

        # VK API typically sends event within an object depending on the exact callback format
        # In message_event or money_transfer, we can extract from_id and amount
        obj = event.get("object", {})
        vk_id = obj.get("from_id")
        amount = obj.get("amount")

        if not vk_id or not amount:
            return

        # amount is in kopecks or rubles? standard money_transfer is rubles usually, but if kopecks it's amount / 100
        # Let's check amount string or integer. In VK it's typically an integer amount.
        # Assuming 99 or 399

        amount_val = int(amount)
        if amount_val > 1000: # if it's in kopecks like 9900
            amount_val = amount_val // 100

        user = await get_user(vk_id)
        if not user:
            print(f"ПЛАТЕЖ ОТ НЕИЗВЕСТНОГО ПОЛЬЗОВАТЕЛЯ: vk_id={vk_id}, amount={amount_val}")
            return

        current_balance = user.get("balance", 0)
        new_balance = current_balance + amount_val

        await update_user(vk_id, {"balance": new_balance})

        await bot.api.messages.send(
            peer_id=vk_id,
            message=f"БАЛАНС ПОПОЛНЕН! НА ТВОЕМ СЧЕТУ: {new_balance} РУБ. ТЕПЕРЬ ТЫ МОЖЕШЬ АКТИВИРОВАТЬ ВЫБРАННУЮ УСЛУГУ",
            random_id=0
        )
        try:
            await bot.api.messages.send(
                peer_id=27260796,
                message=f"💰 Пополнение баланса: {amount} РУБ от пользователя {vk_id}",
                random_id=0
            )
        except Exception:
            pass

    except Exception as e:
        print(f"Error handling money_transfer: {e}")

async def process_payment_and_generate(vk_id: int, section: str):
    if vk_id in active_tasks:
        return
    user = await get_user(vk_id)
    if not user:
        return

    active_tasks.add(vk_id)
    try:
        try:
            await bot.api.messages.send(
                peer_id=27260796,
                message=f"🛒 Покупка услуги {section} пользователем {vk_id}",
                random_id=0
            )
        except Exception:
            pass

        # Mark as purchased in database
        purchased = user.get("purchased_sections", {})
        if section == "all":
            purchased["sex"] = True
            purchased["money"] = True
            purchased["shadow"] = True
            purchased["final"] = True
            await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.\n\nВсе Врата открыты.", random_id=0)
            try:
                await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
                messages = [
                    "Соединяюсь с космосом...",
                    "Раскладываю карты. Надеюсь, ты сегодня не грешил...",
                    "Анализирую твою карму (и сообщения бывшим)...",
                    "Формирую полный БАНДЛ..."
                ]
                import asyncio
                for msg in messages:
                    await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
                    await asyncio.sleep(2)

                date = user.get("birth_date", "неизвестно")
                time = user.get("birth_time", "неизвестно")
                city = user.get("birth_city", "неизвестно")
                first_name = purchased.get("first_name", "")
                sex_val = purchased.get("sex_val", 0)
                core_profile = user.get("core_profile", "")

                from ai_service import generate_section
                bundle_text = ""
                active_skin = user.get("active_skin", "olesya") if user else "olesya"
                for sect, name in [("sex", "СЕКС"), ("money", "ДЕНЬГИ"), ("shadow", "ТЕНЬ"), ("final", "ФИНАЛ")]:
                    part_text = await generate_section(sect, date, time, city, core_profile, first_name, sex_val, skin=active_skin)
                    if part_text:
                        import re
                        part_text = re.sub(r"ID_?ТАРО:\s*\d+", "", part_text).strip()
                        bundle_text += f"\n\n--- РАЗДЕЛ {name} ---\n\n" + part_text

                if bundle_text:
                    pdf_filename = f"archive_{vk_id}_bundle.pdf"
                    generate_pdf(bundle_text, pdf_filename)
                    from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  DocMessagesUploader
                    doc_uploader = DocMessagesUploader(bot.api)
                    doc_attachment = await doc_uploader.upload(title="Твой_архив_БАНДЛ.pdf", file_source=pdf_filename, peer_id=vk_id)
                    await bot.api.messages.send(peer_id=vk_id, message="Твой персональный архив (БАНДЛ). Скачай, чтобы не потерять.", attachment=doc_attachment, random_id=0)
                    import os
                    if os.path.exists(pdf_filename):
                        os.remove(pdf_filename)

                    purchased["sex"] = False
                    purchased["money"] = False
                    purchased["shadow"] = False
                    purchased["final"] = False
                    await update_user(vk_id, {"purchased_sections": purchased})
            except Exception as e:
                print(f"Error generating bundle pdf: {e}")
        elif section == "oracle":
            purchased["oracle_access"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.\n\nНАПИШИ СВОЙ ВОПРОС СУДЬБЕ ПРЯМО СЕЙЧАС.", random_id=0)
        elif section in ["sex", "money", "shadow", "final"]:
            purchased[section] = True
            updates = {"purchased_sections": purchased}

            # Check if all four main sections are purchased
            if purchased.get("sex") and purchased.get("money") and purchased.get("shadow") and purchased.get("final"):
                updates["has_full_chart"] = True

            await update_user(vk_id, updates)
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.\n\nРаздел открыт.", random_id=0)

        user = await get_user(vk_id)
        kb_json = await get_sections_keyboard(vk_id, user)

        if section != "oracle":
            await bot.api.messages.send(
                peer_id=vk_id,
                message="Используйте меню для вызова нужного раздела:",
                keyboard=kb_json,
                random_id=0
            )
    finally:
        active_tasks.discard(vk_id)

@labeler.message(text=["СЕКС (РАЗОВАЯ)", "ДЕНЬГИ (РАЗОВАЯ)", "ТЕНЬ (РАЗОВАЯ)", "ФИНАЛ (РАЗОВАЯ)", "БАНДЛ"])
async def handle_storefront_purchase(message: Message):
    import json
    vk_id = message.from_id
    text = message.text.upper()

    user = await get_user(vk_id)
    if not user:
        return

    service_map = {
        "СЕКС (РАЗОВАЯ)": {
            "name": "Секс",
            "amount": 100,
            "section_key": "sex",
            "image_name": "sex1.jpg",
            "desc": "РАЗДЕЛ СЕКС   - Цена: 100 РУБ\nТекст: Детальный разбор твоей сексуальности и влечения.\nМеханика: Твоя дата рождения - карта Таро - профессиональный разбор Оракулом.\nВажно: Это разовая консультация. После выдачи текста доступ закроется."
        },
        "ДЕНЬГИ (РАЗОВАЯ)": {
            "name": "Деньги",
            "amount": 90,
            "section_key": "money",
            "image_name": "money1.jpg",
            "desc": "РАЗДЕЛ ДЕНЬГИ   - Цена: 90 РУБ\nТекст: Анализ твоих финансовых блоков и точек роста.\nМеханика: Дата рождения - карта Таро - профессиональный разбор Оракулом.\nВажно: Доступ на один сеанс. Для повторного анализа нужна новая оплата."
        },
        "ТЕНЬ (РАЗОВАЯ)": {
            "name": "Тень",
            "amount": 70,
            "section_key": "shadow",
            "image_name": "demon1.jpg",
            "desc": "РАЗДЕЛ ТЕНЬ   - Цена: 70 РУБ\nТекст: Разбор твоих скрытых качеств и подавленных талантов.\nМеханика: Дата рождения - карта Таро - профессиональный разбор Оракулом.\nВажно: Услуга разовая. Доступ сгорает после получения ответа."
        },
        "ФИНАЛ (РАЗОВАЯ)": {
            "name": "Финал",
            "amount": 120,
            "section_key": "final",
            "image_name": "way1.jpg",
            "desc": "РАЗДЕЛ ФИНАЛ   - Цена: 120 РУБ\nТекст: Главный итог и вектор твоего развития.\nМеханика: Полный синтез всех твоих данных и профессиональный разбор Оракулом.\nВажно: Разовый доступ. Повторный разбор оплачивается отдельно."
        },
        "БАНДЛ": {
            "name": "Бандл",
            "amount": 300,
            "section_key": "all",
            "image_name": "full1.jpg",
            "desc": "РАЗДЕЛ БАНДЛ - Цена: 300 РУБ\nТекст: Полный доступ ко всем тайнам твоей матрицы.\nМеханика: Вскрытие всех четырех архивов (Секс, Деньги, Тень, Финал) со скидкой.\nВажно: Самое выгодное предложение для тех, кто хочет взломать систему целиком."
        },
        "ВОПРОС СУДЬБЕ": {
            "name": "Оракул",
            "amount": 50,
            "section_key": "oracle",
            "image_name": "ora1.jpg",
            "desc": "РАЗДЕЛ ОРАКУЛ - Цена: 50 РУБ\nТекст: [Раз в сутки бесплатно] Снятие блокировки и мгновенный ответ на твой вопрос.\nМеханика: Четкий вопрос - ОБРЕЗАТЬ КОЛОДУ - интеллектуальный анализ подсознания через символику.\nВажно: Система перегрета? Оплати принудительную синхронизацию для доступа."
        }
    }

    service_info = service_map.get(text)
    if not service_info:
        await message.answer("Услуга не найдена. Выбери из меню.")
        return

    balance = user.get("balance", 0)
    amount_needed = service_info["amount"]

    if balance >= amount_needed:
        new_balance = balance - amount_needed
        await update_user(vk_id, {"balance": new_balance})
        await process_payment_and_generate(vk_id, service_info["section_key"])
    else:
        keyboard_obj = {
            "inline": True,
            "buttons": [[{
                "action": {"type": "vkpay", "hash": f"action=pay-to-group&group_id=219181948&amount={amount_needed}"}
            }]]
        }
        kb_json = json.dumps(keyboard_obj, ensure_ascii=False)

        if "desc" in service_info:
            msg_text = f"{service_info['desc']}\n\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ."
            image_name = service_info['image_name']
            photo_attachment = None

            try:
                from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  PhotoMessageUploader
                uploader = PhotoMessageUploader(bot.api)
                filepath = f"cards/{image_name}"
                import aiofiles
                async with aiofiles.open(filepath, "rb") as f:
                    data = await f.read()
                    photo_attachment = await uploader.upload(data)
            except Exception as e:
                print(f"[ERROR] Failed to load image {image_name} from local storage: {e}")

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
        else:
            msg_text = f"{service_info.get('text', '')}\n\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ."
            await message.answer(msg_text, keyboard=kb_json)

@labeler.message(text=["ТАРИФ 1 (99 РУБ)", "ТАРИФ 2 (290 РУБ)", "VIP БАНДЛ (590 РУБ)"])
async def process_tariff_purchase(message: Message):
    vk_id = message.from_id
    if vk_id in active_tasks:
        return

    user = await get_user(vk_id)
    if not user:
        return

    active_tasks.add(vk_id)
    try:
        text = message.text.upper()
        balance = user.get("balance", 0)

        tariff_map = {
            "ТАРИФ 1 (99 РУБ)": {"price": 99, "days": 7, "bundle": False},
            "ТАРИФ 2 (290 РУБ)": {"price": 290, "days": 30, "bundle": False},
            "VIP БАНДЛ (590 РУБ)": {"price": 590, "days": 30, "bundle": True}
        }

        t_info = tariff_map.get(text)
        if not t_info:
            return

        price = t_info["price"]

        if balance >= price:
            import datetime
            new_balance = balance - price
            updates = {"balance": new_balance}

            now = datetime.datetime.now()
            current_expires = user.get("transit_sub_expires_at")
            if current_expires:
                try:
                    exp_date = datetime.datetime.fromisoformat(current_expires)
                    if exp_date > now:
                        now = exp_date
                except ValueError:
                    pass

            new_expires = now + datetime.timedelta(days=t_info["days"])
            updates["transit_sub_expires_at"] = new_expires.isoformat()

            if t_info["bundle"]:
                purchased = user.get("purchased_sections", {})
                purchased["sex"] = True
                purchased["money"] = True
                purchased["shadow"] = True
                purchased["final"] = True
                updates["purchased_sections"] = purchased
                updates["has_full_chart"] = True

            await update_user(vk_id, updates)

            msg = f"ОПЛАТА УСПЕШНА.\n\nТранзит продлен до {new_expires.strftime('%d.%m.%Y %H:%M')}."
            if t_info["bundle"]:
                msg += "\nVIP БАНДЛ АКТИВИРОВАН. Все Врата открыты (Секс, Деньги, Тень, Финал)."

            msg += f"\nТВОЙ ТЕКУЩИЙ БАЛАНС: {new_balance} РУБ."

            # Fetch fresh user to update keyboard if bundle bought
            updated_user = await get_user(vk_id)
            kb_json = await get_sections_keyboard(vk_id, updated_user)

            await message.answer(msg, keyboard=kb_json)
        else:
            import json
            keyboard_obj = {
                "inline": True,
                "buttons": [[{
                    "action": {"type": "vkpay", "hash": f"action=pay-to-group&group_id=219181948&amount={price}"}
                }]]
            }
            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
            await message.answer(f"Недостаточно средств. Цена: {price} РУБ.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ.\nОплата возможна только реальным балансом.", keyboard=kb_json)

    finally:
        active_tasks.discard(vk_id)
