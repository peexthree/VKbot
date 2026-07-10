import asyncio
import json
from unittest.mock import patch, MagicMock
import pytest
from modules.autoposter import generate_post

@pytest.mark.asyncio
async def test_viral_post_generation():
    # Мокаем БД
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Мокаем AI (длина >= 400 символов)
                    mock_json = {
                        "text": "Тестовый пост. Это очень глубокий и развернутый разбор тарологии и космических путей, который заставит каждого задуматься о своих жизненных потоках. Мы препарируем самые сокровенные тайны души и указываем на истинное величие каждого адепта. Хватит плыть по течению, пора настроить свои внутренние струны и услышать настоящий шепот далеких звезд. Мы направляем жизненные потоки в нужное русло. #АнтиТар",
                        "quote": "Таро — это костыль."
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)

                        assert post_data is not None
                        assert "text" in post_data
                        assert post_data["quote"] == "Таро — это костыль."
                        assert "PROVOCATION" in post_data["text"] or "ПРОВОКАЦИЯ" in post_data["text"]

@pytest.mark.asyncio
async def test_hashtag_handling_clean():
    """Тестирует правильность извлечения хэштегов и непопадание обычных слов в хэштеги."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # 1. Сценарий с явно выделенными хэштегами в конце
                    mock_json_1 = {
                        "text": "Ты жаришь хлеб в реакторе. Это очень странное и неэффективное использование столь мощного источника энергии. Твой звездный путь заслуживает гораздо большего, чем просто удовлетворение мелких повседневных нужд за счет космических сил. Сонастрой свои внутренние потоки и начни двигаться к истинной гармонии, которую нашептывают тебе далекие звезды и мудрые Арканы. Помни, что каждый шаг должен быть осмыслен и согласован с движением планет в небесной сфере.\n#АнтиТар #Судьба",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_1)):
                        post_data_1 = await generate_post(is_morning=True)
                        assert "#АнтиТар #Судьба" in post_data_1["text"]
                        assert "Ты жаришь хлеб в реакторе" in post_data_1["text"]

                    # 2. Сценарий с обычным текстом в конце (без хэштегов)
                    mock_json_2 = {
                        "text": "Ты жаришь хлеб в реакторе. Это очень странное и неэффективное использование столь мощного источника энергии. Твой звездный путь заслуживает гораздо большего, чем просто удовлетворение мелких повседневных нужд за счет космических сил. Сонастрой свои внутренние потоки и начни двигаться к истинной гармонии, которую нашептывают тебе далекие звезды и мудрые Арканы. Помни, что каждый шаг должен быть осмыслен и согласован с движением планет в небесной сфере.\nИ это очень странно.",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_2)):
                        post_data_2 = await generate_post(is_morning=True)
                        assert "И это очень странно." in post_data_2["text"]
                        assert "#АнтиТар #МатрицаСудьбы #Психология #Судьба" in post_data_2["text"]

@pytest.mark.asyncio
async def test_hashtag_handling_punctuation_and_deduplication():
    """Тестирует обратное сканирование, очистку знаков препинания из хэштегов и дедупликацию."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Сценарий с грязными хэштегами и дубликатами в конце
                    mock_json = {
                        "text": "Тело поста. Мы пишем очень длинный и развернутый текст, чтобы преодолеть строгий предохранительный порог длины в четыреста символов, установленный для защиты нашего эзотерического сообщества от пустых публикаций. Потоки космоса должны течь свободно, наполняя разум адепта истинным знанием и гармонией звездного неба. Твои сокровенные тайны души будут раскрыты в этом глубоком исследовании.\n\n#АнтиТар, #Психология. #Судьба! #антитар #МатрицаСудьбы...",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)
                        text = post_data["text"]

                        # Хэштеги должны быть очищены от знаков препинания
                        # Из-за дедупликации без учета регистра, #антитар должен остаться только один раз
                        assert "#АнтиТар #Психология #Судьба #МатрицаСудьбы" in text
                        assert "#АнтиТар, " not in text
                        assert "#Психология." not in text
                        assert "#антитар" not in text.split("Чтобы")[1] # В финальной части только первый дедуплицированный
                        assert "Тело поста." in text

@pytest.mark.asyncio
async def test_sunday_mechanics():
    # Мокаем текущую дату на воскресенье
    sunday = MagicMock()
    sunday.weekday.return_value = 6
    sunday.strftime.return_value = "07.07.2024"

    with patch("datetime.datetime") as mock_date:
        mock_date.now.return_value = sunday
        # На самом деле в коде используется now = datetime.datetime.now(tz_bash)
        # Нам нужно убедиться что logic подхватит is_sunday

        with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
            with patch("modules.autoposter.get_active_poll", return_value=None):
                with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                    with patch("modules.autoposter.save_hidden_promo", return_value=True):
                        mock_json = {
                            "text": "Текст с ЧАСТЬ1. Этот текст должен быть достаточно длинным, чтобы пройти валидацию по длине чистого текста от искусственного интеллекта. Мы пишем о прекрасных звездах, созвучиях планет и таинственных силах вселенной, которые направляют наши жизненные потоки и сонастраивают внутреннее эго с великим планом бытия. Это великое учение откроет новые сияющие горизонты перед каждым, кто готов вслушаться в истинную мудрость. #АнтиТар",
                            "quote": "Цитата"
                        }
                        with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                            post_data = await generate_post(is_morning=True)
                            assert post_data["is_sunday"] is True

@pytest.mark.asyncio
async def test_dynamic_cta_handling():
    """Тестирует детекцию динамического CTA (эмодзи 🔮) и пропуск жесткого навигатора."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):

                    # 1. Сценарий, когда ИИ сгенерировал динамический CTA с 🔮 в конце
                    mock_json_with_cta = {
                        "text": "Тело поста. Разрушаем иллюзии. Наш звездный путь полон загадок и великих открытий. Мы учим адептов видеть знаки, которые оставляет вселенная на их жизненном пути. Это длинный лонгрид, превосходящий установленные четыреста символов для успешного прохождения валидации нашими строгими алгоритмами. Вслушайся в биение вселенского сердца, чтобы сонастроить свои шаги с вечностью.\n\n🔮 Хватит кормить чужих демонов... Нажимай на кнопку Написать сообществу...\n#АнтиТар #МатрицаСудьбы",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_with_cta)):
                        post_data = await generate_post(is_morning=True)
                        text = post_data["text"]

                        # Должен быть динамический CTA
                        assert "🔮 Хватит кормить чужих демонов... Нажимай на кнопку Написать сообществу..." in text
                        # Жесткого навигатора быть НЕ должно
                        assert "направить жизненные потоки" not in text

                    # 2. Сценарий, когда ИИ забыл выдать концовку с 🔮
                    mock_json_no_cta = {
                        "text": "Тело поста. Разрушаем иллюзии без призывов. Мы пишем длинный, глубокий текст о природе человеческой души и кармических узлах, который призван раскрыть глаза нашему читателю на его истинное предназначение в этом физическом мире под руководством созвездий. Каждый из нас — лишь крошечная искорка в бескрайнем сияющем океане вечности. Давай вместе сделаем этот шаг навстречу сияющим звездам, которые неуклонно ведут нас сквозь земные преграды к вершинам истинного спокойствия и процветания.\n#АнтиТар #МатрицаСудьбы",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_no_cta)):
                        post_data = await generate_post(is_morning=True)
                        text = post_data["text"]

                        # Жесткий навигатор ДОЛЖЕН быть приклеен
                        # На этом этапе в modules/autoposter.py все еще старый текст, поэтому поддержим оба варианта в тесте для надежности
                        assert ("Чтобы взломать свою судьбу" in text or "Чтобы сонастроить свои внутренние" in text)

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
    чтобы обратный сканер не стер тело поста."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Тело содержит экранированные \\n вместо настоящих переносов строк
                    # Делаем его достаточно длинным (>= 400 символов), чтобы пройти проверку на длину
                    mock_json = {
                        "text": "Это первая строка нашего сакрального лонгрида, которая наполнена глубоким смыслом и величием звездной карты.\\nА это его вторая строка, которая раскрывает космические тайны, недоступные обычным скептикам и любителям простых гороскопов.\\nТретья строка содержит важный вывод для адептов и ведет к просветлению, сонастраивая внутренние энергетические потоки.\\nЧетвертая строка представляет собой напутствие на путь истинный и призывает отбросить все сомнения перед лицом вечности.\\n#АнтиТар #Судьба",
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
                        # Проверяем, что хэштеги были успешно выделены в самый конец
                        assert "#АнтиТар #Судьба" in text

if __name__ == "__main__":
    asyncio.run(test_viral_post_generation())
    asyncio.run(test_sunday_mechanics())
    asyncio.run(test_dynamic_cta_handling())
    asyncio.run(test_autoposter_validation_and_alerting())
    asyncio.run(test_escaped_newline_handling())
    print("Tests passed!")
