import json
import os
from unittest.mock import patch, AsyncMock
import pytest
from modules.autoposter import generate_post, post_to_vk
from modules.utils.visual import generate_card_history_image

@pytest.mark.asyncio
async def test_viral_post_generation():
    # Мокаем БД
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Мокаем AI (длина >= 600 символов)
                    mock_text = (
                        "Ты жаришь хлеб в реакторе. Это очень странное и неэффективное использование столь мощного источника энергии. "
                        "Твой звездный путь заслуживает гораздо большего, чем просто удовлетворение мелких повседневных нужд за счет космических сил. "
                        "Сонастрой свои внутренние потоки и начни двигаться к истинной гармонии, которую нашептывают тебе далекие звезды и мудрые Арканы. "
                        "Помни, что каждый шаг должен быть осмыслен и согласован с движением планет в небесной сфере. "
                        "Мы создаем действительно глубокий, развернутый и впечатляющий лонгрид, который полностью соответствует высокому стандарту качества паблика. "
                        "Каждая фраза наполнена спрессованным смыслом, подталкивающим адепта к переосмыслению своей роли во вселенной и разрыву ментальных зажимов."
                    )
                    mock_json = {
                        "text": mock_text,
                        "quote": "Таро — это костыль.",
                        "first_comment": "Напиши дату рождения — и я разберу твои кармические узелки."
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)

                        assert post_data is not None
                        assert "text" in post_data
                        assert post_data["quote"] == "Таро — это костыль."
                        assert post_data["first_comment"] == "Напиши дату рождения — и я разберу твои кармические узелки."
                        # Проверяем, что техническая шапка находится внизу (Option A)
                        assert post_data["text"].endswith("РУБРИКА: ПРОВОКАЦИЯ\n👁 РАСПУТИН") or "РУБРИКА: ПРОВОКАЦИЯ" in post_data["text"].split("\n\n")[-1]
                        assert post_data["text"].startswith("Ты жаришь хлеб в реакторе")

                        # Хэштегов вообще быть не должно в итоговом тексте
                        assert "#" not in post_data["text"]

@pytest.mark.asyncio
async def test_no_hashtags_at_all():
    """Тестирует полное и безоговорочное удаление хэштегов из поста."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    mock_text = (
                        "Ты жаришь хлеб в реакторе. Это очень странное и неэффективное использование столь мощного источника энергии. "
                        "Твой звездный путь заслуживает гораздо большего, чем просто удовлетворение мелких повседневных нужд за счет космических сил. "
                        "Сонастрой свои внутренние потоки и начни двигаться к истинной гармонии, которую нашептывают тебе далекие звезды и мудрые Арканы. "
                        "Помни, что каждый шаг должен быть осмыслен и согласован с движением планет в небесной сфере. "
                        "Добавим еще немного умных слов в этот абзац, чтобы длина текста превысила шестьсот символов и валидация прошла безупречно и надежно во всех сценариях.\n"
                        "#АнтиТар #Судьба #Психология! #МатрицаСудьбы."
                    )
                    mock_json = {
                        "text": mock_text,
                        "quote": "Цитата",
                        "first_comment": "Комментарий"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)
                        assert post_data is not None
                        text = post_data["text"]

                        assert "#" not in text
                        assert text.startswith("Ты жаришь хлеб в реакторе")
                        # Убедимся, что слова из хэштегов удалились
                        assert "АнтиТар" not in text
                        assert "Судьба" not in text

@pytest.mark.asyncio
async def test_no_cta_in_autoposts():
    """Тестирует, что в сгенерированном посте полностью отсутствуют призывы к действию (CTA) и ссылки vk.me / vk.com."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    mock_text = (
                        "Это очень глубокий и развернутый разбор тарологии и космических путей, который заставит каждого задуматься о своих жизненных потоках. "
                        "Мы препарируем самые сокровенные тайны души и указываем на истинное величие каждого адепта. "
                        "Хватит плыть по течению, пора настроить свои внутренние струны и услышать настоящий шепот далеких звезд. "
                        "Мы направляем жизненные потоки в нужное русло. И конечно, мы пишем еще более длинный текст, чтобы полностью исключить любые срабатывания лимита на минимальный размер "
                        "и сделать данный пост максимально качественным лонгридом для сообщества. "
                        "Дополнительные предложения обеспечивают полную укомплектованность текста до необходимого объема в 600 символов."
                    )
                    mock_json = {
                        "text": mock_text,
                        "quote": "Цитата",
                        "first_comment": "Первый коммент"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)
                        assert post_data is not None
                        text = post_data["text"]

                        # В тексте поста не должно быть ссылок на ВК или призывов писать боту/подписываться
                        assert "vk.me" not in text
                        assert "vk.com" not in text
                        assert "напиши нашему Проводнику" not in text
                        assert "Подпишись на наше сообщество" not in text
                        assert "Присоединяйся к нашему сообществу" not in text

@pytest.mark.asyncio
async def test_autoposter_validation_and_alerting():
    """Тестирует отмену публикации и отправку оповещения админу при некорректной длине текста (< 600 символов)."""
    # 1. Сценарий: ИИ вернул пустой пост (generate_post возвращает None)
    with patch("modules.autoposter.generate_post", return_value=None):
        with patch("modules.autoposter.bot.api.request", new_callable=AsyncMock) as mock_request:
            await post_to_vk(is_morning=True)
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "messages.send"
            params = args[1]
            assert params.get("peer_id") == 27260796
            assert "🚨 Сбой автопостинга! Публикация отменена. Причина: ИИ вернул пустой текст или сработал тайтмаут прокси. Проверь логи Cloudflare" == params.get("message")

    # 2. Сценарий: ИИ вернул текст короче 600 символов
    short_post_data = {
        "text": "Короткий текст поста",
        "ai_text": "Короткий текст",
        "skin_id": "olesya",
        "rubric": "PROVOCATION",
        "topic": "Тема",
        "quote": "Цитата"
    }
    with patch("modules.autoposter.generate_post", return_value=short_post_data):
        with patch("modules.autoposter.bot.api.request", new_callable=AsyncMock) as mock_request:
            await post_to_vk(is_morning=True)
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "messages.send"
            params = args[1]
            assert "🚨 Сбой автопостинга! Публикация отменена. Причина: ИИ вернул пустой текст или сработал тайтмаут прокси. Проверь логи Cloudflare" == params.get("message")

    # 3. Сценарий: ИИ вернул корректный текст (>= 600 символов)
    long_ai_text = "Это очень глубокий и развернутый разбор космических путей. " * 20 # 60 * 20 = 1200 символов
    long_post_data = {
        "text": long_ai_text + "\n\nРУБРИКА: ПРОВОКАЦИЯ\n👁 ОЛЕСЯ",
        "ai_text": long_ai_text,
        "skin_id": "olesya",
        "rubric": "PROVOCATION",
        "topic": "Тема",
        "quote": "Цитата",
        "first_comment": "Напиши дату"
    }
    mock_res = {"response": {"post_id": 123}}
    async def mock_api_request(method, params=None):
        if method == "wall.post":
            return mock_res
        elif method == "wall.createComment":
            return {"response": {"comment_id": 11}}
        return {"response": {}}

    with patch("modules.autoposter.generate_post", return_value=long_post_data):
        with patch("modules.autoposter.bot.api.request", side_effect=mock_api_request) as mock_request:
            with patch("modules.autoposter.upload_wall_photo", return_value="photo123"):
                await post_to_vk(is_morning=True)

                # Проверим, что wall.post вызывался
                any_wall_post = any(call[0][0] == "wall.post" for call in mock_request.call_args_list)
                assert any_wall_post is True

                # Убедимся, что messages.send НЕ вызывался (алерты не отправлялись)
                any_alert = any(call[0][0] == "messages.send" and "🚨 Сбой автопостинга!" in call[0][1].get("message", "") for call in mock_request.call_args_list)
                assert any_alert is False

@pytest.mark.asyncio
async def test_escaped_newline_handling():
    """Тестирует сценарий, когда ИИ вернул JSON с экранированными переносами строк \\n.
    Проверяет, что переносы строк правильно преобразуются в реальные,
    и хэштеги полностью вырезаются."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Тело содержит экранированные \\n вместо настоящих переносов строк
                    mock_json = {
                        "text": "Это первая строка нашего сакрального лонгрида, которая наполнена глубоким смыслом и величием звездной карты.\\nА это его вторая строка, которая раскрывает космические тайны, недоступные обычным скептикам и любителям простых гороскопов.\\nТретья строка содержит важный вывод для адептов и ведет к просветлению, сонастраивая внутренние энергетические потоки.\\nЧетвертая строка представляет собой напутствие на путь истинный и призывает отбросить все сомнения перед лицом вечности. Мы также увеличиваем длину этого текста, чтобы гарантировать прохождение лимита в 600 символов даже после очистки всех хэштегов.\\n#АнтиТар #Судьба",
                        "quote": "Цитата",
                        "first_comment": "Комментарий"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)

                        assert post_data is not None
                        text = post_data["text"]

                        # Проверяем, что тело поста не стерто и в нем присутствуют все ключевые строки
                        assert "Это первая строка нашего сакрального лонгрида" in text
                        assert "А это его вторая строка" in text
                        assert "Третья строка содержит важный вывод" in text
                        assert "Четвертая строка" in text
                        # Проверяем, что хэштеги были полностью вырезаны
                        assert "#" not in text
                        assert "АнтиТар" not in text

@pytest.mark.asyncio
async def test_card_history_rubric_generation():
    """Тестирует рубрику CARD_HISTORY в генераторе постов."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="CARD_HISTORY"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    mock_text = (
                        "Разбор Аркана. Это очень глубокий и развернутый разбор тарологии и космических путей, который заставит каждого задуматься о своих жизненных потоках. "
                        "Мы препарируем самые сокровенные тайны души и указываем на истинное величие каждого адепта. "
                        "Хватит плыть по течению, пора настроить свои внутренние струны и услышать настоящий шепот далеких звезд. "
                        "Мы направляем жизненные потоки в нужное русло. Мы дописываем этот текст, чтобы он стал длиннее и больше, дабы обойти ограничение длины поста в 600 знаков, которое используется нашими алгоритмами и проверками. "
                        "Дополнительный объем текста для прохождения всех валидаций гарантирован."
                    )
                    mock_json = {
                        "text": mock_text,
                        "quote": "Цитата",
                        "first_comment": "Первый коммент"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)
                        assert post_data is not None
                        assert "card_id" in post_data
                        assert "card_name" in post_data
                        assert post_data["card_id"] is not None
                        assert post_data["card_name"] is not None
                        assert "ИСТОРИЯ АРКАНА" in post_data["text"]
                        assert "#" not in post_data["text"]

def test_generate_card_history_image_file():
    """Тестирует корректную генерацию Pillow изображения для CARD_HISTORY."""
    temp_path = "cards/test_temp_hist.jpg"
    if os.path.exists(temp_path):
        os.remove(temp_path)
    try:
        generate_card_history_image(0, "Шут", temp_path)
        assert os.path.exists(temp_path)
        assert os.path.getsize(temp_path) > 100
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@pytest.mark.asyncio
async def test_first_comment_with_promo_ps():
    """Тестирует генерацию first_comment и автоматическую приклейку P.S. при наличии скрытого промокода."""
    long_ai_text = "Пост с подробным текстом..." * 30 # > 600 символов
    mock_post_data = {
        "text": long_ai_text + "\n\nРУБРИКА: ПРОВОКАЦИЯ\n👁 ОЛЕСЯ",
        "ai_text": long_ai_text,
        "skin_id": "olesya",
        "rubric": "PROVOCATION",
        "topic": "Тема",
        "quote": "Цитата",
        "first_comment": "Напиши свою дату рождения под постом!",
        "has_promo": True,
        "energy_reward": 150
    }

    mock_res = {"response": {"post_id": 999}}
    comment_calls = []

    async def mock_api_request(method, params=None):
        if method == "wall.post":
            return mock_res
        elif method == "wall.createComment":
            comment_calls.append((method, params or {}))
            return {"response": {"comment_id": 11}}
        return {"response": {}}

    with patch("modules.autoposter.generate_post", return_value=mock_post_data):
        with patch("modules.autoposter.bot.api.request", side_effect=mock_api_request):
            # Фиксируем ротацию визуалов, чтобы quote гарантированно передавался
            with patch("random.random", return_value=0.1):
                with patch("modules.autoposter.upload_wall_photo", return_value="photo999"):
                    await post_to_vk(is_morning=True)

                    assert len(comment_calls) > 0
                    comment_msg = comment_calls[0][1].get("message", "")
                    assert "Напиши свою дату рождения под постом!" in comment_msg
                    assert "P.S. В тексте этого поста спрятан сакральный шифр на 150 ✨. Нашел? Отправь его мне в личные сообщения." in comment_msg
