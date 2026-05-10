import re
with open("modules/profile.py", "r") as f:
    content = f.read()

new_handlers = """
async def is_waiting_change_date(message: Message) -> bool:
    if message.text and message.text.startswith("✦"): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "date"

@labeler.message(func=is_waiting_change_date)
async def process_change_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        new_date = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "time", "date": new_date}))
        await message.answer(f"Дата {new_date} принята. Теперь введите ВРЕМЯ вашего рождения (например, 14:30 или 'не знаю'):")
    finally:
        await release_lock(vk_id)

async def is_waiting_change_time(message: Message) -> bool:
    if message.text and message.text.startswith("✦"): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "time"

@labeler.message(func=is_waiting_change_time)
async def process_change_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        new_time = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        new_date = state_dict.get("date", "")
        await set_user_state(vk_id, json.dumps({"step": "city", "date": new_date, "time": new_time}))
        await message.answer(f"Время {new_time} принято. Теперь введите ГОРОД вашего рождения:")
    finally:
        await release_lock(vk_id)

async def is_waiting_change_city(message: Message) -> bool:
    if message.text and message.text.startswith("✦"): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "city"

@labeler.message(func=is_waiting_change_city)
async def process_change_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        new_city = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        new_date = state_dict.get("date", "")
        new_time = state_dict.get("time", "")

        await update_user(vk_id, {
            "birth_date": new_date,
            "birth_time": new_time,
            "birth_city": new_city
        })
        await set_user_state(vk_id, "")

        kb = Keyboard(inline=True)
        kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
        await message.answer(f"Твои данные обновлены: {new_date}, {new_time}, г. {new_city}", keyboard=kb.get_json())
    finally:
        await release_lock(vk_id)

@labeler.message(text="Отменить подписку")"""
content = content.replace('@labeler.message(text="Отменить подписку")', new_handlers)
if "get_fsm_step" not in content:
    content = content.replace("upload_local_photo", "upload_local_photo, get_fsm_step")
with open("modules/profile.py", "w") as f:
    f.write(content)
