import random
import datetime
import json
from loguru import logger
from vkbottle import Keyboard, Callback, KeyboardButtonColor
from database import get_user, set_user_state
from modules.bot_init import bot
from modules.utils import (
    ghost_edit,
    start_dynamic_typing,
    stop_dynamic_typing,
    upload_local_photo,
    get_last_bot_msg,
    delete_bot_message,
)
from cache import acquire_lock, release_lock


async def card_of_day_logic(
    vk_id: int, peer_id: int, skip_lock: bool = False, **kwargs
):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        conv_msg_id = kwargs.get("conversation_message_id")

        # Проверка данных в Redis
        from cache import get_birth_data_or_fallback

        birth_data = await get_birth_data_or_fallback(vk_id)
        if not birth_data:
            # Пытаемся спарсить из ВК
            try:
                users_info = await bot.api.users.get(
                    user_ids=[vk_id], fields=["bdate", "city"]
                )
                bdate, city = "", ""
                if users_info:
                    info = users_info[0]
                    bdate = info.bdate or ""
                    if info.city and hasattr(info.city, "title"):
                        city = info.city.title

                if bdate and city:
                    # Данные есть в ВК, предлагаем подтвердить
                    state_dict = {
                        "step": "confirm_data",
                        "date": bdate,
                        "time": "12:00",
                        "city": city,
                        "conv_id": conv_msg_id,
                        "original_intent": {"cmd": "card_of_day"},
                    }
                    await set_user_state(vk_id, json.dumps(state_dict))

                    kb = Keyboard(inline=True)
                    kb.add(
                        Callback("✅ ВЕРНО", payload={"cmd": "confirm_registration"}),
                        color=KeyboardButtonColor.POSITIVE,
                    )
                    kb.row().add(
                        Callback(
                            "🔄 ИЗМЕНИТЬ", payload={"cmd": "edit_onboarding_data"}
                        ),
                        color=KeyboardButtonColor.NEGATIVE,
                    )

                    text = (
                        "🔮 ДАННЫЕ СТЕРТЫ В ЦЕЛЯХ БЕЗОПАСНОСТИ\n\n"
                        "Чтобы я могла настроиться на твою энергию, пожалуйста, проверь верны ли твои данные:\n\n"
                        f"☾ Дата: {bdate}\n"
                        f"☾ Город: {city}\n"
                        "☾ Время: 12:00 (по умолчанию)\n\n"
                        "Всё верно?"
                    )
                    if conv_msg_id:
                        await bot.api.messages.edit(
                            peer_id=peer_id,
                            conversation_message_id=conv_msg_id,
                            message=text,
                            keyboard=kb.get_json(),
                        )
                    else:
                        await bot.api.messages.send(
                            peer_id=peer_id,
                            message=text,
                            keyboard=kb.get_json(),
                            random_id=random.getrandbits(63),
                        )
                    return
            except Exception as e:
                logger.error(f"Error parsing VK data for card of day: {e}")

            # Если данных нет в ВК или ошибка - ручной ввод
            await set_user_state(
                vk_id, '{"step": "waiting_birth_date", "target_section": "card_of_day"}'
            )
            msg = "🔮 ДАННЫЕ СТЕРТЫ В ЦЕЛЯХ БЕЗОПАСНОСТИ\n\nЧтобы я могла настроиться на твою энергию, шепни мне свою ДАТУ рождения (например, 15.04.1990):"
            if conv_msg_id:
                await bot.api.messages.edit(
                    peer_id=peer_id, conversation_message_id=conv_msg_id, message=msg
                )
            else:
                await bot.api.messages.send(
                    peer_id=peer_id, message=msg, random_id=random.getrandbits(63)
                )
            return

        await start_dynamic_typing(
            bot.api, peer_id, conversation_message_id=conv_msg_id
        )
        user = await get_user(vk_id)
        if not user:
            return

        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")
        if last_used_str:
            last_time = datetime.datetime.fromisoformat(last_used_str)
            if (
                datetime.datetime.now(datetime.timezone.utc) - last_time
            ).total_seconds() < 24 * 3600:
                err_msg = "Ты уже получил напутствие на сегодня. Возвращайся завтра или спроси совета у Оракула ✨"
                await stop_dynamic_typing(peer_id)
                if conv_msg_id:
                    await bot.api.messages.edit(
                        peer_id=peer_id,
                        conversation_message_id=conv_msg_id,
                        message=err_msg,
                    )
                else:
                    await bot.api.messages.send(
                        peer_id=peer_id,
                        message=err_msg,
                        random_id=random.getrandbits(63),
                    )
                return

        await set_user_state(
            vk_id, json.dumps({"step": "global_cut", "target_section": "card_of_day"})
        )
        kb = Keyboard(inline=True).add(
            Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}),
            color=KeyboardButtonColor.SECONDARY,
        )
        att = await upload_local_photo(
            bot.api, "uslugi/cardofday.jpeg", peer_id=peer_id
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)

        # Если это вызов из текстового хендлера, пытаемся почистить старое
        if not conv_msg_id:
            last_mid = await get_last_bot_msg(vk_id)
            if last_mid:
                await delete_bot_message(bot.api, vk_id, mid=last_mid)

        await ghost_edit(
            bot.api,
            peer_id,
            message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.",
            conversation_message_id=conv_msg_id,
            message_id=typing_msg_id,
            attachment=att,
            keyboard=kb.get_json(),
        )
    except Exception as e:
        logger.error(f"Ошибка в Карте Дня: {e}")
        err_msg = "Кажется, Вселенная сейчас хранит молчание. Попробуй заглянуть чуть позже ✨"
        if conv_msg_id:
            await bot.api.messages.edit(
                peer_id=peer_id, conversation_message_id=conv_msg_id, message=err_msg
            )
        else:
            await bot.api.messages.send(
                peer_id=peer_id, message=err_msg, random_id=random.getrandbits(63)
            )
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)
