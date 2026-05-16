import json
import os
import datetime
import asyncio
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

from cache import redis_client, set_fsm_state
from database import get_all_users, get_user, update_user, get_user_count
from modules.utils import ADMIN_ID, clear_photo_cache, ghost_edit, get_fsm_step
from modules.bot_init import bot

labeler = BotLabeler()

# ==================== НАВИГАЦИЯ ====================

@labeler.message(text=["⚙️ КОНСОЛЬ МАГИСТРА", "админка"])
@labeler.message(payload={"cmd": "admin_console"})
async def admin_console_handler(message: Message):
    if message.from_id != ADMIN_ID:
        return
    await show_admin_main(message.peer_id)

async def show_admin_main(peer_id: int, conversation_message_id: int = None):
    """Главная страница консоли"""
    user_count = await get_user_count()

    text = (
        "⚙️ КОНСОЛЬ МАГИСТРА: ГЛАВНАЯ ⚙️\n\n"
        "Добро пожаловать в центр управления матрицей.\n"
        f"👥 Всего адептов: {user_count}\n\n"
        "Выберите раздел для глубокой настройки:"
    )

    kb = Keyboard(inline=True)
    kb.add(Callback("💻 СИСТЕМА", payload={"cmd": "admin_nav", "menu": "system"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("📈 АНАЛИТИКА", payload={"cmd": "admin_nav", "menu": "analytics"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("👥 АДЕПТЫ", payload={"cmd": "admin_nav", "menu": "users"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("📢 ВЕЩАНИЕ", payload={"cmd": "admin_nav", "menu": "broadcast"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("💎 VIP ХАБ", payload={"cmd": "admin_nav", "menu": "vip"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("📜 ЛОГИ", payload={"cmd": "admin_nav", "menu": "logs"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("🏠 ВЫХОД", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_system(peer_id: int, conversation_message_id: int = None):
    """Раздел системных настроек"""
    warmup_active = await redis_client.get("system_config:warmup_active")
    warmup_active = bool(int(warmup_active)) if warmup_active else False

    maintenance_mode = await redis_client.get("system_config:maintenance_mode")
    maintenance_mode = bool(int(maintenance_mode)) if maintenance_mode else False

    tag_memory_active = await redis_client.get("system_config:tag_memory_active")
    tag_memory_active = bool(int(tag_memory_active)) if tag_memory_active is not None else True

    try:
        keys = await redis_client.keys("photo:*")
        cache_count = len(keys)
    except:
        cache_count = -1

    text = (
        "💻 СИСТЕМНЫЕ НАСТРОЙКИ\n\n"
        f"🖼 АССЕТОВ В КЭШЕ: {cache_count}\n"
        "--------------------------\n"
        f"ФОНОВЫЙ ПРОГРЕВ: {'🟢 ВКЛ' if warmup_active else '🔴 ВЫКЛ'}\n"
        "- ПРЕДВАРИТЕЛЬНАЯ ЗАГРУЗКА КАРТ В VK ДЛЯ СКОРОСТИ\n\n"
        f"РЕЖИМ ТЕХ. РАБОТ: {'🔴 АКТИВЕН' if maintenance_mode else '🟢 ВЫКЛ'}\n"
        "- БЛОКИРУЕТ ДОСТУП ВСЕМ, КРОМЕ АДМИНИСТРАТОРА\n\n"
        f"ТЕГОВАЯ ПАМЯТЬ ИИ: {'🟢 ВКЛ' if tag_memory_active else '🔴 ВЫКЛ'}\n"
        "- СОХРАНЕНИЕ КОНТЕКСТА ПРОШЛЫХ ГАДАНИЙ\n"
    )

    kb = Keyboard(inline=True)

    # Warmup
    label = "🔴 СТОП ПРОГРЕВ" if warmup_active else "🟢 СТАРТ ПРОГРЕВ"
    kb.add(Callback(label, payload={"cmd": "admin_cmd", "action": "toggle_warmup"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()

    # Maintenance
    label = "🟢 ВЫКЛ ТЕХРАБОТЫ" if maintenance_mode else "🛠 ВКЛ ТЕХРАБОТЫ"
    kb.add(Callback(label, payload={"cmd": "admin_cmd", "action": "toggle_maintenance"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()

    # Memory
    label = "🧠 ВЫКЛ ПАМЯТЬ" if tag_memory_active else "🧠 ВКЛ ПАМЯТЬ"
    kb.add(Callback(label, payload={"cmd": "admin_cmd", "action": "toggle_tag_memory"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()

    kb.add(Callback("🧹 ОЧИСТИТЬ REDIS", payload={"cmd": "admin_cmd", "action": "clear_redis"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()

    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)

    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_analytics(peer_id: int, conversation_message_id: int = None):
    """Раздел аналитики"""
    cached_stats = await redis_client.get("admin:analytics_cache")
    if cached_stats:
        stats = json.loads(cached_stats)
    else:
        users = await get_all_users()
        total_users = len(users)
        now = datetime.datetime.now(datetime.timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        new_today, total_balance, active_today, revenue_est = 0, 0, 0, 0
        purchased_stats = {}
        for u in users:
            total_balance += int(u.get("balance", 0) or 0)
            created_at_str = u.get("created_at")
            if created_at_str:
                try:
                    created_at = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if created_at >= today_start: new_today += 1
                except: pass
            purchased = u.get("purchased_sections", {})
            for key, val in purchased.items():
                if val is True:
                    purchased_stats[key] = purchased_stats.get(key, 0) + 1
                    prices = {"sex": 1000, "money": 900, "shadow": 700, "final": 1200, "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500}
                    revenue_est += prices.get(key, 0)
            last_active = u.get("last_active_date")
            if last_active:
                try:
                    la_date = datetime.datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    if la_date >= today_start: active_today += 1
                except: pass
        stats = {"total_users": total_users, "new_today": new_today, "active_today": active_today, "total_balance": total_balance, "revenue_est": revenue_est, "purchased_stats": purchased_stats}
        await redis_client.set("admin:analytics_cache", json.dumps(stats), ex=600)

    total_users, new_today, active_today, total_balance, revenue_est, purchased_stats = stats["total_users"], stats["new_today"], stats["active_today"], stats["total_balance"], stats["revenue_est"], stats["purchased_stats"]
    conversion_rate = (new_today / active_today * 100) if active_today > 0 else 0
    stats_text = (
        "📈 АНАЛИТИКА МАТРИЦЫ\n\n"
        f"👥 ВСЕГО АДЕПТОВ: {total_users}\n"
        f"✨ НОВЫХ СЕГОДНЯ: {new_today}\n"
        f"🔥 АКТИВНЫХ СЕГОДНЯ: {active_today}\n"
        f"📊 КОНВЕРСИЯ: {conversion_rate:.1f}%\n"
        f"💰 ЭСТИМЕЙТ ВЫРУЧКИ: ~{revenue_est} RUB\n"
        f"🔋 БАНК ЭНЕРГИИ: {total_balance} ✨\n\n"
        "🔥 ТОП УСЛУГ:\n"
    )
    for key, count in sorted(purchased_stats.items(), key=lambda x: x[1], reverse=True)[:5]:
        stats_text += f"- {key.upper()}: {count}\n"
    kb = Keyboard(inline=True).add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, stats_text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_users(peer_id: int, conversation_message_id: int = None):
    """Раздел управления пользователями"""
    text = (
        "👥 УПРАВЛЕНИЕ АДЕПТАМИ\n\n"
        "Здесь вы можете найти конкретного пользователя для ручной коррекции его судьбы.\n\n"
        "Используйте кнопки ниже для поиска или массовых действий."
    )
    kb = Keyboard(inline=True)
    kb.add(Callback("🔍 НАЙТИ ПО ID", payload={"cmd": "admin_cmd", "action": "search_user_start"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("⚡️ ВЫДАТЬ ЭНЕРГИЮ", payload={"cmd": "admin_cmd", "action": "mass_energy_start"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_broadcast(peer_id: int, conversation_message_id: int = None):
    """Раздел рассылки"""
    text = (
        "📢 ПРИЗЫВ СИНДИКАТА (РАССЫЛКА)\n\n"
        "Сообщение будет отправлено всем зарегистрированным адептам.\n"
        "Используйте с осторожностью, чтобы не нарушить баланс матрицы."
    )
    kb = Keyboard(inline=True)
    kb.add(Callback("📝 СОЗДАТЬ ПРИЗЫВ", payload={"cmd": "admin_cmd", "action": "broadcast_start"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_vip(peer_id: int, conversation_message_id: int = None):
    """Раздел управления VIP-клиентами"""
    users = await get_all_users()
    vip_users = [u for u in users if u.get("has_full_chart") or (u.get("balance", 0) or 0) > 5000]
    text = (
        "💎 VIP ХАБ: УПРАВЛЕНИЕ ЭЛИТОЙ 💎\n\n"
        f"Количество VIP-адептов: {len(vip_users)}\n"
        "--------------------------\n"
        "VIP-статус имеют те, у кого открыт полный архив или баланс > 5000 ✨.\n\n"
        "Выберите действие:"
    )
    kb = Keyboard(inline=True)
    kb.add(Callback("👑 СПИСОК VIP", payload={"cmd": "admin_cmd", "action": "list_vips"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🎁 ВЫДАТЬ VIP", payload={"cmd": "admin_cmd", "action": "search_user_start"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_logs(peer_id: int, conversation_message_id: int = None):
    """Просмотр последних логов"""
    log_dir, log_text = "logs", ""
    try:
        files = [f for f in os.listdir(log_dir) if f.startswith("bot_") and f.endswith(".log")]
        if not files: log_text = "Логи не найдены."
        else:
            latest_file = sorted(files)[-1]
            with open(os.path.join(log_dir, latest_file), "r", encoding="utf-8") as f:
                lines = f.readlines()
                log_text = "".join(lines[-15:])
    except Exception as e: log_text = f"Ошибка при чтении логов: {e}"
    text = f"📜 ПОСЛЕДНИЕ СОБЫТИЯ:\n\n{log_text}"
    kb = Keyboard(inline=True)
    kb.add(Callback("🔄 ОБНОВИТЬ", payload={"cmd": "admin_nav", "menu": "logs"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)


# ==================== ОБРАБОТКА КОМАНД ====================

async def process_admin_cmd(vk_id: int, peer_id: int, payload: dict, conversation_message_id: int = None):
    if vk_id != ADMIN_ID: return
    action, nav_menu = payload.get("action"), payload.get("menu")
    if payload.get("cmd") == "admin_nav":
        if nav_menu == "main": await show_admin_main(peer_id, conversation_message_id)
        elif nav_menu == "system": await show_admin_system(peer_id, conversation_message_id)
        elif nav_menu == "analytics": await show_admin_analytics(peer_id, conversation_message_id)
        elif nav_menu == "users": await show_admin_users(peer_id, conversation_message_id)
        elif nav_menu == "broadcast": await show_admin_broadcast(peer_id, conversation_message_id)
        elif nav_menu == "logs": await show_admin_logs(peer_id, conversation_message_id)
        elif nav_menu == "vip": await show_admin_vip(peer_id, conversation_message_id)
        return
    if action == "toggle_warmup":
        c = await redis_client.get("system_config:warmup_active")
        nv = 0 if c and int(c) == 1 else 1
        await redis_client.set("system_config:warmup_active", str(nv))
        if nv == 1:
            from modules.utils import warmup_task
            asyncio.create_task(warmup_task())
        await show_admin_system(peer_id, conversation_message_id)
    elif action == "toggle_maintenance":
        c = await redis_client.get("system_config:maintenance_mode")
        nv = 0 if c and int(c) == 1 else 1
        await redis_client.set("system_config:maintenance_mode", str(nv))
        await show_admin_system(peer_id, conversation_message_id)
    elif action == "toggle_tag_memory":
        c = await redis_client.get("system_config:tag_memory_active")
        nv = 0 if c and int(c) == 1 else 1
        await redis_client.set("system_config:tag_memory_active", str(nv))
        await show_admin_system(peer_id, conversation_message_id)
    elif action == "list_vips":
        users = await get_all_users()
        vips = [u for u in users if u.get("has_full_chart") or (u.get("balance", 0) or 0) > 5000]
        text = "💎 СПИСОК VIP-АДЕПТОВ:\n\n"
        for u in vips[:20]: text += f"- ID: {u['vk_id']} | {u.get('balance', 0)} ✨ | {'FULL' if u.get('has_full_chart') else 'RICH'}\n"
        if not vips: text += "VIP-адепты не обнаружены."
        kb = Keyboard(inline=True).add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "vip"}), color=KeyboardButtonColor.PRIMARY)
        await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)
    elif action == "clear_redis":
        await clear_photo_cache()
        await bot.api.messages.send(peer_id=peer_id, message="Кэш фото в Redis очищен.", random_id=0)
        await show_admin_system(peer_id, conversation_message_id)
    elif action == "search_user_start":
        await set_fsm_state(vk_id, json.dumps({"step": "admin_user_search", "conv_id": conversation_message_id}))
        await bot.api.messages.send(peer_id=peer_id, message="Введите VK ID адепта для поиска:", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "users"})).get_json(), random_id=0)
    elif action == "broadcast_start":
        await set_fsm_state(vk_id, json.dumps({"step": "admin_broadcast_message", "conv_id": conversation_message_id}))
        await bot.api.messages.send(peer_id=peer_id, message="📝 Введите текст призыва (рассылки).\n\nОн будет отправлен всем адептам Синдиката.", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "broadcast"})).get_json(), random_id=0)
    elif action == "broadcast_confirm":
        bt = await redis_client.get(f"admin:broadcast_text:{vk_id}")
        if not bt:
            await bot.api.messages.send(peer_id=peer_id, message="❌ Текст призыва утерян. Начните заново.", random_id=0)
            await show_admin_broadcast(peer_id, conversation_message_id)
            return
        bt = bt.decode('utf-8') if isinstance(bt, bytes) else bt
        await bot.api.messages.send(peer_id=peer_id, message="🚀 Запуск трансмиссии...", random_id=0)
        users = await get_all_users()
        success = 0
        for u in users:
            try:
                await bot.api.messages.send(peer_id=u["vk_id"], message=f"📢 ПРИЗЫВ СИНДИКАТА 📢\n\n{bt}", random_id=0)
                success += 1
                await asyncio.sleep(0.05)
            except: pass
        await bot.api.messages.send(peer_id=peer_id, message=f"✅ Рассылка завершена. Доставлено: {success}/{len(users)}", random_id=0)
        await show_admin_broadcast(peer_id, conversation_message_id)
    elif action == "mass_energy_start":
        await set_fsm_state(vk_id, json.dumps({"step": "admin_energy_target", "conv_id": conversation_message_id}))
        await bot.api.messages.send(peer_id=peer_id, message="Введите ID и количество энергии через пробел (например: 12345 500):", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "users"})).get_json(), random_id=0)
    elif payload.get("cmd") == "admin_user_op":
        op, target = payload.get("op"), payload.get("target")
        if op == "edit_balance":
            await set_fsm_state(vk_id, json.dumps({"step": "admin_user_edit_balance", "target": target, "conv_id": conversation_message_id}))
            await bot.api.messages.send(peer_id=peer_id, message=f"Введите НОВОЕ значение баланса для {target}:", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "users"})).get_json(), random_id=0)
        elif op == "full_unlock":
            user = await get_user(target)
            if user:
                p = user.get("purchased_sections", {})
                for s in ["sex", "money", "shadow", "final", "synastry", "antitaro"]: p[s] = True
                await update_user(target, {"purchased_sections": p, "has_full_chart": True})
                await bot.api.messages.send(peer_id=peer_id, message=f"✅ Все услуги разблокированы для {target}", random_id=0)
                await bot.api.messages.send(peer_id=target, message="🌟 Магистр даровал вам полный доступ ко всем тайнам Синдиката!", random_id=0)
                await show_admin_users(peer_id, conversation_message_id)
        elif op == "give_card_start":
            await set_fsm_state(vk_id, json.dumps({"step": "admin_user_give_card", "target": target, "conv_id": conversation_message_id}))
            await bot.api.messages.send(peer_id=peer_id, message=f"Введите ID карты (0-77) для выдачи адепту {target}:", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "users"})).get_json(), random_id=0)

async def _is_admin_fsm(message: Message) -> bool:
    if message.from_id != ADMIN_ID: return False
    fsm_data = await get_fsm_step(message.from_id)
    if not fsm_data: return False
    return fsm_data.get("step") in ["admin_user_search", "admin_broadcast_message", "admin_energy_target", "admin_user_edit_balance", "admin_user_give_card"]

@labeler.message(func=_is_admin_fsm)
async def admin_fsm_handler(message: Message):
    fsm_data = await get_fsm_step(message.from_id)
    step, vk_id, conv_id = fsm_data.get("step"), message.from_id, fsm_data.get("conv_id")
    if message.text.lower() == "отмена":
        await set_fsm_state(vk_id, "")
        await show_admin_main(message.peer_id, conv_id)
        return
    if step == "admin_user_search":
        try:
            target_id = int(message.text.strip())
            user = await get_user(target_id)
            if not user:
                await message.answer("Адепт не найден в матрице.")
                return
            await set_fsm_state(vk_id, "")
            purchased, skins, has_full = user.get("purchased_sections", {}), user.get("purchased_skins", []), user.get("has_full_chart", False)
            text = (f"👤 ПРОФИЛЬ АДЕПТА: {target_id}\nИмя: {user.get('first_name', '???')}\nБаланс: {user.get('balance', 0)} ✨\nСкины: {', '.join(skins) if skins else 'нет'}\nУслуги: {sum(1 for v in purchased.values() if v is True)}\nFull Chart: {'✅' if has_full else '❌'}\nЗарегистрирован: {user.get('created_at', '???')}")
            kb = Keyboard(inline=True)
            kb.add(Callback("⚡️ БАЛАНС", payload={"cmd": "admin_user_op", "op": "edit_balance", "target": target_id}), color=KeyboardButtonColor.PRIMARY)
            kb.row()
            kb.add(Callback("👑 FULL UNLOCK", payload={"cmd": "admin_user_op", "op": "full_unlock", "target": target_id}), color=KeyboardButtonColor.POSITIVE)
            kb.row()
            kb.add(Callback("🎁 КАРТА", payload={"cmd": "admin_user_op", "op": "give_card_start", "target": target_id}), color=KeyboardButtonColor.SECONDARY)
            kb.row()
            kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "users"}), color=KeyboardButtonColor.SECONDARY)
            await ghost_edit(bot.api, message.peer_id, text, keyboard=kb.get_json(), conversation_message_id=conv_id)
        except ValueError: await message.answer("Введите корректный числовой ID.")
    elif step == "admin_user_edit_balance":
        try:
            target_id, new_bal = fsm_data.get("target"), int(message.text.strip())
            await update_user(target_id, {"balance": new_bal})
            await set_fsm_state(vk_id, "")
            await message.answer(f"Баланс пользователя {target_id} изменен на {new_bal} ✨")
            await show_admin_users(message.peer_id, conv_id)
        except: await message.answer("Введите число.")
    elif step == "admin_user_give_card":
        try:
            target_id, card_id = fsm_data.get("target"), str(int(message.text.strip()))
            user = await get_user(target_id)
            if not user: return
            unlocked = user.get("unlocked_cards", {})
            from cards_data import get_card_data
            card_data = get_card_data(card_id)
            if not card_data:
                await message.answer("Такой карты не существует.")
                return
            unlocked[card_id] = f"{card_data.get('name')} - ДАР МАГИСТРА"
            await update_user(target_id, {"unlocked_cards": unlocked})
            await set_fsm_state(vk_id, "")
            await message.answer(f"✅ Карта {card_id} выдана адепту {target_id}")
            await bot.api.messages.send(peer_id=target_id, message=f"🎁 Магистр Синдиката даровал вам новую карту в Гримуар: {card_data.get('name')}!", random_id=0)
            await show_admin_users(message.peer_id, conv_id)
        except: await message.answer("Введите число ID карты (0-77).")
    elif step == "admin_energy_target":
        parts = message.text.strip().split()
        if len(parts) != 2:
            await message.answer("Формат: ID КОЛИЧЕСТВО")
            return
        try:
            target_id, amount = int(parts[0]), int(parts[1])
            target_user = await get_user(target_id)
            if not target_user:
                await message.answer("Пользователь не найден.")
                return
            new_balance = int(target_user.get("balance", 0) or 0) + amount
            await update_user(target_id, {"balance": new_balance})
            await set_fsm_state(vk_id, "")
            await message.answer(f"Зачислено {amount} ✨ пользователю {target_id}. Итого: {new_balance}")
            try: await bot.api.messages.send(peer_id=target_id, message=f"⚡️ Магистр даровал вам {amount} Энергии звезд!\nВаш баланс: {new_balance}", random_id=0)
            except: pass
            await show_admin_users(message.peer_id, conv_id)
        except: await message.answer("Ошибка в числах.")
    elif step == "admin_broadcast_message":
        text = message.text.strip()
        await set_fsm_state(vk_id, "")
        await redis_client.set(f"admin:broadcast_text:{vk_id}", text, ex=3600)
        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ПОДТВЕРДИТЬ", payload={"cmd": "admin_cmd", "action": "broadcast_confirm"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("❌ ОТМЕНА", payload={"cmd": "admin_nav", "menu": "broadcast"}), color=KeyboardButtonColor.NEGATIVE)
        await ghost_edit(bot.api, message.peer_id, f"ПРЕВЬЮ ПРИЗЫВА:\n\n📢 ПРИЗЫВ СИНДИКАТА 📢\n\n{text}\n\nОтправить всем адептам?", keyboard=kb.get_json(), conversation_message_id=conv_id)

async def show_admin_console(peer_id: int, conversation_message_id: int = None):
    await show_admin_main(peer_id, conversation_message_id=conversation_message_id)
