import json
from database.config import URL, KEY, HEADERS
import database.core as core
from cache import get_fsm_state, set_fsm_state

async def check_and_save_transaction(transaction_id: str, vk_id: int, amount: int) -> bool:
    if not URL or not KEY or core.session is None: return False
    try:
        async with core.session.get(f"{URL}/rest/v1/events?action=eq.vkpay_transaction&metadata->>transaction_id=eq.{transaction_id}", headers=HEADERS) as r:
            if r.status == 200 and await r.json(): return False
        payload = {"user_id": vk_id, "action": "vkpay_transaction", "metadata": {"transaction_id": transaction_id, "amount": amount}}
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
        "waiting_for_onboarding_data": MyStates.WAITING_FOR_ONBOARDING_DATA, "date": MyStates.WAITING_FOR_DATE,
        "time": MyStates.WAITING_FOR_TIME, "city": MyStates.WAITING_FOR_CITY, "confirm_data": MyStates.WAITING_CONFIRM_DATA,
        "waiting_synastry_date": MyStates.WAITING_SYNASTRY_DATE, "waiting_oracle_question": MyStates.WAITING_ORACLE_QUESTION,
        "oracle_draw": MyStates.ORACLE_DRAW, "global_cut": MyStates.GLOBAL_CUT, "waiting_reset_confirm": MyStates.WAITING_RESET_CONFIRM
    }
    target = state_map.get(step)
    if target: await bot.state_dispenser.set(vk_id, target, raw_json=state)
    else:
        try: await bot.state_dispenser.delete(vk_id)
        except: pass
        await set_fsm_state(vk_id, state)
    return True
