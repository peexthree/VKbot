import json
from loguru import logger
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text, Callback
from modules.utils import ADMIN_ID, warmup_task, clear_photo_cache, get_dynamic_keyboard
from cache import redis_client, set_fsm_state
from database import get_all_users

labeler = BotLabeler()

@labeler.message(text=["⚙️ КОНСОЛЬ МАГИСТРА"])
async def admin_console_handler(message: Message):
    if message.from_id != ADMIN_ID:
        return

    await show_admin_console(message.peer_id)

async def show_admin_console(peer_id: int):
    # Fetch flags
    warmup_active = await redis_client.get("system_config:warmup_active")
    warmup_active = bool(int(warmup_active)) if warmup_active else False

    maintenance_mode = await redis_client.get("system_config:maintenance_mode")
    maintenance_mode = bool(int(maintenance_mode)) if maintenance_mode else False

    tag_memory_active = await redis_client.get("system_config:tag_memory_active")
    # Default to True if missing
    tag_memory_active = bool(int(tag_memory_active)) if tag_memory_active is not None else True

    users = await get_all_users()
    user_count = len(users)

    # Note: the real cache size logic will vary, but we can do a rough count from redis
    try:
        keys = await redis_client.keys("photo:*")
        cache_count = len(keys)
    except:
        cache_count = "N/A"

    text = (
        "⚙️ КОНСОЛЬ МАГИСТРА ⚙️\n\n"
        f"👥 Адептов в матрице: {user_count}\n"
        f"🖼 Ассетов в кэше: {cache_count}\n\n"
        f"Фоновый прогрев: {'🟢 ВКЛ' if warmup_active else '🔴 ВЫКЛ'}\n"
        f"Режим тех. работ: {'🔴 АКТИВЕН' if maintenance_mode else '🟢 ВЫКЛ'}\n"
        f"Теговая память ИИ: {'🟢 ВКЛ' if tag_memory_active else '🔴 ВЫКЛ'}"
    )

    kb = Keyboard(inline=True)

    # Toggle Cache
    if warmup_active:
        kb.add(Callback("Остановить прогрев", payload={"cmd": "admin_cmd", "action": "toggle_warmup"}), color=KeyboardButtonColor.NEGATIVE)
    else:
        kb.add(Callback("🟢 ВКЛЮЧИТЬ КЭШИРОВАНИЕ", payload={"cmd": "admin_cmd", "action": "toggle_warmup"}), color=KeyboardButtonColor.POSITIVE)

    kb.row()

    # Toggle Maintenance
    if maintenance_mode:
        kb.add(Callback("Выключить Тех. Работы", payload={"cmd": "admin_cmd", "action": "toggle_maintenance"}), color=KeyboardButtonColor.POSITIVE)
    else:
        kb.add(Callback("🛠 РЕЖИМ ТЕХ. РАБОТ", payload={"cmd": "admin_cmd", "action": "toggle_maintenance"}), color=KeyboardButtonColor.NEGATIVE)

    kb.row()

    # Toggle AI Memory
    if tag_memory_active:
        kb.add(Callback("Отключить память ИИ", payload={"cmd": "admin_cmd", "action": "toggle_tag_memory"}), color=KeyboardButtonColor.NEGATIVE)
    else:
        kb.add(Callback("Включить память ИИ", payload={"cmd": "admin_cmd", "action": "toggle_tag_memory"}), color=KeyboardButtonColor.POSITIVE)

    kb.row()

    # Buttons for single actions
    kb.add(Callback("🧹 ОЧИСТИТЬ REDIS", payload={"cmd": "admin_cmd", "action": "clear_redis"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("⚡️ Выдать Энергию"), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("📢 Призыв Синдиката"), color=KeyboardButtonColor.PRIMARY)

    from modules.bot_init import bot
    await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=0)

async def process_admin_cmd(vk_id: int, peer_id: int, payload: dict):
    if vk_id != ADMIN_ID:
        return

    action = payload.get("action")
    from modules.bot_init import bot
    import asyncio

    if action == "toggle_warmup":
        current = await redis_client.get("system_config:warmup_active")
        new_val = 0 if current and int(current) == 1 else 1
        await redis_client.set("system_config:warmup_active", str(new_val))

        if new_val == 1:
            await bot.api.messages.send(peer_id=peer_id, message="Инициализация вербовки ассетов запущена. Медленное якорение начато.", random_id=0)
            asyncio.create_task(warmup_task())
        else:
            await bot.api.messages.send(peer_id=peer_id, message="Потоки синхронизации заморожены. Матрица работает на текущем кэше.", random_id=0)

    elif action == "toggle_maintenance":
        current = await redis_client.get("system_config:maintenance_mode")
        new_val = 0 if current and int(current) == 1 else 1
        await redis_client.set("system_config:maintenance_mode", str(new_val))

        if new_val == 1:
            await bot.api.messages.send(peer_id=peer_id, message="Синдикат перешел в тень. Идет калибровка матрицы.", random_id=0)
        else:
            await bot.api.messages.send(peer_id=peer_id, message="Матрица снова активна для всех.", random_id=0)

    elif action == "toggle_tag_memory":
        current = await redis_client.get("system_config:tag_memory_active")
        new_val = 0 if current and int(current) == 1 else 1
        await redis_client.set("system_config:tag_memory_active", str(new_val))

        if new_val == 1:
            await bot.api.messages.send(peer_id=peer_id, message="Теговая память ИИ включена.", random_id=0)
        else:
            await bot.api.messages.send(peer_id=peer_id, message="Теговая память ИИ отключена.", random_id=0)

    elif action == "clear_redis":
        await clear_photo_cache()
        await bot.api.messages.send(peer_id=peer_id, message="Кэш фото в Redis очищен.", random_id=0)

    # Re-render console
    await show_admin_console(peer_id)

@labeler.message(text=["⚡️ Выдать Энергию"])
async def admin_energy_start(message: Message):
    if message.from_id != ADMIN_ID:
        return

    await set_fsm_state(message.from_id, json.dumps({"step": "admin_energy_target"}))
    await message.answer("Введите ID пользователя и количество энергии через пробел (например: 123456 500), или напишите Отмена",
                         keyboard=Keyboard(inline=True).add(Text("Отмена", payload={"cmd": "admin_cmd_cancel"})).get_json())

@labeler.message(text=["📢 Призыв Синдиката"])
async def admin_broadcast_start(message: Message):
    if message.from_id != ADMIN_ID:
        return

    await set_fsm_state(message.from_id, json.dumps({"step": "admin_broadcast_message"}))
    await message.answer("Отправьте сообщение для рассылки всем адептам, или напишите Отмена",
                         keyboard=Keyboard(inline=True).add(Text("Отмена", payload={"cmd": "admin_cmd_cancel"})).get_json())


async def _is_admin_fsm(message: Message) -> bool:
    if message.from_id != ADMIN_ID:
        return False
    from modules.utils import get_fsm_step
    fsm_data = await get_fsm_step(message.from_id)
    if not fsm_data:
        return False
    step = fsm_data.get("step")
    return step in ["admin_energy_target", "admin_broadcast_message"]

@labeler.message(func=_is_admin_fsm)
async def admin_fsm_handler(message: Message):


    from modules.utils import get_fsm_step
    fsm_data = await get_fsm_step(message.from_id)
    if not fsm_data:
        return False

    step = fsm_data.get("step")

    if message.text.lower() == "отмена":
        await set_fsm_state(message.from_id, "")
        await message.answer("Действие отменено.")
        await show_admin_console(message.peer_id)
        return True

    if step == "admin_energy_target":
        parts = message.text.strip().split()
        if len(parts) != 2:
            await message.answer("Неверный формат. Нужно: ID КОЛИЧЕСТВО")
            return True

        try:
            target_id = int(parts[0])
            amount = int(parts[1])
        except ValueError:
            await message.answer("Неверный формат. ID и Количество должны быть числами.")
            return True

        from database import get_user, update_user
        target_user = await get_user(target_id)
        if not target_user:
            await message.answer(f"Пользователь {target_id} не найден.")
            return True

        new_balance = int(target_user.get("balance", 0) or 0) + amount
        await update_user(target_id, {"balance": new_balance})

        await set_fsm_state(message.from_id, "")
        await message.answer(f"Пользователю {target_id} выдано {amount} Энергии звезд. Новый баланс: {new_balance}.")

        from modules.bot_init import bot
        try:
            await bot.api.messages.send(
                peer_id=target_id,
                message=f"⚡️ Магистр Синдиката даровал вам {amount} Энергии звезд!\nВаш баланс: {new_balance}",
                random_id=0,
                keyboard=get_dynamic_keyboard(target_user)
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю: {e}")

        return True

    elif step == "admin_broadcast_message":
        text = message.text.strip()
        await set_fsm_state(message.from_id, "")

        users = await get_all_users()
        success = 0
        from modules.bot_init import bot
        import asyncio

        await message.answer(f"Начинаю рассылку для {len(users)} пользователей...")

        for u in users:
            try:
                await bot.api.messages.send(
                    peer_id=u["vk_id"],
                    message=f"📢 ПРИЗЫВ СИНДИКАТА 📢\n\n{text}",
                    random_id=0
                )
                success += 1
                await asyncio.sleep(0.1) # prevent flood
            except Exception:
                pass

        await message.answer(f"Рассылка завершена. Успешно доставлено: {success}/{len(users)}")
        return True

    return False
