from __future__ import annotations
import asyncio
import json
from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

from cache import redis_client, set_fsm_state , acquire_lock, release_lock
from database import get_all_users , get_user, update_user
from modules.bot_init import bot
from modules.utils import (
    get_fsm_step,
    ADMIN_ID,
    clear_photo_cache,
    get_dynamic_keyboard,
    start_dynamic_typing,
    warmup_task,
)

labeler = BotLabeler()


# ====================== КОНСОЛЬ МАГИСТРА ======================
@labeler.message(text=["⚙️ КОНСОЛЬ МАГИСТРА"])
async def admin_console_handler(message: Message):
    if message.from_id != ADMIN_ID:
        return
    await show_admin_console(message.peer_id)


async def show_admin_console(peer_id: int):
    # Читаем флаги из Redis
    warmup_active = bool(int(await redis_client.get("system_config:warmup_active") or 0))
    maintenance_mode = bool(int(await redis_client.get("system_config:maintenance_mode") or 0))
    tag_memory_active = bool(int(await redis_client.get("system_config:tag_memory_active") or 1))

    users = await get_all_users()
    user_count = len(users)

    try:
        cache_count = len(await redis_client.keys("photo:*"))
    except Exception:
        cache_count = -1

    text = (
        "⚙️ КОНСОЛЬ МАГИСТРА ⚙️\n\n"
        f"👥 Адептов в матрице: {user_count}\n"
        f"🖼 Ассетов в кэше: {cache_count}\n\n"
        f"Фоновый прогрев: {'🟢 ВКЛ' if warmup_active else '🔴 ВЫКЛ'}\n"
        f"Режим тех. работ: {'🔴 АКТИВЕН' if maintenance_mode else '🟢 ВЫКЛ'}\n"
        f"Теговая память ИИ: {'🟢 ВКЛ' if tag_memory_active else '🔴 ВЫКЛ'}"
    )

    kb = Keyboard(inline=True)
    kb.add(
        Callback(
            "🟢 ВКЛЮЧИТЬ КЭШИРОВАНИЕ" if not warmup_active else "Остановить прогрев",
            payload={"cmd": "admin_cmd", "action": "toggle_warmup"}
        ),
        color=KeyboardButtonColor.POSITIVE if not warmup_active else KeyboardButtonColor.NEGATIVE
    )
    kb.row()
    kb.add(
        Callback(
            "🛠 РЕЖИМ ТЕХ. РАБОТ" if not maintenance_mode else "Выключить Тех. Работы",
            payload={"cmd": "admin_cmd", "action": "toggle_maintenance"}
        ),
        color=KeyboardButtonColor.NEGATIVE if not maintenance_mode else KeyboardButtonColor.POSITIVE
    )
    kb.row()
    kb.add(
        Callback(
            "Включить память ИИ" if not tag_memory_active else "Отключить память ИИ",
            payload={"cmd": "admin_cmd", "action": "toggle_tag_memory"}
        ),
        color=KeyboardButtonColor.POSITIVE if not tag_memory_active else KeyboardButtonColor.NEGATIVE
    )
    kb.row()
    kb.add(Callback("🧹 ОЧИСТИТЬ REDIS", payload={"cmd": "admin_cmd", "action": "clear_redis"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("⚡️ Выдать Энергию", payload={"cmd": "admin_cmd", "action": "give_energy"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("📢 Призыв Синдиката", payload={"cmd": "admin_cmd", "action": "broadcast"}), color=KeyboardButtonColor.PRIMARY)

    await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=0)


# ====================== ОБРАБОТКА КОМАНД ======================
@labeler.callback(payload={"cmd": "admin_cmd"})
async def admin_cmd_handler(event):
    vk_id = event.user_id
    peer_id = event.peer_id
    action = event.payload.get("action")

    if vk_id != ADMIN_ID:
        return

    if not await acquire_lock(vk_id):
        return

    try:
        await start_dynamic_typing(bot.api, peer_id)

        if action == "toggle_warmup":
            current = await redis_client.get("system_config:warmup_active")
            new_val = "0" if current == "1" else "1"
            await redis_client.set("system_config:warmup_active", new_val)
            msg = "Потоки синхронизации заморожены." if new_val == "0" else "Инициализация вербовки ассетов запущена."
            await bot.api.messages.send(peer_id=peer_id, message=msg, random_id=0)
            if new_val == "1":
                asyncio.create_task(warmup_task())

        elif action == "toggle_maintenance":
            current = await redis_client.get("system_config:maintenance_mode")
            new_val = "0" if current == "1" else "1"
            await redis_client.set("system_config:maintenance_mode", new_val)
            msg = "Матрица снова активна для всех." if new_val == "0" else "Синдикат перешел в тень."
            await bot.api.messages.send(peer_id=peer_id, message=msg, random_id=0)

        elif action == "toggle_tag_memory":
            current = await redis_client.get("system_config:tag_memory_active")
            new_val = "0" if current == "1" else "1"
            await redis_client.set("system_config:tag_memory_active", new_val)
            msg = "Теговая память ИИ " + ("включена." if new_val == "1" else "отключена.")
            await bot.api.messages.send(peer_id=peer_id, message=msg, random_id=0)

        elif action == "clear_redis":
            await clear_photo_cache()
            await bot.api.messages.send(peer_id=peer_id, message="Кэш фото в Redis очищен.", random_id=0)

        elif action == "give_energy":
            await set_fsm_state(vk_id, json.dumps({"step": "admin_energy_target"}))
            kb = Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_cmd_cancel"}), color=KeyboardButtonColor.NEGATIVE)
            await bot.api.messages.send(
                peer_id=peer_id,
                message="Введите ID пользователя и количество энергии через пробел (например: 123456 500)",
                keyboard=kb.get_json(),
                random_id=0
            )
            return

        elif action == "broadcast":
            await set_fsm_state(vk_id, json.dumps({"step": "admin_broadcast_message"}))
            kb = Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_cmd_cancel"}), color=KeyboardButtonColor.NEGATIVE)
            await bot.api.messages.send(
                peer_id=peer_id,
                message="Отправьте сообщение для рассылки всем адептам",
                keyboard=kb.get_json(),
                random_id=0
            )
            return

        # После любой команды перерисовываем консоль
        await show_admin_console(peer_id)

    finally:
        await release_lock(vk_id)


# ====================== FSM АДМИНА ======================
@labeler.message(func=lambda m: m.from_id == ADMIN_ID and m.payload and m.payload.get("cmd") == "admin_cmd_cancel")
async def admin_cancel(message: Message):
    await set_fsm_state(message.from_id, "")
    await message.answer("Действие отменено.")
    await show_admin_console(message.peer_id)


@labeler.message(func=lambda m: m.from_id == ADMIN_ID)
async def admin_fsm_handler(message: Message):
    fsm_data = await get_fsm_step(message.from_id)  # используем из utils
    if not fsm_data:
        return

    step = fsm_data.get("step")
    if message.text.lower() == "отмена":
        await set_fsm_state(message.from_id, "")
        await message.answer("Действие отменено.")
        await show_admin_console(message.peer_id)
        return

    if step == "admin_energy_target":
        parts = message.text.strip().split()
        if len(parts) != 2:
            await message.answer("Неверный формат. Нужно: ID КОЛИЧЕСТВО")
            return
        try:
            target_id = int(parts[0])
            amount = int(parts[1])
        except ValueError:
            await message.answer("ID и количество должны быть числами.")
            return

        target_user = await get_user(target_id)
        if not target_user:
            await message.answer(f"Пользователь {target_id} не найден.")
            return

        new_balance = int(target_user.get("balance", 0) or 0) + amount
        await update_user(target_id, {"balance": new_balance})
        await set_fsm_state(message.from_id, "")

        await message.answer(f"Пользователю {target_id} выдано {amount} Энергии звезд. Новый баланс: {new_balance}.")
        try:
            await bot.api.messages.send(
                peer_id=target_id,
                message=f"⚡️ Магистр Синдиката даровал вам {amount} Энергии звезд!\nВаш баланс: {new_balance}",
                random_id=0,
                keyboard=get_dynamic_keyboard()
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {target_id}: {e}")

    elif step == "admin_broadcast_message":
        text = message.text.strip()
        await set_fsm_state(message.from_id, "")
        users = await get_all_users()
        await message.answer(f"Начинаю рассылку для {len(users)} пользователей...")

        success = 0
        for u in users:
            try:
                await bot.api.messages.send(
                    peer_id=u["vk_id"],
                    message=f"📢 ПРИЗЫВ СИНДИКАТА 📢\n\n{text}",
                    random_id=0
                )
                success += 1
                await asyncio.sleep(0.3)  # защита от бана
            except Exception:
                pass

        await message.answer(f"Рассылка завершена. Успешно: {success}/{len(users)}")

    await show_admin_console(message.peer_id)


# ====================== ЗАВЕРШЕНИЕ ======================
logger.info("Модуль admin.py загружен успешно")
