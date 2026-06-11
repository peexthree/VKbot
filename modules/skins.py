import random
from loguru import logger
from modules.utils.consts import CHARACTER_DESCRIPTIONS, SKIN_VISUALS
from modules.utils import upload_local_photo
from database import update_user, get_user

SKIN_QUEST_SNACKBARS = {
    "fluffy": "Твой Круг пуст! Пригласи 5 активных друзей, которые дойдут до 3 уровня энергии.",
    "vanga": "Держи ритм! Заходи за прогнозом 7 дней подряд без единого пропуска.",
    "ai_mom": "Матрица ждет данных! Соверши 30 любых ритуалов или разборов в системе.",
    "honest_oracle": "Сбрось старую кожу! Собери комбо: получи теги 'выход-из-кризиса' и 'свобода' одновременно.",
    "saint_germain": "Путь алхимика платный. Стань Доном или купи VIP-пакет энергии.",
    "pythia": "Твои сны - ключ. Сделай 10 глубоких разборов в Соннике и найди скрытый символ.",
    "freud": "Познай пламя страсти! Проверь совместимость с 3 разными партнерами, чтобы вскрыть свои паттерны.",
    "jack_sparrow": "Пусть все увидят твой путь! Поделись раскладом на стене своего профиля.",
    "cleopatra": "Твой облик неясен. Заполни профиль на 100% и примени 3 разных маски персонажей.",
    "anubis": "Врата мертвых закрыты. Достигни 5 уровня Гримуара и активируй все разделы бота."
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
            random_id=random.getrandbits(63)
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
