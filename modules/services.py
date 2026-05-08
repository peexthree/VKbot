<<<<<<< Updated upstream
from modules.bot_init import bot
import json
from cache import acquire_lock, release_lock
from modules.states import MyStates

from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from database import get_user, set_user_state
from modules.utils import get_fsm_step, upload_local_photo
=======
import json

>>>>>>> Stashed changes
from loguru import logger
from vkbottle import (
    Callback,
    Keyboard,
    KeyboardButtonColor,
)
from vkbottle.bot import BotLabeler, Message

from cache import acquire_lock, release_lock
from database import get_user, set_user_state
from modules.bot_init import bot
from modules.states import MyStates
from modules.utils import (
    get_fsm_step,
    upload_local_photo,
)

labeler = BotLabeler()

@labeler.message(text=["🔮 ГЛУБОКИЕ РАЗБОРЫ", "ГЛУБОКИЕ РАЗБОРЫ", "✦ Услуги", "Услуги", "✦ УСЛУГИ 🛒"])
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
            logger.error(f"Ignored Exception: {str(e)}")
        return

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

    elements = []
    for svc in services:
        att = await upload_local_photo(bot.api, svc['image_name'], peer_id=vk_id) if svc['image_name'] else None

        # Trim description to fit VK Carousel limits (approx 80 chars for title, 80 chars for description in carousel)
        # However, for carousel description max length is 80, title is 80.
        title_trimmed = svc['title'][:80]
        desc_trimmed = svc['desc'][:80] + "..." if len(svc['desc']) > 80 else svc['desc']

        button_cmd = "buy" if svc['key'] != "card_of_day" else "card_of_day"
        button_label = "КУПИТЬ" if svc['key'] != "card_of_day" else "ПОЛУЧИТЬ"

        # We need a valid action URL or action for the element itself. Usually "open_photo" or "open_link"
        element = {
            "title": title_trimmed,
            "description": desc_trimmed,
            "action": {"type": "open_photo"},
            "buttons": [
                {
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": button_cmd, "type": "service", "key": svc['key']}),
                        "label": button_label
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
        logger.error(f"Error sending service carousel: {str(e)}")
        try:
            await bot.api.messages.send(peer_id=peer_id, message=msg_text, random_id=0)
        except Exception as e:
            logger.error(f"Ignored Exception: {str(e)}")


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
            logger.error(f"Ignored Exception: {str(e)}")
        return

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

    elements = []
    for svc in tariffs:
        att = await upload_local_photo(bot.api, svc['image_name'], peer_id=vk_id) if svc['image_name'] else None

        title_trimmed = svc['title'][:80]
        desc_trimmed = svc['desc'][:80] + "..." if len(svc['desc']) > 80 else svc['desc']

        element = {
            "title": title_trimmed,
            "description": desc_trimmed,
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
        logger.error(f"Error sending tariff carousel: {str(e)}")
        try:
            await bot.api.messages.send(peer_id=peer_id, message=msg_text, random_id=0)
        except Exception as e:
            logger.error(f"Ignored Exception: {str(e)}")
