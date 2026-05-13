import json
from loguru import logger
from modules.bot_init import bot
from database import get_user
from cache import get_tarot_names, acquire_lock, release_lock
from modules.utils import SKIN_ASSETS, upload_local_photo

async def show_grimoire_page(vk_id: int, peer_id: int, page: int):
    if not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user:
            return

        unlocked_cards = user.get("unlocked_cards", {})
        if isinstance(unlocked_cards, list):
             unlocked_cards = {}

        tarot_names = await get_tarot_names()

        unlocked_items = []
        for i in range(78):
            card_id_str = str(i)
            if card_id_str in unlocked_cards:
                unlocked_items.append({"id": card_id_str, "name": tarot_names.get(card_id_str, f"Карта {i}")})

        if not unlocked_items:
            await bot.api.messages.send(peer_id=peer_id, message="✦ МОЙ ГРИМУАР ✦\n\nТвой гримуар пока пуст.", random_id=0)
            return

        ITEMS_PER_PAGE = 5
        total_pages = (len(unlocked_items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        start_idx = page * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        current_items = unlocked_items[start_idx:end_idx]

        lines = [
            f"✦ МОЙ ГРИМУАР ✦ (Страница {page + 1}/{total_pages})\n",
            "Это твоя личная книга магии. Здесь хранятся все карты, которые ты уже успел открыть. Нажимай на любую, чтобы освежить в памяти ее тайное значение.\n"
        ]

        # Max 2 buttons per row
        buttons = []
        current_row = []

        for item in current_items:
            lines.append(f"[{item['id']}] {item['name']}")
            current_row.append({
                "action": {
                    "type": "callback",
                    "payload": json.dumps({"cmd": "view_card", "id": item['id']}),
                    "label": f"Карта {item['id']}"
                },
                "color": "secondary"
            })
            if len(current_row) == 2:
                buttons.append(current_row)
                current_row = []

        if current_row:
            buttons.append(current_row)

        text = "\n".join(lines)

        nav_row = []
        if page > 0:
            nav_row.append({
                "action": {
                    "type": "callback",
                    "payload": json.dumps({"cmd": "grimoire_page", "page": page - 1}),
                    "label": "Назад"
                },
                "color": "primary"
            })
        if page < total_pages - 1:
            nav_row.append({
                "action": {
                    "type": "callback",
                    "payload": json.dumps({"cmd": "grimoire_page", "page": page + 1}),
                    "label": "Вперед"
                },
                "color": "primary"
            })
        if nav_row:
            buttons.append(nav_row)

        buttons.append([{
            "action": {
                "type": "callback",
                "payload": json.dumps({"cmd": "services_menu"}),
                "label": "🔮 ГЛУБОКИЕ РАЗБОРЫ"
            },
            "color": "positive"
        }])

        kb = {"inline": True, "buttons": buttons}

        try:
            await bot.api.messages.send(
                peer_id=peer_id,
                message=text,
                keyboard=json.dumps(kb, ensure_ascii=False),
                random_id=0
            )
        except Exception as e:
            logger.error(f"Ошибка отправки клавиатуры Гримуара: {str(e)}")
            await bot.api.messages.send(peer_id=peer_id, message=text, random_id=0)
    finally:
        await release_lock(vk_id)

async def view_card_direct(vk_id: int, peer_id: int, card_id: str):
    if not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user:
            return

        unlocked_cards = user.get("unlocked_cards", {})
        if isinstance(unlocked_cards, list):
             unlocked_cards = {}

        if str(card_id) not in unlocked_cards:
            await bot.api.messages.send(peer_id=peer_id, message="Эта карта еще не открыта.", random_id=0)
            return

        active_skin = user.get("active_skin", "olesya")
        skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
        if skin_att:
            await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)

        signature = unlocked_cards[str(card_id)]
        await bot.api.messages.send(peer_id=peer_id, message=f"Твое первое касание с этой картой: {signature}", random_id=0)

        photo_att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)
        if photo_att:
            await bot.api.messages.send(peer_id=peer_id, message="", attachment=photo_att, random_id=0)
    finally:
        await release_lock(vk_id)
