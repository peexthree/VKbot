import re

with open('main.py', 'r') as f:
    content = f.read()

# Make sure we add aiohttp globally if not already there, actually it's inside main()
# Let's write the patch

# 1. Update get_inline_buy_full_chart to add a dummy URL to the webhook
new_keyboard_func = """    def get_inline_buy_full_chart(user_id: int) -> str:
        from vkbottle import OpenLink
        keyboard = Keyboard(inline=True)
        port = os.environ.get("PORT", 10000)
        # Assuming the Render app URL or local, we just provide a dummy localhost link for now
        # But we need a host. Render provides RENDER_EXTERNAL_URL
        host = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
        payment_url = f"{host}/payment/webhook?user_id={user_id}&amount=990"

        keyboard.add(OpenLink(payment_url, "Оплатить разбор (990₽)"))
        return keyboard.get_json()"""

content = re.sub(r'    def get_inline_buy_full_chart\(\) -> str:.*?return keyboard.get_json\(\)', new_keyboard_func, content, flags=re.DOTALL)

# Update calls to get_inline_buy_full_chart
content = content.replace('get_inline_buy_full_chart()', 'get_inline_buy_full_chart(vk_id)')

# Now we need to implement the webhook route and the heavy processing logic
# We need to extract the heavy processing from buy_full_chart and move it to a helper or put it in the webhook

# 2. Add process_payment helper inside main
heavy_processing_logic = """    async def process_payment_and_generate(vk_id: int):
        user = await get_user(vk_id)
        if not user:
            return

        active_tasks.add(vk_id)
        try:
            await bot.api.messages.send(peer_id=vk_id, message="Входящий платеж подтвержден.\\n\\nВрата открыты. Генерирую полный разбор и сакральную визуальную карту... Это займет около минуты.", random_id=0)
            await bot.api.messages.set_activity(peer_id=vk_id, type="typing")

            # Mark as purchased in database
            await update_user(vk_id, {"has_full_chart": True})

            date = user.get("birth_date", "неизвестно")
            time = user.get("birth_time", "неизвестно")
            city = user.get("birth_city", "неизвестно")

            text_prompt = (
                f"Ты премиальный психолог-астролог. Составь глубокий и полный анализ личности "
                f"по данным: дата {date}, время {time}, город {city}. "
                f"Избегай банальностей и ванильной астрологии. Используй юнгианские архетипы, "
                f"анализ теневой стороны личности и кармических узлов. Текст должен быть строгим, "
                f"проницательным, с долей холодного интеллекта. Пиши так, чтобы человек почувствовал "
                f"легкий шок от того, насколько точно вскрыты его скрытые мотивы."
            )
            full_text = await generate_text(text_prompt)

            # Генерируем выжимку для памяти (core_profile)
            if full_text:
                summary_prompt = (
                    f"Сделай очень короткую выжимку (психологический профиль, 2-3 предложения) "
                    f"из этого текста: {full_text[:1000]}. Это нужно для системной памяти бота."
                )
                core_profile = await generate_text(summary_prompt)
                if core_profile:
                    await update_user(vk_id, {"core_profile": core_profile})

            image_prompt = (
                "Стиль Премиум минимализм. Темный графитовый фон, тонкие линии из матового золота. "
                "Создай абстрактную карту таро. Включи элементы строгой сакральной геометрии. "
                "Добавь легкие, едва уловимые отсылки к египетской мифологии, например, строгий профиль "
                "Анубиса или золотые весы, стилизованные под созвездия. Никакого киберпанка, глитчей или "
                "хакерских элементов. Изображение должно излучать спокойствие, роскошь и древнюю власть."
            )
            image_bytes = await generate_image(image_prompt)

            user = await get_user(vk_id)
            if full_text:
                if image_bytes:
                    try:
                        from vkbottle import PhotoMessageUploader
                        uploader = PhotoMessageUploader(bot.api)
                        photo_attachment = await uploader.upload(image_bytes, peer_id=vk_id)
                        await bot.api.messages.send(peer_id=vk_id, message=full_text, attachment=photo_attachment, keyboard=get_dynamic_keyboard(user), random_id=0)
                    except Exception as e:
                        await bot.api.messages.send(peer_id=vk_id, message=f"Текст сгенерирован, но ошибка с фото: {e}\\n\\n{full_text}", keyboard=get_dynamic_keyboard(user), random_id=0)
                else:
                    await bot.api.messages.send(peer_id=vk_id, message=f"Не удалось сгенерировать изображение.\\n\\n{full_text}", keyboard=get_dynamic_keyboard(user), random_id=0)
            else:
                await bot.api.messages.send(peer_id=vk_id, message="Произошла ошибка при генерации разбора.", random_id=0)

        finally:
            active_tasks.discard(vk_id)"""

# Find the buy_full_chart handler to replace it
buy_full_chart_regex = r'    @bot\.on\.message\(text=\["Купить полный разбор", "Раскрыть полную карту"\]\).*?active_tasks\.discard\(vk_id\)'
content = re.sub(buy_full_chart_regex, heavy_processing_logic, content, flags=re.DOTALL)

# Add the webhook handler
webhook_handler_logic = """    async def payment_webhook(request):
        try:
            # We simulate a webhook via GET for ease of clicking a link in VK (which opens browser)
            # In real prod this would be POST from YooKassa
            user_id_str = request.query.get('user_id')
            if not user_id_str:
                return web.Response(text="Missing user_id", status=400)
            user_id = int(user_id_str)

            # Fire and forget the processing
            asyncio.create_task(process_payment_and_generate(user_id))

            return web.Response(text="Payment processed successfully! You can close this window and return to the bot.")
        except Exception as e:
            return web.Response(text=str(e), status=500)

    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/payment/webhook', payment_webhook)"""

# Replace app routing logic at the bottom
app_setup_regex = r'    app = web\.Application\(\).*?app\.router\.add_get\(\'/\', handle_ping\)'
content = re.sub(app_setup_regex, webhook_handler_logic, content, flags=re.DOTALL)

with open('main.py', 'w') as f:
    f.write(content)
