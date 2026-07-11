import asyncio
import json
import random

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
from modules.utils import (
    get_fsm_step,
    upload_local_photo,
    ghost_edit,
    get_last_bot_msg,
    set_last_bot_msg,
    delete_bot_message,
    extract_msg_id
)

labeler = BotLabeler()


async def _send_catalog_page(
    vk_id: int,
    peer_id: int,
    items: list[dict],
    idx: int,
    edit_msg_id: int | None,
    header_text: str,
    item_type: str, # "service" or "tariff"
    filter_val: str = None,
    fallback_att: str = None
):
    total_items = len(items)
    if not items:
        try:
            await bot.api.messages.send(peer_id=peer_id, message="Раздел пуст.", random_id=random.getrandbits(63))
        except Exception:
            pass
        return

    if total_items > 0:
        idx = idx % total_items

    item = items[idx]
    att = None
    if item.get("image_name"):
        try:
            att = await upload_local_photo(bot.api, item["image_name"], peer_id=vk_id)
        except Exception as e:
            logger.error(f"Failed to upload photo {item['image_name']}: {str(e)}")

    if not att:
        att = fallback_att

    button_cmd = "buy" if item["key"] != "card_of_day" else "card_of_day"
    button_label = "КУПИТЬ" if item["key"] != "card_of_day" else "ПОЛУЧИТЬ"

    from modules.keyboards import get_catalog_inline_keyboard
    user = await get_user(vk_id)
    kb_json = get_catalog_inline_keyboard(
        idx=idx,
        total_items=total_items,
        item_type=item_type,
        button_label=button_label,
        button_cmd=button_cmd,
        item_key=item["key"],
        filter_val=filter_val,
        user=user
    )

    full_text = f"{header_text}\n\n📦 {item['title']}\n📜 {item['desc']}\n\nПозиция: {idx + 1} из {total_items}"

    await ghost_edit(
        bot.api,
        peer_id,
        full_text,
        conversation_message_id=edit_msg_id,
        attachment=att,
        keyboard=kb_json
    )


async def _ensure_user_state(vk_id: int, peer_id: int) -> bool:
    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        try:
            from modules.bot_init import bot
            await bot.api.messages.send(peer_id=peer_id, message="ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.", random_id=random.getrandbits(63))
        except Exception as e:
            logger.error(f"Ignored Exception: {str(e)}")
        return False
    return True

async def show_services(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None, filter_val: str = None, is_catalog: bool = False, target_key: str = None):
    """Главный экран Услуг с пагинацией и разделением по Кабинетам"""
    if not await _ensure_user_state(vk_id, peer_id):
        return

    # Если мы зашли в раздел услуг, но не выбрали конкретный кабинет/услугу
    if not is_catalog and not filter_val and not target_key:
        from modules.keyboards import services_menu_kb
        text = "🔮 ВИТРИНА УСЛУГ И ТАЙНЫХ ЗНАНИЙ\n\nДобро пожаловать в единую обитель откровений Анти-Таро. Здесь все наши услуги разложены по тематическим Кабинетам для удобства вашего духовного поиска."
        header_att = await upload_local_photo(bot.api, "uslugi/main_menu.jpeg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, keyboard=services_menu_kb(), attachment=header_att, conversation_message_id=edit_msg_id)
        return

    header_att = await upload_local_photo(bot.api, "uslugi/services.jpeg", peer_id=vk_id)

    services = [
        # --- BIOMETRICS ---
        {
            "key": "oculomancy",
            "title": "👁 Окуломантия: Зеркало души",
            "desc": "1200 Энергии. Загрузи крупное фото своего глаза. ИИ считывает оттенок, узоры радужки и форму разреза, выдавая глубокий психологический портрет, скрытые таланты и «уязвимости» твоей души.",
            "image_name": "uslugi/services.jpeg",
            "category": "biometrics"
        },
        {
            "key": "palmistry",
            "title": "✋ Хиромантия",
            "desc": "1200 Энергии (Бесплатно по VIP). Чтение судьбы по ладоням. Узнай свой врожденный потенциал, сильные стороны и текущую реализацию через глубокий анализ линий твоей руки по фото.",
            "image_name": "uslugi/hiro.jpeg",
            "category": "biometrics"
        },

        # --- ARTIFACTS ---
        {
            "key": "sigil",
            "title": "🎨 Сигил-Мастер: Генератор знаков",
            "desc": "1000 Энергии. Трансформируй свое сокровенное желание в уникальный графический символ — сигил по древним канонам практической магии. Сохрани его на экран для активации потоков удачи!",
            "image_name": "uslugi/services.jpeg",
            "category": "artifacts"
        },
        {
            "key": "alchemist",
            "title": "🧪 Цифровой Алхимик",
            "desc": "700 Энергии. Расчет твоего ведущего первоэлемента (Философская Ртуть, Сера или Соль) на основе точной даты рождения и составление персональной формулы душевного и энергетического баланса.",
            "image_name": "uslugi/services.jpeg",
            "category": "artifacts"
        },

        # --- DESTINY ---
        {
            "key": "karma",
            "title": "🧬 Кармический навигатор",
            "desc": "900 Энергии. Раскрой тайны своего предыдущего воплощения, невыполненные кармические долги и получи индивидуальный ключ к решению текущих жизненных трудностей через интерактивный тест.",
            "image_name": "uslugi/services.jpeg",
            "category": "destiny"
        },
        {
            "key": "totem",
            "title": "🐾 Тотемный проводник",
            "desc": "900 Энергии. Определение твоего священного животного силы через шаманский интерактивный квиз, получение сакрального послания от тотема и ценные советы по использованию его энергии.",
            "image_name": "uslugi/services.jpeg",
            "category": "destiny"
        },
        {
            "key": "astro_geo",
            "title": "🗺 Астро-картография",
            "desc": "900 Энергии. Анализ влияния планетарных линий на земную географию. Введи город или страну и узнай, какие энергии принесет тебе это место: богатство, любовь, испытания или гармонию.",
            "image_name": "uslugi/services.jpeg",
            "category": "destiny"
        },

        # --- ORACLES ---
        {
            "key": "egyptian_oracle",
            "title": "🏺 Древний Египетский Оракул",
            "desc": "700 Энергии. Свитки Судьбы из Книги Тота. Три священных пророчества древних богов Гелиополя, раскрывающие векторы твоего триумфа и предупреждающие о скрытых преградах.",
            "image_name": "uslugi/services.jpeg",
            "category": "oracles"
        },
        {
            "key": "shadow_oracle",
            "title": "👤 Теневой Оракул Лилит",
            "desc": "700 Энергии. Встреча со своими истинными, подавленными желаниями и теневой стороной личности по концепции Карла Юнга. Трансформируй своих внутренних демонов в огромный ресурс силы.",
            "image_name": "uslugi/services.jpeg",
            "category": "oracles"
        },
        {
            "key": "chrono",
            "title": "⏱ Хроно-прогноз",
            "desc": "700 Энергии. Расчет личных 'ведьминских часов' и пиков мистической и интуитивной активности на месяц вперед. Идеальный эзотерический тайм-менеджмент для планирования важных дел.",
            "image_name": "uslugi/services.jpeg",
            "category": "oracles"
        },
        {
            "key": "charoslov",
            "title": "🌾 Славянский Чарослов",
            "desc": "600 Энергии. Старообрядческие заговоры, обереги и индивидуальные ведовские практики защиты, привлечения блага и гармонизации пространства на сегодняшний день.",
            "image_name": "uslugi/services.jpeg",
            "category": "oracles"
        },
        {
            "key": "oracle",
            "title": "🔮 Спроси у звезд",
            "desc": "500 Энергии. Прямой и точный ответ на твой самый важный, волнующий вопрос от звездного Оракула. Напиши свой вопрос и звезды дадут тебе ясный ориентир.",
            "image_name": "uslugi/QUEST.jpeg",
            "category": "oracles"
        },
        {
            "key": "antitaro",
            "title": "🃏 Анти-Таро",
            "desc": "500 Энергии. Честный, трезвый взгляд на любую запутанную ситуацию без иллюзий, приукрашиваний и розовых очков. Получи прямой совет, как действовать прямо сейчас.",
            "image_name": "uslugi/ANTITARO.jpeg",
            "category": "oracles"
        },
        {
            "key": "micro_insight",
            "title": "✨ Микро-инсайт",
            "desc": "100 Энергии. Быстрый и точный совет от твоего персонального Проводника на ближайший час. Идеально для мгновенной сонастройки перед принятием решения.",
            "image_name": "uslugi/QUEST.jpeg",
            "category": "oracles"
        },
        {
            "key": "card_of_day",
            "title": "🎴 Карта дня",
            "desc": "Бесплатно. Твое личное напутствие на сегодня для сонастройки с матрицей.",
            "image_name": "uslugi/cardofday.jpeg",
            "category": "oracles"
        },

        # --- ENERGY & SYNC ---
        {
            "key": "synastry",
            "title": "❤️ Совместимость",
            "desc": "1500 Энергии. Глубокий анализ ваших отношений по звездам. Узнайте, созданы ли вы друг для друга, какие кармические задачи стоят перед вашей парой, а также раскройте потенциал вашей сексуальной и эмоциональной связи.",
            "image_name": "uslugi/SINISTRY.jpeg",
            "category": "energy_sync"
        },
        {
            "key": "destiny_card",
            "title": "⭐ Карта Судьбы",
            "desc": "1500 Энергии. Твой главный жизненный путь на всю жизнь. Самый важный разбор в твоем профиле, определяющий твой архетип, предназначение и кармические задачи.",
            "image_name": "uslugi/WAYLIFE.jpeg",
            "category": "energy_sync"
        },
        {
            "key": "dream",
            "title": "🌙 Сонник",
            "desc": "1000 Энергии (Бесплатно по VIP). Толкование твоих снов через призму архетипов и символов. Узнай, что хочет сказать твое подсознание, и расшифруй тайные знаки ночи.",
            "image_name": "uslugi/dream.jpeg",
            "category": "energy_sync"
        },
        {
            "key": "sex",
            "title": "🔥 Сексуальность",
            "desc": "1000 Энергии. Погружение в мир твоих истинных чувств, желаний и сексуального потенциала через анализ твоих планет страсти.",
            "image_name": "uslugi/sex.jpeg",
            "category": "energy_sync"
        },
        {
            "key": "money",
            "title": "💰 Денежный поток",
            "desc": "900 Энергии. Раскрой свой путь к финансовой свободе, сильные и слабые стороны в материальном мире и способы привлечения изобилия.",
            "image_name": "uslugi/Money.jpeg",
            "category": "energy_sync"
        },
        {
            "key": "shadow",
            "title": "👹 Ваши демоны / Тень",
            "desc": "700 Энергии. Встреча с тем, что скрыто в глубине тебя. Осознание и принятие своей теневой стороны для обретения целостности.",
            "image_name": "uslugi/DEMONS.jpeg",
            "category": "energy_sync"
        },
        {
            "key": "final",
            "title": "🧭 Ваш путь в жизни",
            "desc": "1200 Энергии. Главный вектор твоей жизни, долгосрочные цели и предназначение души в этом воплощении.",
            "image_name": "uslugi/WAYLIFE.jpeg",
            "category": "energy_sync"
        },
        {
            "key": "all",
            "title": "👑 VIP-Пакет",
            "desc": "3000 Энергии. Полный разбор Матрицы Судьбы: Совместимость, Карта Судьбы и все 4 тайных раздела натальной карты (Сексуальность, Денежный поток, Тень, Ваш путь). Вечный доступ!",
            "image_name": "uslugi/VIP.jpeg",
            "category": "energy_sync"
        },
    ]

    # Если передан target_key, определим его категорию для фиксации навигации в кабинете
    if target_key and not filter_val:
        for s in services:
            if s["key"] == target_key:
                filter_val = s.get("category")
                break

    if filter_val:
        services = [s for s in services if s.get("category") == filter_val]

    if target_key:
        for i, s in enumerate(services):
            if s["key"] == target_key:
                idx = i
                break

    # Умные рекомендации на основе тегов
    user = await get_user(vk_id)
    if user and not filter_val:
        from modules.utils.logic import get_safe_tags
        tags = get_safe_tags(user)
        if tags:
            tags_lower = [t.lower() for t in tags]
            # Если в тегах есть 'отношения' или 'любовь', поднимаем синастрию
            if any(x in " ".join(tags_lower) for x in ["люб", "отнош", "секс", "партнер"]):
                rel_keys = ["synastry", "sex"]
                rel_items = [s for s in services if s["key"] in rel_keys]
                other_items = [s for s in services if s["key"] not in rel_keys]
                services = rel_items + other_items
            # Если есть 'деньги' или 'карьера'
            elif any(x in " ".join(tags_lower) for x in ["ден", "фин", "раб", "бизнес", "карьер"]):
                rel_keys = ["money"]
                rel_items = [s for s in services if s["key"] in rel_keys]
                other_items = [s for s in services if s["key"] not in rel_keys]
                services = rel_items + other_items

    # Текстовые заголовки Кабинетов
    cat_headers = {
        "biometrics": "👁 КАБИНЕТ БИОМЕТРИИ И ФОТО 👁",
        "artifacts": "🎨 САД САКРАЛЬНЫХ АРТЕФАКТОВ 🎨",
        "destiny": "🧭 ПРОЕКЦИИ СУДЬБЫ 🧭",
        "oracles": "🏺 ДРЕВНИЕ ОРАКУЛЫ 🏺",
        "energy_sync": "❤️ КАБИНЕТ ЭНЕРГИИ И СЛИЯНИЯ ❤️"
    }

    header = cat_headers.get(filter_val, "✨ КАТАЛОГ УСЛУГ ✨")

    await _send_catalog_page(
        vk_id=vk_id,
        peer_id=peer_id,
        items=services,
        idx=idx,
        edit_msg_id=edit_msg_id,
        header_text=f"{header}\nВыбери то, что откликается твоему сердцу.",
        item_type="service",
        filter_val=filter_val,
        fallback_att=header_att
    )

async def is_waiting_synastry_name(message: Message) -> bool:
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар"]: return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_name"

@labeler.message(func=is_waiting_synastry_name)
async def process_synastry_name(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

        partner_name = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_date", "partner_name": partner_name}))
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message=f"Имя {partner_name} согрело колоду ✨ Теперь введи, пожалуйста, дату рождения партнера (например, 15.04.1990):",
            random_id=random.getrandbits(63)
        )
        msg_id = extract_msg_id(resp)
        await set_last_bot_msg(vk_id, msg_id)
    finally:
        await release_lock(vk_id)

async def is_waiting_synastry_date(message: Message) -> bool:
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар"]: return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_date"

@labeler.message(func=is_waiting_synastry_date)
async def process_synastry_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

        partner_date = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")

        await set_user_state(vk_id, json.dumps({
            "step": "waiting_synastry_time",
            "partner_name": partner_name,
            "partner_date": partner_date
        }))
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message=f"Дата {partner_date} принята. Теперь напиши время рождения партнера (например, 14:30 или 'не знаю'):",
            random_id=random.getrandbits(63)
        )
        msg_id = extract_msg_id(resp)
        await set_last_bot_msg(vk_id, msg_id)
    finally:
        await release_lock(vk_id)

async def is_waiting_synastry_time(message: Message) -> bool:
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар"]: return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_time"

@labeler.message(func=is_waiting_synastry_time)
async def process_synastry_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

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
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message=f"Время {partner_time} принято. И последнее — в каком городе родился партнер (например, Москва или 'не знаю')?",
            random_id=random.getrandbits(63)
        )
        msg_id = extract_msg_id(resp)
        await set_last_bot_msg(vk_id, msg_id)
    finally:
        await release_lock(vk_id)

async def is_waiting_dream_text(message: Message) -> bool:
    # Игнорируем команды и меню
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар", "тайные искусства"]: return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_dream_text"

@labeler.message(func=is_waiting_dream_text)
async def process_dream_text(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        dream_text = message.text.strip() if message.text else ""
        if len(dream_text) < 15:
            await message.answer("Пожалуйста, опиши свой сон подробнее (хотя бы пару предложений), чтобы я смог провести глубокий анализ.")
            return

        await set_user_state(vk_id, "")

        # Сохраняем текст сна в редис для генерации
        from cache import redis_client
        await redis_client.set(f"dream_text:{vk_id}", dream_text, ex=600)

        # Сообщаем о начале анализа
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message="✦ СОН ПРИНЯТ. ПОГРУЖАЮСЬ В ТВОЕ ПОДСОЗНАНИЕ...",
            random_id=random.getrandbits(63)
        )
        conv_id = extract_msg_id(resp)

        # Запускаем генерацию
        from modules.payments.logic import execute_generation
        asyncio.create_task(execute_generation(
            vk_id=vk_id,
            peer_id=message.peer_id,
            target_section="dream",
            partner_name="",
            partner_date="",
            conversation_message_id=conv_id
        ))
    finally:
        await release_lock(vk_id)


async def is_waiting_palmistry_photos(message: Message) -> bool:
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_palmistry_photos"

@labeler.message(func=is_waiting_palmistry_photos)
async def process_palmistry_photos(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        photos = []
        if message.attachments:
            for att in message.attachments:
                if att.photo:
                    # Берем максимальный размер фото
                    sizes = att.photo.sizes
                    max_size = max(sizes, key=lambda s: s.width * s.height)
                    photos.append(max_size.url)

        if not photos:
            # Если это не фото, а другой тип или просто текст
            if message.text and message.text.lower() in ["начать", "главное меню", "услуги"]:
                await set_user_state(vk_id, "")
                await show_services(vk_id, message.peer_id, 0)
                return
            await message.answer("Пожалуйста, пришлите именно фотографии ваших ладоней для анализа.")
            return

        state_dict = await get_fsm_step(vk_id)
        collected_photos = state_dict.get("photos", [])
        # Добавляем только уникальные URL, чтобы избежать дублей
        for p_url in photos:
            if p_url not in collected_photos:
                collected_photos.append(p_url)

        if len(collected_photos) < 2:
            await set_user_state(vk_id, json.dumps({
                "step": "waiting_palmistry_photos",
                "photos": collected_photos
            }))
            await message.answer("Отлично, я вижу первое фото. Пришлите, пожалуйста, вторую ладонь.")
        else:
            # Берем первые два фото
            final_photos = collected_photos[:2]
            await set_user_state(vk_id, "")

            # Пока сохраним в редис по ключу palmistry_photos:{vk_id}
            from cache import redis_client
            await redis_client.set(f"palmistry_photos:{vk_id}", json.dumps(final_photos), ex=600)

            # Сообщаем о начале анализа
            resp = await bot.api.messages.send(
                peer_id=message.peer_id,
                message="✦ ФОТО ПОЛУЧЕНЫ. ИНИЦИИРУЮ ГЛУБОКИЙ АНАЛИЗ ЛАДОНЕЙ...",
                random_id=random.getrandbits(63)
            )
            conv_id = extract_msg_id(resp)

            # Запускаем генерацию
            from modules.payments.logic import execute_generation
            asyncio.create_task(execute_generation(
                vk_id=vk_id,
                peer_id=message.peer_id,
                target_section="palmistry",
                partner_name="",
                partner_date="",
                conversation_message_id=conv_id
            ))

    finally:
        await release_lock(vk_id)

async def is_waiting_synastry_city(message: Message) -> bool:
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар"]: return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_city"

@labeler.message(func=is_waiting_synastry_city)
async def process_synastry_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

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
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message="✨ ШАГ 2 ИЗ 3: НАСТРОЙКА ✨\nПрикоснись к колоде, чтобы настроиться на вашу связь.",
            keyboard=kb.get_json(),
            random_id=random.getrandbits(63)
        )
        msg_id = extract_msg_id(resp)
        await set_last_bot_msg(vk_id, msg_id)
    except Exception as e:
        logger.error(f"Ошибка в процессе синастрии: {str(e)}")
    finally:
        await release_lock(vk_id)


async def show_tariffs(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None):

    if not await _ensure_user_state(vk_id, peer_id):
        return

    user = await get_user(vk_id)
    balance = int(user.get("balance", 0) or 0)

    header_att = await upload_local_photo(bot.api, "uslugi/tariffs.jpeg", peer_id=vk_id)

    tariffs = [
        {"key": "tariff_1", "title": "🛰 Спутник 7 дней", "desc": "990 Энергии. Твое ежедневное напутствие на неделю.", "image_name": "uslugi/7day.jpeg"},
        {"key": "tariff_2", "title": "🔮 Оракул 30 дней", "desc": "2900 Энергии. Выгода 400% — Хит! Целый месяц под защитой звезд.", "image_name": "uslugi/30day.jpeg"},
        {"key": "tariff_vip", "title": "👑 VIP-Адепт", "desc": "5900 Энергии. Полный безлимит на 30 дней на ВСЁ, включая Хиромантию и Сонник + вечный доступ к натальной карте.", "image_name": "uslugi/VIPTOP.jpeg"},
        {"key": "topup_5000", "title": "✨ Пакет 5000 Энергии", "desc": "400 руб. Выгодный старт для глубокого погружения.", "image_name": "uslugi/tariffs.jpeg"},
        {"key": "topup_10000", "title": "✨ Пакет 10000 Энергии", "desc": "750 руб. Оптимальный выбор для истинных искателей.", "image_name": "uslugi/tariffs.jpeg"},
        {"key": "topup_50000", "title": "👑 VIP Пакет 50000 Энергии", "desc": "3500 руб. Максимальная выгода и безграничные возможности.", "image_name": "uslugi/VIP.jpeg"},
    ]

    await _send_catalog_page(
        vk_id=vk_id,
        peer_id=peer_id,
        items=tariffs,
        idx=idx,
        edit_msg_id=edit_msg_id,
        header_text=f"✨ ДАРЫ И ЭНЕРГИЯ ✨\nТвой баланс: {balance} ✨\n\nВыбери подходящий объем энергии для своего пути.",
        item_type="tariff",
        fallback_att=header_att
    )


# --- ОБЩИЕ КОМАНДНЫЕ ОБРАБОТЧИКИ (в конце для низкого приоритета) ---

@labeler.message(func=lambda m: m.text and m.text.lower() in ['🔮 глубокие разборы', 'глубокие разборы', '✦ услуги', 'услуги', '✦ услуги 🛒'] and not m.attachments)
async def show_services_handler(message: Message):
    logger.info(f"show_services_handler triggered by from_id={message.from_id}")
    last_mid = await get_last_bot_msg(message.from_id)
    if last_mid:
        await delete_bot_message(bot.api, message.peer_id, mid=last_mid)
    await show_services(message.from_id, message.peer_id, 0)


@labeler.message(func=lambda m: m.text and m.text.lower() in ['🛰 тарифы', '💳 пополнить'] and not m.attachments)
async def show_tariffs_handler(message: Message):
    last_mid = await get_last_bot_msg(message.from_id)
    if last_mid:
        await delete_bot_message(bot.api, message.peer_id, mid=last_mid)
    await show_tariffs(message.from_id, message.peer_id, 0)
