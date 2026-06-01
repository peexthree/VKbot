from loguru import logger
from modules.utils.consts import CHARACTER_DESCRIPTIONS, SKIN_VISUALS
from modules.utils import upload_local_photo
from database import update_user, get_user

SKIN_QUEST_SNACKBARS = {
    "fluffy": "Пригласи 5 друзей по своей реферальной ссылке.",
    "vanga": "Заходи в бота и запрашивай прогноз 7 дней подряд без перерывов.",
    "ai_mom": "Сделай 15 любых генераций или разборов в боте.",
    "honest_oracle": "Получи в профиль ИИ-тег выход-из-кризиса или освобождение-от-прошлого.",
    "saint_germain": "Стань участником клуба VK Donut или купи VIP-пакет энергии.",
    "pythia": "Сделай 5 глубоких разборов сновидений в модуле Сонник.",
    "freud": "Сделай полный разбор сексуальной совместимости в модуле СТРАСТЬ.",
    "jack_sparrow": "Поделись результатом любого расклада на своей стене ВКонтакте.",
    "cleopatra": "Заполни профиль на 100%: укажи дату, время и город рождения.",
    "anubis": "Пасхалка! Сделай разборы абсолютно всех 5 разделов бота."
}

def get_quest_text(skin_id: str) -> str:
    return SKIN_QUEST_SNACKBARS.get(skin_id, "Квест временно недоступен.")

async def send_trigger_message(api, vk_id: int, skin_id: str):
    try:
        desc = CHARACTER_DESCRIPTIONS.get(skin_id)
        if not desc:
            return

        name = desc.get("name", "").upper()
        concept = desc.get("concept", "").replace("—", "-")
        style = desc.get("style", "").replace("—", "-")
        effect = desc.get("effect", "").replace("—", "-")

        msg = (
            f"🏆 ДОСТИЖЕНИЕ РАЗБЛОКИРОВАНО!\n\n"
            f"🔮 Тебе открылся новый тайный проводник: {name}\n\n"
            f"{concept}\n\n"
            f"{style}\n\n"
            f"{effect}\n\n"
            f"✨ Переходи в Главное меню, жми кнопку «🔮 ЗАЛ ПРОРОКОВ» и активируй его, чтобы перепрошить свою Систему!"
        )

        filename = SKIN_VISUALS.get(skin_id, "o.png")
        att = await upload_local_photo(api, f"uslugi/{filename}", peer_id=vk_id)

        await api.messages.send(
            peer_id=vk_id,
            message=msg,
            attachment=att,
            random_id=0
        )
    except Exception as e:
        logger.error(f"Error sending trigger message for {skin_id} to {vk_id}: {e}")

async def unlock_skin(api, vk_id: int, skin_id: str):
    """Открывает скин для пользователя, если он еще не открыт"""
    user = await get_user(vk_id)
    if not user:
        return

    purchased_skins = user.get("purchased_skins", [])
    if skin_id not in purchased_skins:
        purchased_skins.append(skin_id)
        await update_user(vk_id, {"purchased_skins": purchased_skins})
        await send_trigger_message(api, vk_id, skin_id)
