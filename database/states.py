import json
from database.config import URL, KEY, HEADERS
import database.core as core
from cache import get_fsm_state, set_fsm_state

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
        "waiting_reset_confirm": MyStates.WAITING_RESET_CONFIRM
    }
    # Always persist to Redis for reliability across restarts
    await set_fsm_state(vk_id, state)

    target = state_map.get(step)
    if target:
        await bot.state_dispenser.set(vk_id, target, raw_json=state)
    else:
        try:
            await bot.state_dispenser.delete(vk_id)
        except Exception:
            pass
    return True
