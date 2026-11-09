# modules/tarot/spreads_logic.py
"""Логика сакральных раскладов Таро проекта АНТИ-ТАР."""

import asyncio
import datetime
import json
import random
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback

from configs.tarot_spreads import TAROT_SPREADS
from database import get_user, update_user, set_user_state
from ai_service import generate_text
from modules.bot_init import bot
from modules.utils import (
    start_dynamic_typing,
    stop_dynamic_typing,
    upload_local_photo,
    ghost_edit,
    safe_edit,
    get_fsm_step,
    acquire_lock,
    release_lock,
)
from cache import (
    get_tarot_names,
    set_latest_reading,
    add_reading_to_history,
    get_readings_history,
)


async def initiate_spread_flow(vk_id: int, peer_id: int, spread_key: str, edit_msg_id: int = None):
    """Инициализация расклада после списания энергии: переход к соприкосновению."""
    spread = TAROT_SPREADS.get(spread_key)
    if not spread:
        logger.error(f"Spread {spread_key} not found in TAROT_SPREADS")
        return

    # Подготавливаем колоду
    pool = list(range(0, 78))
    random.shuffle(pool)

    cards_count = spread["cards_count"]
    # Ограничиваем пул для интерактива
    interactive_pool = pool[: min(12, max(cards_count + 4, 10))]

    state_dict = {
        "step": "spread_cut",
        "spread_key": spread_key,
        "pool": interactive_pool,
        "full_deck": pool,
        "drawn_cards": [],
    }
    await set_user_state(vk_id, json.dumps(state_dict))

    kb = Keyboard(inline=True)
    kb.add(
        Callback("✦ СНЯТЬ КОЛОДУ", payload={"cmd": "spread_cut", "key": spread_key}),
        color=KeyboardButtonColor.PRIMARY,
    )
    kb.row()
    kb.add(
        Callback("❌ ОТМЕНА", payload={"cmd": "secret_arts_cat", "cat": "tarot_spreads"}),
        color=KeyboardButtonColor.SECONDARY,
    )

    msg = (
        f"✨ РИТУАЛ РАСКЛАДА: {spread['title'].upper()} ✨\n\n"
        f"Позиций карт: {cards_count}\n"
        f"Прикоснись к колоде, чтобы передать ей вибрацию своего запроса и разделить энергетические потоки."
    )

    att = None
    if spread.get("image_name"):
        try:
            att = await upload_local_photo(bot.api, spread["image_name"], peer_id=vk_id)
        except Exception as e:
            logger.warning(f"Failed to upload spread image {spread['image_name']}: {e}")

    await ghost_edit(
        bot.api,
        peer_id,
        msg,
        keyboard=kb.get_json(),
        attachment=att,
        conversation_message_id=edit_msg_id,
    )


async def handle_spread_cut(vk_id: int, peer_id: int, spread_key: str, edit_msg_id: int = None):
    """Обработка снятия колоды: показ карт для выбора или авто-расклад для VIP."""
    state_dict = await get_fsm_step(vk_id)
    spread = TAROT_SPREADS.get(spread_key)
    if not state_dict or not spread:
        await safe_edit(
            peer_id=peer_id,
            conversation_message_id=edit_msg_id,
            message="Энергетическая нить прервана. Открой расклад заново через меню услуг.",
            keyboard=Keyboard(inline=True).add(Callback("🔮 В Меню", payload={"cmd": "services_menu"})).get_json(),
        )
        return

    cards_count = spread["cards_count"]
    pool = state_dict.get("pool") or list(range(0, 78))

    # Для больших VIP-раскладов (20 карт) кликать 20 раз неудобно: сдаем сакральным ритуалом
    if cards_count >= 15:
        full_deck = state_dict.get("full_deck") or list(range(0, 78))
        drawn = full_deck[:cards_count]
        await set_user_state(vk_id, "")

        await safe_edit(
            peer_id=peer_id,
            conversation_message_id=edit_msg_id,
            message=(
                f"✦ КОЛОДА СНЯТА ✦\n\n"
                f"Великий круг из {cards_count} священных Арканов развернут на звездном алтаре.\n"
                f"Вхожу в трансцендентный транс для чтения каждой позиции..."
            ),
            keyboard=Keyboard(inline=True).get_json(),
        )

        asyncio.create_task(
            execute_spread_reading(
                vk_id,
                peer_id,
                spread_key,
                drawn,
                conversation_message_id=edit_msg_id,
            )
        )
        return

    # Для раскладов до 10 карт — интерактивный выбор
    state_dict["step"] = "spread_draw"
    state_dict["drawn_cards"] = []
    await set_user_state(vk_id, json.dumps(state_dict))

    kb = Keyboard(inline=True)
    for i, cid in enumerate(pool):
        kb.add(Callback("🎴", payload={"spread_card": cid, "key": spread_key}))
        if (i + 1) % 4 == 0 and (i + 1) < len(pool):
            kb.row()

    await safe_edit(
        peer_id=peer_id,
        conversation_message_id=edit_msg_id,
        message=(
            f"✨ ВЫБОР АРКАНОВ: 0/{cards_count} ✨\n\n"
            f"Прислушайся к внутренней интуиции и выбери {cards_count} карт из разложенных:"
        ),
        keyboard=kb.get_json(),
    )


async def handle_spread_card_draw(vk_id: int, peer_id: int, card_id: int, spread_key: str, edit_msg_id: int = None):
    """Обработка клика по карте расклада."""
    state_dict = await get_fsm_step(vk_id)
    spread = TAROT_SPREADS.get(spread_key)
    if not state_dict or not spread or state_dict.get("step") != "spread_draw":
        await safe_edit(
            peer_id=peer_id,
            conversation_message_id=edit_msg_id,
            message="Колода рассыпалась. Начни расклад заново через витрину услуг.",
            keyboard=Keyboard(inline=True).add(Callback("🔮 В Меню", payload={"cmd": "services_menu"})).get_json(),
        )
        return

    drawn = state_dict.get("drawn_cards", [])
    pool = state_dict.get("pool", [])
    cards_count = spread["cards_count"]

    if card_id not in drawn:
        drawn.append(card_id)

    if len(drawn) < cards_count:
        state_dict["drawn_cards"] = drawn
        await set_user_state(vk_id, json.dumps(state_dict))

        remaining = [c for c in pool if c not in drawn]
        kb = Keyboard(inline=True)
        for i, cid in enumerate(remaining):
            kb.add(Callback("🎴", payload={"spread_card": cid, "key": spread_key}))
            if (i + 1) % 4 == 0 and (i + 1) < len(remaining):
                kb.row()

        await safe_edit(
            peer_id=peer_id,
            conversation_message_id=edit_msg_id,
            message=f"✨ ВЫБОР АРКАНОВ: {len(drawn)}/{cards_count} ✨\n\nВыбери еще {cards_count - len(drawn)} карт:",
            keyboard=kb.get_json(),
        )
    else:
        # Все карты выбраны!
        await set_user_state(vk_id, "")
        await safe_edit(
            peer_id=peer_id,
            conversation_message_id=edit_msg_id,
            message=f"✦ ВСЕ {cards_count} КАРТ СОБРАНЫ ✦\n\nПриступаю к расшифровке тайных резонансов...",
            keyboard=Keyboard(inline=True).get_json(),
        )

        asyncio.create_task(
            execute_spread_reading(
                vk_id,
                peer_id,
                spread_key,
                drawn,
                conversation_message_id=edit_msg_id,
            )
        )


async def execute_spread_reading(
    vk_id: int,
    peer_id: int,
    spread_key: str,
    card_ids: list[int],
    conversation_message_id: int = None,
):
    """Генерация глубокого разбора расклада Таро с учетом активного скина и позиций."""
    lock_key = f"execute_spread:{vk_id}"
    if not await acquire_lock(lock_key, ttl=300):
        return
    try:
        spread = TAROT_SPREADS.get(spread_key)
        if not spread:
            return

        user = await get_user(vk_id)
        if not user:
            return

        await start_dynamic_typing(bot.api, peer_id)

        tarot_names = await get_tarot_names()
        positions = spread["positions"]

        # Собираем текстовое описание выпавших карт по позициям
        cards_mapping = []
        unlocked = user.get("unlocked_cards", {}) or {}
        if not isinstance(unlocked, dict):
            unlocked = {}

        for idx, cid in enumerate(card_ids):
            card_name = tarot_names.get(str(cid), f"Аркан {cid}")
            pos_title = positions[idx] if idx < len(positions) else f"Позиция {idx + 1}"
            cards_mapping.append(f"Позиция {idx + 1} («{pos_title}»): Карта «{card_name}»")
            if str(cid) not in unlocked:
                unlocked[str(cid)] = f"{card_name} (Расклад: {spread['title']})"

        # Обновляем открытые карты пользователя
        await update_user(
            vk_id,
            {
                "unlocked_cards": unlocked,
                "total_cards_received": user.get("total_cards_received", 0) + len(card_ids),
            },
        )

        # Определение гендера и контекста
        p = user.get("purchased_sections", {}) or {}
        sex_val = p.get("sex_val", 0)
        if sex_val == 1:
            gender_instruction = "ПОЛЬЗОВАТЕЛЬ - ЖЕНЩИНА. ОБРАЩАЙСЯ К НЕЙ В ЖЕНСКОМ РОДЕ."
        elif sex_val == 2:
            gender_instruction = "ПОЛЬЗОВАТЕЛЬ - МУЖЧИНА. ОБРАЩАЙСЯ К НЕМУ В МУЖСКОМ РОДЕ."
        else:
            gender_instruction = "ОБРАЩАЙСЯ К ПОЛЬЗОВАТЕЛЮ НЕЙТРАЛЬНО, БЕЗ УКАЗАНИЯ ПОЛА."

        from cache import get_core_profile
        from modules.utils.logic import get_safe_tags

        core = await get_core_profile(vk_id)
        tags = get_safe_tags(user)
        active_skin = user.get("active_skin", "olesya")

        prompt = (
            f"{gender_instruction}\n"
            f"{'Прошлый анализ души: ' + core if core else ''}\n"
            f"{'Фокус судьбы: [' + ', '.join(tags) + ']' if tags else ''}\n\n"
            f"ТЫ ПРОВОДИШЬ ПРОФЕССИОНАЛЬНЫЙ ЭЗОТЕРИЧЕСКИЙ РАСКЛАД ТАРО: «{spread['title'].upper()}».\n"
            f"ОПИСАНИЕ СУТИ РАСКЛАДА: {spread['desc']}\n\n"
            f"ВЫПАВШИЕ АРКАНЫ ПО ПОЗИЦИЯМ:\n"
            + "\n".join(cards_mapping)
            + "\n\n"
            f"ЖЕСТКИЕ ТРЕБОВАНИЯ К СТРУКТУРЕ ОТВЕТА:\n"
            f"1. Для КАЖДОЙ позиции напиши четкий заголовок с номером и вопросом, укажи выпавшую карту.\n"
            f"2. Дай глубокий, психологически точный и образный разбор каждой позиции (по 2-4 емких предложения на позицию без воды).\n"
            f"3. В конце сделай общий СИНТЕЗ КАРТ: главный сакральный совет, предостережение и вектор исхода ситуации.\n"
            f"4. Твой тон: полностью отыгрывай архетип своего персонажа ({active_skin}). Держи атмосферу тайны, эмпатии и мудрости."
        )

        res_text = await generate_text(prompt, skin=active_skin, is_background=False)
        if not res_text or res_text == "ERROR_RPM_LIMIT":
            msg = "Космические потоки перегружены. Твой расклад зафиксирован — попробуй получить ответ через минуту ✨"
            await stop_dynamic_typing(peer_id)
            if conversation_message_id:
                await safe_edit(peer_id=peer_id, conversation_message_id=conversation_message_id, message=msg)
            else:
                await bot.api.messages.send(peer_id=peer_id, message=msg, random_id=random.getrandbits(63))
            return

        # Сохраняем результат в Гримуар и последний разбор
        reading_payload_data = {
            "title": spread["title"],
            "section": spread_key,
            "cards": [str(c) for c in card_ids],
            "date": datetime.datetime.now().strftime("%d.%m.%Y"),
            "text": res_text,
        }
        await set_latest_reading(
            vk_id,
            res_text,
            data=reading_payload_data,
        )
        await add_reading_to_history(
            vk_id,
            {
                "title": spread["title"],
                "date": datetime.datetime.now().strftime("%d.%m.%Y"),
                "text": res_text,
                "section": spread_key,
                "data": reading_payload_data,
            },
        )
        history = await get_readings_history(vk_id)
        await update_user(
            vk_id,
            {
                "latest_reading_text": res_text,
                "latest_reading_data": reading_payload_data,
                "readings_history": history,
            },
        )

        # Подготовка карточки и выпавших Арканов для вывода (до 10 фото ВК)
        attachments = []
        if spread.get("image_name"):
            try:
                cover_photo = await upload_local_photo(bot.api, spread["image_name"], peer_id=vk_id)
                if cover_photo:
                    attachments.append(cover_photo)
            except Exception as e:
                logger.warning(f"Failed to upload spread image {spread['image_name']}: {e}")

        # Прикрепляем выпавшие карты арканов (максимум до 10 вложений суммарно)
        max_card_photos = min(len(card_ids), 9) if attachments else min(len(card_ids), 10)
        for cid in card_ids[:max_card_photos]:
            try:
                card_photo = await upload_local_photo(bot.api, f"{cid}.jpeg", peer_id=vk_id)
                if card_photo:
                    attachments.append(card_photo)
            except Exception as e:
                logger.warning(f"Failed to upload card photo {cid}.jpeg: {e}")

        att = ",".join(attachments) if attachments else None

        # Клавиатура итогового отчета
        kb = Keyboard(inline=True)
        kb.add(
            Callback(
                "📜 ПОЛНЫЙ PDF-ОТЧЕТ",
                payload={"cmd": "gen_pdf", "section": spread_key, "card": str(card_ids[0])},
            ),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
        kb.add(
            Callback(
                "⭐️ Оценить расклад",
                payload={"cmd": "show_rating", "section": spread_key, "card": str(card_ids[0])},
            ),
            color=KeyboardButtonColor.PRIMARY,
        )
        kb.row()
        kb.add(
            Callback("🔮 ДРУГИЕ РАСКЛАДЫ", payload={"cmd": "secret_arts_cat", "cat": "tarot_spreads"}),
            color=KeyboardButtonColor.PRIMARY,
        )
        kb.row()
        kb.add(
            Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}),
            color=KeyboardButtonColor.SECONDARY,
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)
        target_cmid = typing_msg_id or conversation_message_id

        header_msg = f"✨ САВРАЛЬНЫЙ РАСКЛАД: {spread['title'].upper()} ✨\n\n{res_text}"

        # Если текст длиннее лимита ВК (4096 символов), аккуратно режем
        if len(header_msg) > 4000:
            part1 = header_msg[:3900]
            part2 = header_msg[3900:]
            if target_cmid:
                await ghost_edit(
                    bot.api,
                    peer_id,
                    part1,
                    attachment=att,
                    conversation_message_id=target_cmid,
                )
            else:
                await bot.api.messages.send(
                    peer_id=peer_id,
                    message=part1,
                    attachment=att,
                    random_id=random.getrandbits(63),
                )
            await bot.api.messages.send(
                peer_id=peer_id,
                message=part2,
                keyboard=kb.get_json(),
                random_id=random.getrandbits(63),
            )
        else:
            if target_cmid:
                await ghost_edit(
                    bot.api,
                    peer_id,
                    header_msg,
                    keyboard=kb.get_json(),
                    attachment=att,
                    conversation_message_id=target_cmid,
                )
            else:
                await bot.api.messages.send(
                    peer_id=peer_id,
                    message=header_msg,
                    keyboard=kb.get_json(),
                    attachment=att,
                    random_id=random.getrandbits(63),
                )
    finally:
        await release_lock(lock_key)
