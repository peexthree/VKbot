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

def get_progress_bar(current: int, total: int) -> str:
    percent = min(100, int((current / total) * 100))
    filled = min(10, int(percent / 10))
    bar = "▒" * filled + "░" * (10 - filled)
    return f"{bar} {percent}%"

async def get_dynamic_quest_text(vk_id: int, skin_id: str) -> str:
    user = await get_user(vk_id)
    if not user:
        return "Данные пользователя не найдены."

    # Названия и условия
    skin_names = {
        "fluffy": "Флаффи", "vanga": "Ванга", "ai_mom": "AI Mom",
        "honest_oracle": "Честный Оракул", "pythia": "Пифия", "freud": "Фрейд",
        "jack_sparrow": "Джек Соловей", "cleopatra": "Клеопатра", "anubis": "Анубис"
    }

    name = skin_names.get(skin_id, skin_id.capitalize())

    base_text = f"🔒 {name}\nСтатус: В процессе пробуждения\n\n"
    footer = "\n\n💡 Выполни условия, и Проводник заговорит с тобой."

    if skin_id == "fluffy":
        curr = user.get("active_referrals_count", 0) or 0
        total = 5
        bar = get_progress_bar(curr, total)
        return f"{base_text}➔ Пригласить 5 активных друзей (ур. 3): [ {curr} / {total} ]\n{bar}{footer}"

    elif skin_id == "vanga":
        curr = user.get("visit_streak", 0) or 0
        total = 7
        bar = get_progress_bar(curr, total)
        return f"{base_text}➔ Ежедневный стрик: [ {curr} / {total} ]\n{bar}{footer}"

    elif skin_id == "ai_mom":
        curr = user.get("rituals_count", 0) or 0
        total = 30
        bar = get_progress_bar(curr, total)
        return f"{base_text}➔ Совершить 30 ритуалов: [ {curr} / {total} ]\n{bar}{footer}"

    elif skin_id == "pythia":
        curr = user.get("dreams_analyzed_count", 0) or 0
        total = 10
        bar = get_progress_bar(curr, total)
        return f"{base_text}➔ Разборы в Соннике: [ {curr} / {total} ]\n{bar}{footer}"

    elif skin_id == "freud":
        curr = user.get("compatibility_partners_count", 0) or 0
        total = 3
        bar = get_progress_bar(curr, total)
        return f"{base_text}➔ Проверки совместимости: [ {curr} / {total} ]\n{bar}{footer}"

    elif skin_id == "cleopatra":
        # Профиль на 100% (дата, время, город)
        from cache import get_temp_birth_data
        temp_birth = await get_temp_birth_data(vk_id)
        has_profile = temp_birth and temp_birth.get("date") and temp_birth.get("time") and temp_birth.get("city")
        profile_status = "[ Найдено ]" if has_profile else "[ Не заполнен ]"

        curr_skins = user.get("used_skins_count", 0) or 0
        total_skins = 3
        bar_skins = get_progress_bar(curr_skins, total_skins)

        return f"{base_text}➔ Заполнить профиль: {profile_status}\n➔ Применить 3 маски: [ {curr_skins} / {total_skins} ]\n{bar_skins}{footer}"

    elif skin_id == "anubis":
        from modules.utils.logic import calculate_user_rank
        level, _ = calculate_user_rank(user)
        total_lvl = 5
        bar_lvl = get_progress_bar(level, total_lvl)

        history = user.get("readings_history", [])
        used_sections = {h.get("section") for h in history} if isinstance(history, list) else set()
        core_sections = {"sex", "money", "shadow", "final", "synastry", "palmistry", "dream", "oracle", "antitaro"}
        found_sections = core_sections.intersection(used_sections)

        return f"{base_text}➔ Достичь 5 уровня: [ {level} / {total_lvl} ]\n{bar_lvl}\n➔ Активировать все разделы: [ {len(found_sections)} / {len(core_sections)} ]{footer}"

    elif skin_id == "honest_oracle":
        tags = user.get("tags", [])
        has_crisis = "выход-из-кризиса" in tags
        has_freedom = "свобода" in tags
        status = f"[{'✅' if has_crisis else '░'}] Кризис | [{'✅' if has_freedom else '░'}] Свобода"
        return f"{base_text}➔ Собрать комбо тегов:\n{status}{footer}"

    elif skin_id == "jack_sparrow":
        return f"{base_text}➔ Поделиться раскладом на стене ВК: [ 0 / 1 ]\n░░░░░░░░░░ 0%{footer}"

    return get_quest_text(skin_id)

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
