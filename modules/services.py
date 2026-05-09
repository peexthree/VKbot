from __future__ import annotations
import json
from typing import List, Dict, Any

from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

from cache import acquire_lock, release_lock
from database import get_user, set_user_state
from modules.bot_init import bot
from modules.states import MyStates
from modules.utils import (
    get_fsm_step,
    upload_local_photo,
    start_dynamic_typing,
)

labeler = BotLabeler()

# ====================== КЭШ ФОТО (чтобы не грузить каждый раз) ======================
_photo_cache: Dict[str, str] = {}


async def get_photo_attachment(image_name: str, peer_id: int) -> str | None:
    if image_name in _photo_cache:
        return _photo_cache[image_name]
    try:
        att = await upload_local_photo(bot.api, image_name, peer_id=peer_id)
        _photo_cache[image_name] = att
        return att
    except Exception as e:
        logger.error(f"Не удалось загрузить фото {image_name}: {e}")
        return None


# ====================== УНИВЕРСАЛЬНАЯ КАРУСЕЛЬ (AGENTS.md compliant) ======================
async def send_carousel(
    vk_id: int,
    peer_id: int,
    items: List[Dict[str, Any]],
    title: str,
    edit_msg_id: int | None = None,
    event_id: str | None = None,
    item_type: str = "service",
):
    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        msg = "ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'."
        if edit_msg_id:
            await bot.api.messages.edit(peer_id=peer_id, message_id=edit_msg_id, message=msg)
        else:
            await bot.api.messages.send(peer_id=peer_id, message=msg, random_id=0)
        return

    if event_id:
        try:
            await bot.api.messages.send_message_event_answer(
                event_id=event_id, user_id=vk_id, peer_id=peer_id
            )
        except Exception as e:
            logger.error(f"Ignored event answer error: {e}")

    # ЖИВОЙ РИТУАЛ (AGENTS.md)
    await start_dynamic_typing(bot.api, peer_id, typing_time=1200)
    if edit_msg_id:
        try:
            await bot.api.messages.edit(
                peer_id=peer_id,
                message_id=edit_msg_id,
                message="Открываю гримуар...",
                keyboard=Keyboard(inline=True).get_json()
            )
        except Exception:
            pass

    elements = []
    for item in items:
        att = await get_photo_attachment(item["image_name"], peer_id) if item.get("image_name") else None

        title_trimmed = item["title"][:80]
        desc_trimmed = item["desc"][:80] + "..." if len(item["desc"]) > 80 else item["desc"]

        button_cmd = "buy" if item["key"] != "card_of_day" else "card_of_day"
        button_label = "КУПИТЬ" if item["key"] != "card_of_day" else "ПОЛУЧИТЬ"

        element: Dict[str, Any] = {
            "title": title_trimmed,
            "description": desc_trimmed,
            "action": {"type": "open_photo"},
            "buttons": [
                {
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": button_cmd, "type": item_type, "key": item["key"]}),
                        "label": button_label,
                    },
                    "color": "positive",
                }
            ],
        }

        if att:
            photo_id = att.replace("photo", "")
            if "_" in photo_id:
                element["photo_id"] = photo_id

        elements.append(element)

    template = {"type": "carousel", "elements": elements}
    template_json = json.dumps(template, ensure_ascii=False)

    msg_text = f"{title}\nВыберите и нажмите кнопку ниже."

    try:
        if edit_msg_id:
            await bot.api.messages.edit(
                peer_id=peer_id, message_id=edit_msg_id, message=msg_text, template=template_json
            )
        else:
            await bot.api.messages.send(peer_id=peer_id, message=msg_text, template=template_json, random_id=0)
    except Exception as e:
        logger.error(f"Error sending carousel: {e}")
        fallback_msg = f"{title}\nВыберите услугу."
        if edit_msg_id:
            await bot.api.messages.edit(peer_id=peer_id, message_id=edit_msg_id, message=fallback_msg)
        else:
            await bot.api.messages.send(peer_id=peer_id, message=fallback_msg, random_id=0)


# ====================== УСЛУГИ ======================
@labeler.message(text=["🔮 ГЛУБОКИЕ РАЗБОРЫ", "ГЛУБОКИЕ РАЗБОРЫ", "✦ Услуги", "Услуги", "✦ УСЛУГИ 🛒"])
async def show_services_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        logger.info(f"show_services_handler triggered by from_id={vk_id}")

        services = [
            {
                "key": "sex",
                "title": "Твоя сексуальная энергия",
                "desc": "1000 Энергии. Раскроет матрицу страсти.\n\nДемо: В этом разборе мы изучим позицию Марса и Венеры, чтобы вскрыть твои истинные влечения.",
                "image_name": "uslugi/sex.jpg"
            },
            {
                "key": "money",
                "title": "Код твоего богатства",
                "desc": "900 Энергии. Пробьет финансовый потолок.\n\nДемо: Узнай, как положение Сатурна и 2-го дома блокируют или открывают твой денежный поток.",
                "image_name": "uslugi/Money.jpg"
            },
            {
                "key": "shadow",
                "title": "Твои скрытые грани",
                "desc": "700 Энергии. Раскроет подавленные эмоции.\n\nДемо: Лилит и 8-й дом покажут то, что ты боишься признать даже самому себе.",
                "image_name": "uslugi/DEMONS.jpg"
            },
            {
                "key": "final",
                "title": "Твой истинный путь",
                "desc": "1200 Энергии. Вектор развития.\n\nДемо: Северный узел укажет направление, в котором заложен твой максимальный потенциал.",
                "image_name": "uslugi/WAYLIFE.jpg"
            },
            {
                "key": "synastry",
                "title": "Тайна ваших отношений",
                "desc": "1500 Энергии. Жесткий разбор совместимости.\n\nДемо: Взаимодействие ваших натальных карт покажет, кармический ли это союз или временное испытание.",
                "image_name": "uslugi/SINISTRY.jpg"
            },
            {
                "key": "oracle",
                "title": "Вопрос судьбе (Оракул)",
                "desc": "500 Энергии. Ответ судьбы без воды.\n\nДемо: Задай свой самый сокровенный вопрос и получи трактовку 3-х карт Таро.",
                "image_name": "uslugi/QUEST.jpg"
            },
            {
                "key": "antitaro",
                "title": "Антитаро (Разрыв иллюзий)",
                "desc": "500 Энергии. Разбор иллюзий.\n\nДемо: Вскрываем ложь, которую ты себе рассказываешь, через темные арканы.",
                "image_name": "uslugi/ANTITARO.jpg"
            },
            {
                "key": "all",
                "title": "Золотой архив всех откровений",
                "desc": "3000 Энергии. Полный доступ ко всем тайнам твоей матрицы.",
                "image_name": "uslugi/VIP.jpg"
            },
            {
                "key": "card_of_day",
                "title": "Карта дня",
                "desc": "Бесплатно. Твоя персональная карта дня. Открой завесу тайн.",
                "image_name": "uslugi/cardofday.jpg"
            }
        ]

        await send_carousel(
            vk_id=vk_id,
            peer_id=message.peer_id,
            items=services,
            title="✦ ВИТРИНА УСЛУГ ✦",
            item_type="service",
        )
    finally:
        await release_lock(vk_id)


# ====================== ТАРИФЫ ======================
@labeler.message(text=["🛰 ТАРИФЫ"])
async def show_tariffs_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        tariffs = [
            {
                "key": "tariff_1",
                "title": "Спутник 7 дней",
                "desc": "990 Энергии. Ежедневные прогнозы и транзиты на 7 дней.",
                "image_name": "uslugi/7day.jpg"
            },
            {
                "key": "tariff_2",
                "title": "Оракул 30 дней",
                "desc": "2900 Энергии. Ежедневные прогнозы и транзиты на 30 дней.",
                "image_name": "uslugi/30day.jpg"
            },
            {
                "key": "tariff_vip",
                "title": "VIP Архив",
                "desc": "5900 Энергии. Золотой архив тайн + месяц транзитов.",
                "image_name": "uslugi/VIPTOP.jpg"
            }
        ]

        await send_carousel(
            vk_id=vk_id,
            peer_id=message.peer_id,
            items=tariffs,
            title="🛰 ТАРИФЫ 🛰",
            item_type="tariff",
        )
    finally:
        await release_lock(vk_id)


# ====================== СИНАСТРИЯ ======================
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
    try:
        partner_date = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")

        await set_user_state(vk_id, json.dumps({
            "step": "waiting_synastry_time",
            "partner_name": partner_name,
            "partner_date": partner_date
        }))
        await message.answer(f"Дата {partner_date} принята. Теперь введите ВРЕМЯ РОЖДЕНИЯ партнера (например, 14:30 или 'не знаю'):")
    finally:
        await release_lock(vk_id)


@labeler.message(state=MyStates.WAITING_SYNASTRY_TIME)
async def process_synastry_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        partner_time = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")
        partner_date = state_dict.get("partner_date", "")

        await set_user_state(vk_id, json.dumps({
            "step": "waiting_synastry_city",
            "partner_name": partner_name,
            "partner_date": partner_date,
            "partner_time": partner_time
        }))
        await message.answer(f"Время {partner_time} принято. Теперь введите ГОРОД РОЖДЕНИЯ партнера (например, Москва или 'не знаю'):")
    finally:
        await release_lock(vk_id)


@labeler.message(state=MyStates.WAITING_SYNASTRY_CITY)
async def process_synastry_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        partner_city = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")
        partner_date = state_dict.get("partner_date", "")
        partner_time = state_dict.get("partner_time", "")

        partner_full_info = f"{partner_date} {partner_time} {partner_city}"

        await set_user_state(vk_id, json.dumps({
            "step": "global_cut",
            "target_section": "synastry",
            "partner_name": partner_name,
            "partner_date": partner_full_info
        }))

        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
        await message.answer(
            "ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.",
            keyboard=kb.get_json()
        )
    except Exception as e:
        logger.error(f"Ошибка в процессе синастрии: {str(e)}")
    finally:
        await release_lock(vk_id)
