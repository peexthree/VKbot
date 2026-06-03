import ipaddress
import json
import os
import uuid
from aiohttp import web, ClientSession, BasicAuth
from loguru import logger

SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# Официальные подсети и IP-адреса ЮKassa для валидации запросов
YOOKASSA_TRUSTED_NETWORKS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25")
]
YOOKASSA_TRUSTED_IPS = [
    ipaddress.ip_address("77.75.156.11"),
    ipaddress.ip_address("77.75.156.35")
]

def verify_yookassa_ip(ip_str: str) -> bool:
    """Проверяет, что вебхук пришел именно от серверов ЮKassa"""
    try:
        # X-Forwarded-For может содержать несколько IP через запятую
        client_ip = ipaddress.ip_address(ip_str.split(",")[0].strip())
        if client_ip in YOOKASSA_TRUSTED_IPS:
            return True
        for network in YOOKASSA_TRUSTED_NETWORKS:
            if client_ip in network:
                return True
        return False
    except Exception as e:
        logger.error(f"IP validation error: {e}")
        return False

async def create_yookassa_payment(amount: int, description: str, user_id: int) -> str | None:
    """Создаёт платёж в ЮKassa и возвращает URL для перенаправления"""
    if not SHOP_ID or not SECRET_KEY:
        logger.error("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не настроены в .env")
        return None

    idempotency_key = str(uuid.uuid4())
    payload = {
        "amount": {
            "value": f"{amount}.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://vk.com/im?sel={user_id}"
        },
        "capture": True,
        "description": description[:128],
        "metadata": {
            "user_id": str(user_id)
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Idempotence-Key": idempotency_key
    }

    async with ClientSession() as session:
        try:
            async with session.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                headers=headers,
                auth=BasicAuth(SHOP_ID, SECRET_KEY),
                timeout=15
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    return data["confirmation"]["confirmation_url"]
                else:
                    text = await resp.text()
                    logger.error(f"Yookassa API error: {resp.status} - {text}")
                    return None
        except Exception as e:
            logger.exception(f"Exception during Yookassa payment creation: {e}")
            return None

async def yookassa_webhook(request: web.Request):
    """Webhook приемник платежей ЮKassa с IP-фильтрацией"""
    forwarded_ip = request.headers.get("X-Forwarded-For") or request.remote
    if not forwarded_ip or not verify_yookassa_ip(forwarded_ip):
        logger.warning(f"Unauthorized Yookassa webhook attempt from IP: {forwarded_ip}")
        return web.Response(status=403, text="Access Denied")

    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Yookassa JSON payload: {e}")
        return web.Response(status=400, text="Invalid JSON")

    event = data.get("event")
    payment_obj = data.get("object", {})

    # Безопасное логирование (без PII)
    safe_log_data = {
        "event": event,
        "id": payment_obj.get("id"),
        "status": payment_obj.get("status"),
        "amount": payment_obj.get("amount"),
        "metadata": payment_obj.get("metadata")
    }
    logger.info(f"Yookassa webhook received: {safe_log_data}")

    if event == "payment.succeeded" and payment_obj.get("status") == "succeeded":
        metadata = payment_obj.get("metadata", {})
        user_id_str = metadata.get("user_id")
        payment_id = payment_obj.get("id")

        if not user_id_str:
            logger.error(f"Yookassa missing user_id in metadata for payment {payment_id}")
            return web.Response(status=200)

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            logger.error(f"Invalid user_id format in metadata: {user_id_str}")
            return web.Response(status=200)

        # Проверка на дубликаты (БД + Redis для скорости)
        from database import add_energy, add_event, is_first_payment, get_user, is_payment_processed, mark_payment_as_processed
        from cache import redis_client

        # 1. Проверка в БД (постоянная защита)
        if await is_payment_processed(payment_id):
            logger.warning(f"Payment {payment_id} already processed (DB check)")
            return web.Response(status=200)

        # 2. Redis lock (защита от одновременных запросов)
        lock_key = f"yookassa_lock:{payment_id}"
        if not await redis_client.set(lock_key, "1", ex=60, nx=True):
            logger.warning(f"Payment {payment_id} is being processed right now (Redis lock)")
            return web.Response(status=200)

        # 3. Валидация существования пользователя
        user = await get_user(user_id)
        if not user:
            logger.warning(f"Unauthorized payment attempt for non-existent user_id: {user_id}")
            return web.Response(status=200)

        amount_rub = int(float(payment_obj["amount"]["value"]))
        energy_bonus = amount_rub * 10

        # Атомарное начисление
        if await add_energy(user_id, energy_bonus):
            # Помечаем как обработанный в БД
            await mark_payment_as_processed(payment_id)

            logger.info(f"ЮKassa УСПЕХ: Начислено {energy_bonus} энергии пользователю vk_id={user_id}")

            # Логгируем событие в таблицу events
            ev_metadata = {
                "payment_id": payment_id,
                "amount": amount_rub,
                "payment_method": "yookassa"
            }
            await add_event(user_id, "energy_purchased", ev_metadata)
            await add_event(user_id, "yookassa_transaction", ev_metadata)

            if await is_first_payment(user_id):
                await add_event(user_id, "first_payment", ev_metadata)

            # Уведомление пользователю (через инлайн-кнопку для пуша)
            try:
                from modules.bot_init import bot
                from modules.utils.consts import SKIN_DISPLAY_NAMES
                active_skin = user.get("active_skin", "olesya")
                character_name = SKIN_DISPLAY_NAMES.get(active_skin, "Твой Проводник")
                push_text = f"✨ БАЛАНС ПОПОЛНЕН! ✨\nЗачислено {energy_bonus} Энергии звезд за оплату {amount_rub} RUB.\n{character_name} приветствует тебя!"

                # Ручное создание клавиатуры во избежание циклического импорта
                keyboard = {
                    "one_time": False,
                    "inline": True,
                    "buttons": [[{
                        "action": {
                            "type": "callback",
                            "label": "🏠 ГЛАВНОЕ МЕНЮ",
                            "payload": json.dumps({"cmd": "main_menu"})
                        },
                        "color": "primary"
                    }]]
                }

                await bot.api.messages.send(
                    peer_id=user_id,
                    message=push_text,
                    random_id=0,
                    keyboard=json.dumps(keyboard)
                )
            except Exception as push_err:
                logger.error(f"Failed to send VK payment push notification: {push_err}")

    return web.Response(status=200, text="OK")
