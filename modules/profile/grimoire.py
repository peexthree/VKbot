from vkbottle import Keyboard, KeyboardButtonColor, Callback
from loguru import logger

from modules.bot_init import bot
from database import get_user
from cache import get_tarot_names, acquire_lock, release_lock
from modules.utils import SKIN_ASSETS, upload_local_photo, start_dynamic_typing, stop_dynamic_typing


def _normalize_unlocked_cards(unlocked_cards) -> dict:
    """Приводим unlocked_cards к dict независимо от того, list или dict в БД"""
    if isinstance(unlocked_cards, list):
        return {}
    return unlocked_cards or {}


async def show_grimoire_page(vk_id: int, peer_id: int, page: int = 0, skip_lock: bool = False):
    """Показывает страницу Гримуара с пагинацией"""
    if not skip_lock and not await acquire_lock(vk_id):
        return

    try:
        await start_dynamic_typing(bot.api, peer_id)

        user = await get_user(vk_id)
        if not user:
            await bot.api.messages.send(peer_id=peer_id, message="❌ Профиль не найден.", random_id=0)
            return

        unlocked_cards = _normalize_unlocked_cards(user.get("unlocked_cards"))
        tarot_names = await get_tarot_names()

        # Собираем только открытые карты
        unlocked_items = [
            {"id": str(i), "name": tarot_names.get(str(i), f"Карта {i}")}
            for i in range(78)
            if str(i) in unlocked_cards
        ]

        if not unlocked_items:
            await bot.api.messages.send(
                peer_id=peer_id,
                message="✦ МОЙ ГРИМУАР ✦\n\nТвой гримуар пока пуст. Открой первую карту в Услугах.",
                random_id=0
            )
            return

        ITEMS_PER_PAGE = 5
        total_pages = (len(unlocked_items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        page = max(0, min(page, total_pages - 1))

        start_idx = page * ITEMS_PER_PAGE
        current_items = unlocked_items[start_idx : start_idx + ITEMS_PER_PAGE]

        # Текст
        lines = [
            f"✦ МОЙ ГРИМУАР ✦ (Страница {page + 1}/{total_pages})\n",
            "Это твоя личная книга магии. Нажимай на карту, чтобы освежить её значение.\n",
        ]
        for item in current_items:
            lines.append(f"[{item['id']}] {item['name']}")

        text = "\n".join(lines)

        # Красивая клавиатура через vkbottle
        kb = Keyboard(inline=True, one_time=False)

        # Кнопки карт (по 2 в ряд)
        for i, item in enumerate(current_items):
            if i % 2 == 0 and i != 0:
                kb.row()
            kb.add(
                Callback(
                    f"Карта {item['id']}",
                    payload={"cmd": "view_card", "id": item['id']},
                    color=KeyboardButtonColor.SECONDARY,
                )
            )

        # Навигация
        kb.row()
        if page > 0:
            kb.add(
                Callback("◀️ Назад", payload={"cmd": "grimoire_page", "page": page - 1}),
                color=KeyboardButtonColor.PRIMARY,
            )
        if page < total_pages - 1:
            kb.add(
                Callback("Вперёд ▶️", payload={"cmd": "grimoire_page", "page": page + 1}),
                color=KeyboardButtonColor.PRIMARY,
            )

        # Кнопка в Услуги
        kb.row()
        kb.add(
            Callback("🔮 ГЛУБОКИЕ РАЗБОРЫ", payload={"cmd": "services_menu"}),
            color=KeyboardButtonColor.POSITIVE,
        )

        await bot.api.messages.send(
            peer_id=peer_id,
            message=text,
            keyboard=kb.get_json(),
            random_id=0,
        )

    except Exception as e:
        logger.error(f"Ошибка в show_grimoire_page: {e}")
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def view_card_direct(vk_id: int, peer_id: int, card_id: str, skip_lock: bool = False):
    """Показывает детальную информацию по конкретной карте"""
    if not skip_lock and not await acquire_lock(vk_id):
        return

    try:
        await start_dynamic_typing(bot.api, peer_id)

        user = await get_user(vk_id)
        if not user:
            return

        unlocked_cards = _normalize_unlocked_cards(user.get("unlocked_cards"))

        if str(card_id) not in unlocked_cards:
            await bot.api.messages.send(peer_id=peer_id, message="Эта карта ещё не открыта.", random_id=0)
            return

        # Проводник (скин)
        active_skin = user.get("active_skin", "olesya")
        skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
        if skin_att:
            await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)

        # Подпись первого касания
        signature = unlocked_cards[str(card_id)]
        await bot.api.messages.send(
            peer_id=peer_id,
            message=f"Твоё первое касание с этой картой:\n{signature}",
            random_id=0,
        )

        # Фото карты
        photo_att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)
        if photo_att:
            await bot.api.messages.send(peer_id=peer_id, message="", attachment=photo_att, random_id=0)

    except Exception as e:
        logger.error(f"Ошибка в view_card_direct: {e}")
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)
