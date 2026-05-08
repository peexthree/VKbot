# Mindsee Bot

VK esoteric bot built with aiohttp and VKBottle.

## Установка и запуск

1. Создать виртуальное окружение и установить зависимости:
   virtualenv venv
   source venv/bin/activate
   pip install -r requirements.txt

2. Скопировать `.env.example` в `.env` и указать ключи:
   cp .env.example .env

3. Запустить бота:
   python main.py

## Переменные окружения
- `VK_TOKEN`: Токен бота ВКонтакте.
- `SUPABASE_URL`, `SUPABASE_KEY`: Доступы к Supabase.
- `GEMINI_API_KEYS`: API ключи для модели Gemini (через запятую, если несколько).
- `REDIS_URL`: Ссылка на подключение к Redis.

## Развертывание
Можно использовать Docker и docker-compose, конфигурации уже добавлены в корень проекта.

## Тестирование
pytest tests/
