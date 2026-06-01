import ipaddress
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

    if event == "payment.succeeded" and payment_obj.get("status") == "succeeded":
        metadata = payment_obj.get("metadata", {})
        user_id_str = metadata.get("user_id")
        payment_id = payment_obj.get("id")

        if not user_id_str:
            logger.error("Yookassa missing user_id in metadata")
            return web.Response(status=200)

        user_id = int(user_id_str)
        amount_rub = int(float(payment_obj["amount"]["value"]))
        energy_bonus = amount_rub * 10

        # Проверка на дубликаты и логгирование в БД
        from database import add_energy, add_event, is_first_payment

        # Используем Redis для быстрой проверки на дубликаты вебхука (на 24 часа)
        from cache import redis_client
        lock_key = f"yookassa_processed:{payment_id}"
        if await redis_client.set(lock_key, "1", ex=86400, nx=True):
            if await add_energy(user_id, energy_bonus):
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

            try:
                from modules.bot_init import bot
                from modules.keyboards import get_main_keyboard
                push_text = f"✨ БАЛАНС ПОПОЛНЕН! ✨\nЗачислено {energy_bonus} Энергии звезд за оплату {amount_rub} RUB.\nПроводники приветствуют тебя!"
                await bot.api.messages.send(peer_id=user_id, message=push_text, random_id=0, keyboard=get_main_keyboard(user_id))
            except Exception as push_err:
                logger.error(f"Failed to send VK payment push notification: {push_err}")

    return web.Response(status=200, text="OK")
