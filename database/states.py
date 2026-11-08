import json
from database.config import URL, KEY, HEADERS
import database.core as core
from cache import get_fsm_state, set_fsm_state

# Маппинг шага FSM -> стейт vkbottle dispenser'а.
# Dispenser - in-memory зеркало Redis: главный источник истины - Redis
# (fsm:{vk_id}), а dispenser восстанавливается из него при старте
# (см. restore_fsm_dispenser), чтобы стейт жил после рестарта Render.
STATE_MAP = {
    "waiting_for_onboarding_data": "waiting_for_onboarding_data",
    "date": "waiting_for_date",
    "time": "waiting_for_time",
    "city": "waiting_for_city",
    "confirm_data": "waiting_confirm_data",
    "waiting_synastry_name": "waiting_synastry_name",
    "waiting_synastry_date": "waiting_synastry_date",
    "waiting_synastry_time": "waiting_synastry_time",
    "waiting_synastry_city": "waiting_synastry_city",
    "waiting_oracle_question": "waiting_oracle_question",
    "oracle_cut": "oracle_cut",
    "oracle_draw": "oracle_draw",
    "waiting_palmistry_photos": "waiting_palmistry_photos",
    "waiting_support_question": "waiting_support_question",
    "waiting_admin_reply": "waiting_admin_reply",
    "waiting_for_seal": "waiting_for_seal",
    "admin_user_search": "admin_user_search",
    "admin_broadcast_message": "admin_broadcast_message",
    "admin_energy_target": "admin_energy_target",
    "admin_user_edit_balance": "admin_user_edit_balance",
    "admin_user_give_card": "admin_user_give_card",
    "global_cut": "global_cut",
    "waiting_reset_confirm": "waiting_reset_confirm",
    "waiting_oculomancy_photo": "waiting_oculomancy_photo",
    "waiting_sigil_wish": "waiting_sigil_wish",
    "waiting_geo_location": "waiting_geo_location",
    "waiting_totem_step1": "waiting_totem_step1",
    "waiting_totem_step2": "waiting_totem_step2",
    "waiting_karma_step1": "waiting_karma_step1",
    "waiting_karma_step2": "waiting_karma_step2",
    "waiting_dream_text": "waiting_dream_text",
    "waiting_feedback_comment": "waiting_feedback_comment",
    "waiting_email_input": "waiting_email_input",
    "waiting_email_code": "waiting_email_code",
}


async def restore_fsm_dispenser(bot):
    """Восстанавливает in-memory state_dispenser из Redis после рестарта.

    Без этого хендлеры с фильтром state=MyStates... переставали работать
    до следующего действия пользователя: Redis-стейт жив, а dispenser пуст
    (аудит 2026-11: юзер зависал в waiting_email_code после деплоя).
    """
    from loguru import logger
    from modules.states import MyStates

    steps_to_states = {
        "waiting_for_onboarding_data": MyStates.WAITING_FOR_ONBOARDING_DATA,
        "date": MyStates.WAITING_FOR_DATE,
        "time": MyStates.WAITING_FOR_TIME,
        "city": MyStates.WAITING_FOR_CITY,
        "confirm_data": MyStates.WAITING_CONFIRM_DATA,
        "waiting_synastry_name": MyStates.WAITING_SYNASTRY_NAME,
        "waiting_synastry_date": MyStates.WAITING_SYNASTRY_DATE,
        "waiting_synastry_time": MyStates.WAITING_SYNASTRY_TIME,
        "waiting_synastry_city": MyStates.WAITING_SYNASTRY_CITY,
        "waiting_oracle_question": MyStates.WAITING_ORACLE_QUESTION,
        "oracle_cut": MyStates.ORACLE_CUT,
        "oracle_draw": MyStates.ORACLE_DRAW,
        "waiting_palmistry_photos": MyStates.WAITING_PALMISTRY_PHOTOS,
        "waiting_support_question": MyStates.WAITING_SUPPORT_QUESTION,
        "global_cut": MyStates.GLOBAL_CUT,
        "waiting_reset_confirm": MyStates.WAITING_RESET_CONFIRM,
        "waiting_oculomancy_photo": MyStates.WAITING_OCULOMANCY_PHOTO,
        "waiting_sigil_wish": MyStates.WAITING_SIGIL_WISH,
        "waiting_geo_location": MyStates.WAITING_GEO_LOCATION,
        "waiting_totem_step1": MyStates.WAITING_TOTEM_STEP1,
        "waiting_totem_step2": MyStates.WAITING_TOTEM_STEP2,
        "waiting_karma_step1": MyStates.WAITING_KARMA_STEP1,
        "waiting_karma_step2": MyStates.WAITING_KARMA_STEP2,
        "waiting_dream_text": MyStates.WAITING_DREAM_TEXT,
        "waiting_feedback_comment": MyStates.WAITING_FEEDBACK_COMMENT,
        "waiting_email_input": MyStates.WAITING_EMAIL_INPUT,
        "waiting_email_code": MyStates.WAITING_EMAIL_CODE,
    }

    restored = 0
    try:
        from cache import redis_client

        keys = await redis_client.keys("fsm:*")
        for key in keys:
            raw_vk_id = key.split(":", 1)[1] if isinstance(key, str) else key.decode().split(":", 1)[1]
            raw = await get_fsm_state(raw_vk_id)
            if not raw:
                continue
            try:
                state = json.loads(raw)
            except Exception:
                continue
            step = state.get("step") if isinstance(state, dict) else None
            target = steps_to_states.get(step)
            if target:
                try:
                    await bot.state_dispenser.set(int(raw_vk_id), target, raw_json=raw)
                    restored += 1
                except Exception:
                    pass
        logger.info(f"FSM восстановлен из Redis: {restored} активных стейтов")
    except Exception as e:
        logger.error(f"Ошибка восстановления FSM из Redis: {e}")
    return restored

async def check_and_save_transaction(transaction_id: str, vk_id: int, amount: int) -> bool:
    if not URL or not KEY or core.session is None: return False
    try:
        async with core.session.get(f"{URL}/rest/v1/events?action=eq.vkpay_transaction&metadata->>transaction_id=eq.{transaction_id}", headers=HEADERS) as r:
            if r.status == 200 and await r.json(): return False

        from .events import add_event, is_first_payment

        # Check if first payment before recording this one
        first = await is_first_payment(vk_id)

        metadata = {"transaction_id": transaction_id, "amount": amount, "payment_method": "vkpay"}

        # Track energy purchase
        await add_event(vk_id, "energy_purchased", metadata)

        # Track first payment if applicable
        if first:
            await add_event(vk_id, "first_payment", metadata)

        payload = {"user_id": vk_id, "action": "vkpay_transaction", "metadata": metadata}
        async with core.session.post(f"{URL}/rest/v1/events", headers=HEADERS, json=payload) as r:
            return r.status in (200, 201, 204)
    except Exception: return False

async def get_user_state(vk_id: int):
    from modules.bot_init import bot
    state_rec = await bot.state_dispenser.get(vk_id)
    if state_rec: return state_rec.payload.get("raw_json") if state_rec.payload else None
    return await get_fsm_state(vk_id)

async def set_user_state(vk_id: int, state: str):
    from modules.bot_init import bot
    from modules.states import MyStates
    if not state:
        try: await bot.state_dispenser.delete(vk_id)
        except: pass
        await set_fsm_state(vk_id, state)
        return True
    try: step = json.loads(state).get("step", "")
    except: step = state
    state_map = {
        "waiting_for_onboarding_data": MyStates.WAITING_FOR_ONBOARDING_DATA,
        "date": MyStates.WAITING_FOR_DATE,
        "time": MyStates.WAITING_FOR_TIME,
        "city": MyStates.WAITING_FOR_CITY,
        "confirm_data": MyStates.WAITING_CONFIRM_DATA,
        "waiting_synastry_name": MyStates.WAITING_SYNASTRY_NAME,
        "waiting_synastry_date": MyStates.WAITING_SYNASTRY_DATE,
        "waiting_synastry_time": MyStates.WAITING_SYNASTRY_TIME,
        "waiting_synastry_city": MyStates.WAITING_SYNASTRY_CITY,
        "waiting_oracle_question": MyStates.WAITING_ORACLE_QUESTION,
        "oracle_cut": MyStates.ORACLE_CUT,
        "oracle_draw": MyStates.ORACLE_DRAW,
        "waiting_palmistry_photos": MyStates.WAITING_PALMISTRY_PHOTOS,
        "waiting_support_question": MyStates.WAITING_SUPPORT_QUESTION,
        "waiting_admin_reply": "waiting_admin_reply",
        "waiting_for_seal": "waiting_for_seal",
        "admin_user_search": "admin_user_search",
        "admin_broadcast_message": "admin_broadcast_message",
        "admin_energy_target": "admin_energy_target",
        "admin_user_edit_balance": "admin_user_edit_balance",
        "admin_user_give_card": "admin_user_give_card",
        "global_cut": MyStates.GLOBAL_CUT,
        "waiting_reset_confirm": MyStates.WAITING_RESET_CONFIRM,
        "waiting_oculomancy_photo": MyStates.WAITING_OCULOMANCY_PHOTO,
        "waiting_sigil_wish": MyStates.WAITING_SIGIL_WISH,
        "waiting_geo_location": MyStates.WAITING_GEO_LOCATION,
        "waiting_totem_step1": MyStates.WAITING_TOTEM_STEP1,
        "waiting_totem_step2": MyStates.WAITING_TOTEM_STEP2,
        "waiting_karma_step1": MyStates.WAITING_KARMA_STEP1,
        "waiting_karma_step2": MyStates.WAITING_KARMA_STEP2,
        "waiting_dream_text": MyStates.WAITING_DREAM_TEXT,
        "waiting_feedback_comment": MyStates.WAITING_FEEDBACK_COMMENT,
        "waiting_email_input": MyStates.WAITING_EMAIL_INPUT,
        "waiting_email_code": MyStates.WAITING_EMAIL_CODE
    }
    # Always persist to Redis for reliability across restarts
    await set_fsm_state(vk_id, state)

    # Логируем переход в новое состояние для UX аналитики
    from .events import add_event
    import asyncio
    asyncio.create_task(add_event(vk_id, "state_transition", {"new_state": state}))

    target = state_map.get(step)
    if target:
        await bot.state_dispenser.set(vk_id, target, raw_json=state)
    else:
        try:
            await bot.state_dispenser.delete(vk_id)
        except Exception:
            pass
    return True
