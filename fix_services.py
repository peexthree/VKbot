import re

with open('modules/services.py', 'r') as f:
    content = f.read()

replacement = '''@labeler.message(text=["✦ Услуги", "Услуги", "✦ УСЛУГИ 🛒"])
async def show_services_handler(message: Message):
    await show_services(message.from_id, message.peer_id, 0)

async def show_services(vk_id: int, peer_id: int, idx: int = 0):
    import json
    from database import set_user_state
    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        try:
            await bot.api.messages.send(peer_id=peer_id, message="ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.", random_id=0)
        except Exception:
            pass
        return

    services = [
        {
            "key": "sex",
            "title": "Твоя сексуальная энергия",
            "desc": "Что это даст: Глубокое понимание своих истинных желаний и блоков в интимной сфере.\\nКак это работает: Расклад на картах с анализом твоей матрицы страсти.\\nВремя подготовки: 1 минута.\\n\\nИнструкция: Нажми кнопку Купить. После этого ты выберешь карту для настройки системы. Я подготовлю твой личный архив в формате PDF в течение минуты.",
            "price_text": "100 РУБ",
            "image_name": "sex1.jpg"
        },
        {
            "key": "money",
            "title": "Код твоего богатства",
            "desc": "Что это даст: Понимание, как пробить финансовый потолок и привлечь деньги в свою жизнь.\\nКак это работает: Анализ финансового потока и твоих скрытых возможностей.\\nВремя подготовки: 1 минута.\\n\\nИнструкция: Нажми кнопку Купить. После этого ты выберешь карту для настройки системы. Я подготовлю твой личный архив в формате PDF в течение минуты.",
            "price_text": "90 РУБ",
            "image_name": "money1.jpg"
        },
        {
            "key": "shadow",
            "title": "Твои скрытые грани",
            "desc": "Что это даст: Раскрытие подавленных эмоций и теневых сторон личности, мешающих росту.\\nКак это работает: Работа с подсознанием через темные арканы.\\nВремя подготовки: 1 минута.\\n\\nИнструкция: Нажми кнопку Купить. После этого ты выберешь карту для настройки системы. Я подготовлю твой личный архив в формате PDF в течение минуты.",
            "price_text": "70 РУБ",
            "image_name": "demon1.jpg"
        },
        {
            "key": "final",
            "title": "Твой истинный путь",
            "desc": "Что это даст: Осознание своего предназначения и глобального вектора развития.\\nКак это работает: Полный расклад на жизненный путь и кармические задачи.\\nВремя подготовки: 1 минута.\\n\\nИнструкция: Нажми кнопку Купить. После этого ты выберешь карту для настройки системы. Я подготовлю твой личный архив в формате PDF в течение минуты.",
            "price_text": "120 РУБ",
            "image_name": "way1.jpg"
        },
        {
            "key": "synastry",
            "title": "Тайна ваших отношений",
            "desc": "Что это даст: Полный разбор совместимости с партнером, сильные и слабые стороны союза.\\nКак это работает: Жесткий разбор мэтча с партнером.\\nВремя подготовки: 1 минута.\\n\\nИнструкция: Нажми кнопку Купить. После этого ты выберешь карту для настройки системы. Я подготовлю твой личный архив в формате PDF в течение минуты.",
            "price_text": "150 РУБ",
            "image_name": "sin.jpeg"
        },
        {
            "key": "all",
            "title": "Золотой архив всех откровений",
            "desc": "Что это даст: Полный доступ ко всем тайнам твоей матрицы (Сексуальная энергия, Деньги, Скрытые грани, Истинный путь).\\nКак это работает: Комплексный анализ всех сфер жизни.\\nВремя подготовки: 1 минута.\\n\\nИнструкция: Нажми кнопку Купить. После этого ты выберешь карту для настройки системы. Я подготовлю твой личный архив в формате PDF в течение минуты.",
            "price_text": "300 РУБ",
            "image_name": "full1.jpg"
        }
    ]

    if idx < 0 or idx >= len(services):
        idx = 0

    svc = services[idx]

    msg_text = f"✦ {svc['title'].upper()} ✦\\nЦена: {svc['price_text']}\\n\\n{svc['desc']}"

    buttons = []

    # Navigation row 1
    nav_buttons = []
    if idx > 0:
        nav_buttons.append({"action": {"type": "callback", "payload": json.dumps({"cmd": "service_page", "idx": idx - 1}), "label": "⬅ НАЗАД"}, "color": "secondary"})

    nav_buttons.append({"action": {"type": "callback", "payload": json.dumps({"cmd": "buy", "type": "service", "key": svc['key']}), "label": "КУПИТЬ"}, "color": "positive"})

    if idx < len(services) - 1:
        nav_buttons.append({"action": {"type": "callback", "payload": json.dumps({"cmd": "service_page", "idx": idx + 1}), "label": "ДАЛЕЕ ➡"}, "color": "secondary"})
    else:
        nav_buttons.append({"action": {"type": "callback", "payload": json.dumps({"cmd": "tariff_page", "idx": 0}), "label": "🛰 ТАРИФЫ"}, "color": "primary"})

    buttons.append(nav_buttons)

    keyboard_obj = {
        "inline": True,
        "buttons": buttons
    }
    kb_json = json.dumps(keyboard_obj, ensure_ascii=False)

    try:
        from modules.utils import upload_local_photo
        from modules.bot_init import bot
        att = await upload_local_photo(bot.api, svc['image_name']) if svc['image_name'] else None

        if att:
            try:
                await bot.api.messages.send(peer_id=peer_id, message=msg_text, attachment=att, keyboard=kb_json, random_id=0)
            except Exception:
                await bot.api.messages.send(peer_id=peer_id, message=msg_text, attachment=att, random_id=0)
        else:
            try:
                await bot.api.messages.send(peer_id=peer_id, message=msg_text, keyboard=kb_json, random_id=0)
            except Exception:
                await bot.api.messages.send(peer_id=peer_id, message=msg_text, random_id=0)
    except Exception as e:
        print(f"Error sending service block {svc['title']}: {e}")
        try:
            await bot.api.messages.send(peer_id=peer_id, message=msg_text, random_id=0)
        except Exception:
            pass'''

# We need to replace the entire show_services function
match = re.search(r'@labeler\.message\(text=\["✦ Услуги", "Услуги", "✦ УСЛУГИ 🛒"\]\)\nasync def show_services.*?await message\.answer\("ДЛЯ ВОЗВРАТА ВОСПОЛЬЗУЙСЯ МЕНЮ"\)', content, re.DOTALL)
if match:
    content = content[:match.start()] + replacement + content[match.end():]
    with open('modules/services.py', 'w') as f:
        f.write(content)
else:
    print("Could not find show_services")
