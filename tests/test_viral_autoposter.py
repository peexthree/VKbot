import json
import os
from unittest.mock import patch
import pytest
from modules.autoposter import generate_post
from modules.utils.visual import generate_card_history_image

@pytest.mark.asyncio
async def test_viral_post_generation():
    # Мокаем БД
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Мокаем AI (длина >= 400 символов)
                    mock_json = {
                        "text": "Тестовый пост. Это очень глубокий и развернутый разбор тарологии и космических путей, который заставит каждого задуматься о своих жизненных потоках. Мы препарируем самые сокровенные тайны души и указываем на истинное величие каждого адепта. Хватит плыть по течению, пора настроить свои внутренние струны и услышать настоящий шепот далеких звезд. Мы направляем жизненные потоки в нужное русло. Это дополнительное предложение, чтобы увеличить длину текста и сделать его гарантированно проходящим любые проверки пороговой длины на бэкенде. Теперь пост стал действительно длинным и основательным лонгридом. #АнтиТар",
                        "quote": "Таро — это костыль."
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)

                        assert post_data is not None
                        assert "text" in post_data
                        assert post_data["quote"] == "Таро — это костыль."
                        assert "PROVOCATION" in post_data["text"] or "ПРОВОКАЦИЯ" in post_data["text"]

                        # Хэштегов вообще быть не должно в итоговом тексте
                        assert "#" not in post_data["text"]

@pytest.mark.asyncio
async def test_no_hashtags_at_all():
    """Тестирует полное и безоговорочное удаление хэштегов из поста."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    mock_json = {
                        "text": "Ты жаришь хлеб в реакторе. Это очень странное и неэффективное использование столь мощного источника энергии. Твой звездный путь заслуживает гораздо большего, чем просто удовлетворение мелких повседневных нужд за счет космических сил. Сонастрой свои внутренние потоки и начни двигаться к истинной гармонии, которую нашептывают тебе далекие звезды и мудрые Арканы. Помни, что каждый шаг должен быть осмыслен и согласован с движением планет в небесной сфере. Добавим еще немного умных слов в этот абзац, чтобы длина текста превысила четыреста символов и валидация прошла безупречно.\n#АнтиТар #Судьба #Психология! #МатрицаСудьбы.",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)
                        text = post_data["text"]

                        assert "#" not in text
                        assert "Ты жаришь хлеб в реакторе" in text
                        # Убедимся, что слова из хэштегов удалились (или остались просто как текст без решетки, если были частью текста, но тут они шли отдельными тегами)
                        assert "АнтиТар" not in text
                        assert "Судьба" not in text

@pytest.mark.asyncio
async def test_no_cta_in_autoposts():
    """Тестирует, что в сгенерированном посте полностью отсутствуют призывы к действию (CTA) и ссылки vk.me / vk.com."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    mock_json = {
                        "text": "Это очень глубокий и развернутый разбор тарологии и космических путей, который заставит каждого задуматься о своих жизненных потоках. Мы препарируем самые сокровенные тайны души и указываем на истинное величие каждого адепта. Хватит плыть по течению, пора настроить свои внутренние струны и услышать настоящий шепот далеких звезд. Мы направляем жизненные потоки в нужное русло. И конечно, мы пишем еще более длинный текст, чтобы полностью исключить любые срабатывания лимита на минимальный размер.",
                        "quote": "Цитата"
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
    """Тестирует отмену публикации и отправку оповещения админу при некорректной длине текста."""
    from modules.autoposter import post_to_vk
    from unittest.mock import AsyncMock

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

    # 2. Сценарий: ИИ вернул текст короче 400 символов
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

    # 3. Сценарий: ИИ вернул корректный текст (>= 400 символов)
    long_ai_text = "Это очень глубокий и развернутый разбор. " * 20 # 40 * 20 = 800 символов
    long_post_data = {
        "text": "РУБРИКА: ПРОВОКАЦИЯ\n\n" + long_ai_text,
        "ai_text": long_ai_text,
        "skin_id": "olesya",
        "rubric": "PROVOCATION",
        "topic": "Тема",
        "quote": "Цитата"
    }
    with patch("modules.autoposter.generate_post", return_value=long_post_data):
        with patch("modules.autoposter.bot.api.request", new_callable=AsyncMock) as mock_request:
            # Нам нужно вернуть мокнутый объект для wall.post
            mock_request.return_value = {"post_id": 123}
            with patch("modules.autoposter.upload_wall_photo", return_value="photo123"):
                await post_to_vk(is_morning=True)

                # Проверим, что был вызван wall.post
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
                        "text": "Это первая строка нашего сакрального лонгрида, которая наполнена глубоким смыслом и величием звездной карты.\\nА это его вторая строка, которая раскрывает космические тайны, недоступные обычным скептикам и любителям простых гороскопов.\\nТретья строка содержит важный вывод для адептов и ведет к просветлению, сонастраивая внутренние энергетические потоки.\\nЧетвертая строка представляет собой напутствие на путь истинный и призывает отбросить все сомнения перед лицом вечности. Мы также увеличиваем длину этого текста, чтобы гарантировать прохождение лимита в 400 символов даже после очистки всех хэштегов.\\n#АнтиТар #Судьба",
                        "quote": "Цитата"
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
                    mock_json = {
                        "text": "Разбор Аркана. Это очень глубокий и развернутый разбор тарологии и космических путей, который заставит каждого задуматься о своих жизненных потоках. Мы препарируем самые сокровенные тайны души и указываем на истинное величие каждого адепта. Хватит плыть по течению, пора настроить свои внутренние струны и услышать настоящий шепот далеких звезд. Мы направляем жизненные потоки в нужное русло. Мы дописываем этот текст, чтобы он стал длиннее и больше, дабы обойти ограничение длины поста в 400 знаков, которое используется нашими алгоритмами. #АнтиТар",
                        "quote": "Цитата"
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
