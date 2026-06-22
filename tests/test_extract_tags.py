import pytest
from unittest.mock import patch, AsyncMock
from ai.sections import extract_tags

@pytest.mark.asyncio
async def test_extract_tags_greedy_regex_issue():
    """
    Тест проверяет, что текущая реализация extract_tags ломается на 'разболтанном' ответе ИИ.
    """
    # Имитируем ответ ИИ, где после JSON идет текст с закрывающей скобкой
    ai_response = '["путь-к-себе", "трансформация-личности"] Игорь, мой хороший, ну ты даешь! Опять играешь в прятки... [надеюсь, это поможет]'

    with patch('ai.sections.generate_text', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = ai_response

        # Мы ожидаем, что теги будут извлечены правильно.
        # В текущем состоянии (жадная регулярка) это вернет [], так как json.loads упадет.
        # После фикса (ленивая регулярка) это вернет список тегов.
        tags = await extract_tags("какой-то текст")

        assert tags == ["путь-к-себе", "трансформация-личности"]
