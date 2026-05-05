import os
import json
import math
from cache import acquire_lock, release_lock
from modules.states import MyStates
import asyncio

import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader, Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, generate_premium_pdf, get_fsm_step, upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, cover_cache, SKIN_ASSETS, pdf_semaphore
from loguru import logger

labeler = BotLabeler()

@labeler.message(text=["✦ Услуги", "Услуги", "✦ УСЛУГИ 🛒"])
async def show_services_handler(message: Message):
    logger.info(f"show_services_handler triggered by from_id={message.from_id}")
    await show_services(message.from_id, message.peer_id, 0)

async def show_services(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None):


    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        try:
            await bot.api.messages.send(peer_id=peer_id, message="ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.", random_id=0)
        except Exception as e:
            logger.exception("Ignored Exception")
        return

    services = [
        {
            "key": "sex",
            "title": "Твоя сексуальная энергия",
            "desc": "Что это даст: Глубокое понимание своих истинных желаний и блоков в интимной сфере.\nКак это работает: Расклад на картах с анализом твоей матрицы страсти.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', выбери карту из моей колоды, и через минуту я пришлю тебе личный разбор.",
            "price_text": "1000 Энергии звезд",
            "image_name": "sex1.jpg"
        },
        {
            "key": "money",
            "title": "Код твоего богатства",
            "desc": "Что это даст: Понимание, как пробить финансовый потолок и привлечь деньги в свою жизнь.\nКак это работает: Анализ финансового потока и твоих скрытых возможностей.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', выбери карту из моей колоды, и через минуту я пришлю тебе личный разбор.",
            "price_text": "900 Энергии звезд",
            "image_name": "money1.jpg"
        },
        {
            "key": "shadow",
            "title": "Твои скрытые грани",
            "desc": "Что это даст: Раскрытие подавленных эмоций и теневых сторон личности, мешающих росту.\nКак это работает: Работа с подсознанием через темные арканы.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', выбери карту из моей колоды, и через минуту я пришлю тебе личный разбор.",
            "price_text": "700 Энергии звезд",
            "image_name": "demon1.jpg"
        },
        {
            "key": "final",
            "title": "Твой истинный путь",
            "desc": "Что это даст: Осознание своего предназначения и глобального вектора развития.\nКак это работает: Полный расклад на жизненный путь и кармические задачи.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', выбери карту из моей колоды, и через минуту я пришлю тебе личный разбор.",
            "price_text": "1200 Энергии звезд",
            "image_name": "way1.jpg"
        },
        {
            "key": "synastry",
            "title": "Тайна ваших отношений",
            "desc": "Что это даст: Полный разбор совместимости с партнером, сильные и слабые стороны союза.\nКак это работает: Жесткий разбор мэтча с партнером.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', выбери карту из моей колоды, и через минуту я пришлю тебе личный разбор.",
            "price_text": "1500 Энергии звезд",
            "image_name": "sin.jpeg"
        },
        {
            "key": "oracle",
            "title": "Вопрос судьбе (Оракул)",
            "desc": "Что это даст: Мгновенный ответ на твой вопрос от мироздания.\nКак это работает: Интеллектуальный анализ подсознания через символику. Без воды.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', чтобы открыть диалог с судьбой.",
            "price_text": "500 Энергии звезд",
            "image_name": "ora1.jpg"
        },
        {
            "key": "antitaro",
            "title": "Антитаро (Разрыв иллюзий)",
            "desc": "Что это даст: Жесткий разбор иллюзий и самообмана. Раздел для тех, кто готов услышать неприятную правду.\nКак это работает: Снятие розовых очков.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', выбери карту из моей колоды, и через минуту я пришлю тебе личный разбор.",
            "price_text": "500 Энергии звезд",
            "image_name": "demon1.jpg"
        },
        {
            "key": "all",
            "title": "Золотой архив всех откровений",
            "desc": "Что это даст: Полный доступ ко всем тайнам твоей матрицы (Сексуальная энергия, Деньги, Скрытые грани, Истинный путь).\nКак это работает: Комплексный анализ всех сфер жизни.\nВремя подготовки: 1 минута.\n\nСделай шаг навстречу себе. Нажми 'Купить', выбери карту из моей колоды, и через минуту я пришлю тебе личный разбор.",
            "price_text": "3000 Энергии звезд",
            "image_name": "full1.jpg"
        }
    ]

    elements = []
    for svc in services:
        att = await upload_local_photo(bot.api, svc['image_name']) if svc['image_name'] else None

        # Trim description to fit VK Carousel limits (approx 80 chars for title, 80 chars for description in carousel)
        # However, for carousel description max length is 80, title is 80.
        title_trimmed = svc['title'][:80]
        desc_trimmed = svc['desc'][:80] + "..." if len(svc['desc']) > 80 else svc['desc']

        # We need a valid action URL or action for the element itself. Usually "open_photo" or "open_link"
        element = {
            "title": title_trimmed,
            "description": f"Цена: {svc['price_text']}\n{desc_trimmed}",
            "action": {"type": "open_photo"},
            "buttons": [
                {
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "buy", "type": "service", "key": svc['key']}),
                        "label": "КУПИТЬ"
                    },
                    "color": "positive"
                }
            ]
        }

        if att:
            # att format from upload_photo is "photo{owner_id}_{photo_id}"
            photo_id = att.replace("photo", "")
            if "_" in photo_id:
                element["photo_id"] = photo_id

        elements.append(element)

    template = {
        "type": "carousel",
        "elements": elements
    }

    template_json = json.dumps(template, ensure_ascii=False)
    msg_text = "✦ ВИТРИНА УСЛУГ ✦\nВыберите услугу и нажмите 'КУПИТЬ'."

    try:
        await bot.api.messages.send(peer_id=peer_id, message=msg_text, template=template_json, random_id=0)
    except Exception as e:
        logger.exception(f"Error sending service carousel: {e}")
        try:
            await bot.api.messages.send(peer_id=peer_id, message=msg_text, random_id=0)
        except Exception as e:
            logger.exception("Ignored Exception")


async def is_waiting_synastry_name(message: Message) -> bool:
    if message.text and message.text.startswith("✦"):
        return False
    if message.text and message.text.lower() in ["начать", "start", "/start", "лайн голос"]:
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_name"

@labeler.message(func=is_waiting_synastry_name)
async def process_synastry_name(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:

        partner_name = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_date", "partner_name": partner_name}))
        await message.answer(f"Имя {partner_name} принято. Теперь введите ДАТУ РОЖДЕНИЯ партнера (например, 15.04.1990):")
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_SYNASTRY_DATE)
async def process_synastry_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        return

    try:
        partner_date = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")

        await set_user_state(vk_id, "")

        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
        messages = [
            "Соединяюсь с космосом...",
            "Раскладываю карты. Надеюсь, ты сегодня не грешил...",
            "Анализирую твою карму (и сообщения бывшим)..."
        ]
        for msg in messages:
            await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)

            await asyncio.sleep(2)

        date = user.get("birth_date", "неизвестно")
        time = user.get("birth_time", "неизвестно")
        city = user.get("birth_city", "неизвестно")
        purchased = user.get("purchased_sections", {})
        first_name = purchased.get("first_name", "")
        sex_val = purchased.get("sex_val", 0)
        core_profile = user.get("core_profile", "")



        active_skin = user.get("active_skin", "olesya") if user else "olesya"

        await bot.api.messages.send(peer_id=vk_id, message="ЧИТАЮ ЛИНИИ ВЕРОЯТНОСТИ...", random_id=0)
        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")

        result_text = await generate_section("synastry", date, time, city, core_profile, first_name, sex_val, partner_name=partner_name, partner_date=partner_date, skin=active_skin)

        if not result_text:
            result_text = "Система не смогла рассчитать совместимость."
        else:
            if first_name:
                result_text = f"{first_name},\n\n" + result_text

        kb_json = await get_sections_keyboard(vk_id, user)



        match = re.search(r"ID_?ТАРО:\s*(\d+)", result_text)
        if match:
            num = int(match.group(1))
            if 0 <= num <= 77:
                card_id = str(num)
            else:
                card_id = str(random.randint(0, 77))
        else:
            card_id = str(random.randint(0, 77))

        user = await get_user(vk_id)
        if user:
            unlocked_cards = user.get("unlocked_cards", {})
            if isinstance(unlocked_cards, list):
                unlocked_cards = {k: "Первое касание" for k in unlocked_cards}

            if card_id not in unlocked_cards:

                grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
                signature = await generate_text(grimoire_prompt, skin=active_skin)
                unlocked_cards[card_id] = signature if signature else "Первое касание"

            current_total = user.get("total_cards_received", 0)
            await update_user(vk_id, {"total_cards_received": current_total + 1, "unlocked_cards": unlocked_cards})

        photo_attachment = None
        try:

            photo_attachment = await upload_local_photo(bot.api, f"{card_id}.jpeg")
        except Exception as e:
            logger.exception(f"Failed to upload tarot card {card_id}: {e}")

        display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", result_text).strip()

        try:
            pdf_filename = f"archive_{vk_id}_synastry.pdf"

            date = user.get("birth_date", "неизвестно")
            time = user.get("birth_time", "неизвестно")
            city = user.get("birth_city", "неизвестно")
            birth_info = f"{date} {time} {city}"
            partner_name = state_dict.get("partner_name", "Партнер")

            async with pdf_semaphore:
                await asyncio.to_thread(generate_premium_pdf, partner_name, birth_info, "СИНАСТРИЯ", display_text, pdf_filename, card_id)

            doc_uploader = DocMessagesUploader(bot.api)
            doc_attachment = await doc_uploader.upload(title="Твой_архив.pdf", file_source=pdf_filename, peer_id=vk_id)
            await bot.api.messages.send(peer_id=vk_id, message="Твой персональный архив. Скачай, чтобы не потерять.", attachment=doc_attachment, random_id=0)

            if os.path.exists(pdf_filename):
                await asyncio.to_thread(os.remove, pdf_filename)
        except Exception as e:
            logger.exception(f"Failed to process pdf for synastry: {e}")

        parts = re.split(rf"(?i)\bСИНАСТРИЯ\b", display_text, maxsplit=1)
        intro = ""
        main_part = display_text

        if len(parts) > 1:
            intro = parts[0].strip()
            main_part = f"СИНАСТРИЯ\n" + parts[1].strip()


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
                await message.answer(main_part)
        else:
            try:
                await message.answer(display_text, keyboard=kb_json)
            except Exception as e:
                await message.answer(display_text)

        if photo_attachment:
            caption = ""
            if user:
                unlocked_cards = user.get("unlocked_cards", {})
                if isinstance(unlocked_cards, dict):
                    caption = unlocked_cards.get(card_id, "Новая карта добавлена в твой Гримуар.")

            try:
                await message.answer(f"🎴 Значение карты:\n{caption}", attachment=photo_attachment)
            except Exception as e:
                await message.answer("", attachment=photo_attachment)

    finally:
        await release_lock(vk_id)

@labeler.message(text=["🛰 ТАРИФЫ"])
async def show_tariffs_handler(message: Message):
    await show_tariffs(message.from_id, message.peer_id, 0)

async def show_tariffs(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None):


    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        try:
            await bot.api.messages.send(peer_id=peer_id, message="ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.", random_id=0)
        except Exception as e:
            logger.exception("Ignored Exception")
        return

    tariffs = [
        {
            "key": "tariff_1",
            "title": "Спутник 7 дней",
            "desc": "Что это даст: Ежедневные транзиты и прогнозы на 7 дней.\nКак это работает: Автоматическая рассылка каждое утро.\nВремя подготовки: Мгновенная активация.\n\nИнструкция: Нажми кнопку Купить. Система настроится на твои вибрации.",
            "price_text": "990 Энергии звезд",
            "image_name": "full1.jpg"
        },
        {
            "key": "tariff_2",
            "title": "Оракул 30 дней",
            "desc": "Что это даст: Ежедневные транзиты и прогнозы на 30 дней.\nКак это работает: Автоматическая рассылка каждое утро.\nВремя подготовки: Мгновенная активация.\n\nИнструкция: Нажми кнопку Купить. Система настроится на твои вибрации.",
            "price_text": "2900 Энергии звезд",
            "image_name": "full1.jpg"
        },
        {
            "key": "tariff_vip",
            "title": "VIP Архив",
            "desc": "Что это даст: Полный доступ ко всем тайнам (Золотой архив) + месяц ежедневных транзитов.\nКак это работает: Полная разблокировка функционала.\nВремя подготовки: Мгновенная активация.\n\nИнструкция: Нажми кнопку Купить. Система настроится на твои вибрации.",
            "price_text": "5900 Энергии звезд",
            "image_name": "full1.jpg"
        }
    ]

    elements = []
    for svc in tariffs:
        att = await upload_local_photo(bot.api, svc['image_name']) if svc['image_name'] else None

        title_trimmed = svc['title'][:80]
        desc_trimmed = svc['desc'][:80] + "..." if len(svc['desc']) > 80 else svc['desc']

        element = {
            "title": title_trimmed,
            "description": f"Цена: {svc['price_text']}\n{desc_trimmed}",
            "action": {"type": "open_photo"},
            "buttons": [
                {
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "buy", "type": "tariff", "key": svc['key']}),
                        "label": "КУПИТЬ"
                    },
                    "color": "positive"
                }
            ]
        }

        if att:
            photo_id = att.replace("photo", "")
            if "_" in photo_id:
                element["photo_id"] = photo_id

        elements.append(element)

    template = {
        "type": "carousel",
        "elements": elements
    }

    template_json = json.dumps(template, ensure_ascii=False)
    msg_text = "🛰 ТАРИФЫ 🛰\nВыберите тариф и нажмите 'КУПИТЬ'."

    try:
        await bot.api.messages.send(peer_id=peer_id, message=msg_text, template=template_json, random_id=0)
    except Exception as e:
        logger.exception(f"Error sending tariff carousel: {e}")
        try:
            await bot.api.messages.send(peer_id=peer_id, message=msg_text, random_id=0)
        except Exception as e:
            logger.exception("Ignored Exception")
