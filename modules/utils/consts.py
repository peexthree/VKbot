import os
import asyncio
from jinja2 import Environment, FileSystemLoader

THEATRICAL_PHRASES = [
    "Считываю цифровой след...",
    "Открываю гримуар...",
    "Анализирую векторы вероятности...",
    "Настраиваюсь на ваши вибрации...",
    "Обращаюсь к древним арканам...",
    "Раскладываю карты судьбы...",
    "Запрашиваю ответ у мироздания...",
    "Синхронизирую потоки энергии...",
    "Читаю линии вероятности...",
    "Проникаю в тайны подсознания...",
    "Собираю осколки грядущего...",
    "Вслушиваюсь в шепот звезд...",
    "Приподнимаю завесу тайны...",
    "Сканирую энергетический фон...",
    "Анализирую кармические узлы...",
    "Шарф перемешивается...",
    "Звёзды выстраиваются...",
    "Спрашиваю у духов...",
    "Нити судьбы переплетаются...",
    "Открываю портал в астрал..."
]

SKIN_ASSETS = {
    "Олеся Ивонченко": "o.png",
    "olesya": "o.png",
    "Серьезный Аскет": "as.jpeg",
    "asket": "as.jpeg",
    "Олег Шэпс": "ol.jpeg",
    "Влад Череватов": "2o.jpeg",
    "Виктория Райдес": "v.jpeg",
    "Александр Шеппс": "a.jpeg",
    "Баба Ванга": "ba.jpeg",
    "Григорий Распутин": "r.jpeg",
    "Магистр": "magistr.jpeg"
}

ADMIN_ID = int(os.environ.get("ADMIN_ID", 27260796))

# Global state for typing animations
_typing_tasks: dict[int, asyncio.Task] = {}
_typing_msg_ids: dict[int, int] = {}

# Global cache for cover photo IDs
cover_cache: dict[str, str] = {}

# Batch anchor logic
ANCHOR_BATCH_SIZE = 10
_anchor_batch: list[str] = []

# PDF related
templates_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'templates')
jinja_env = Environment(loader=FileSystemLoader('templates'))
pdf_semaphore = asyncio.Semaphore(1)
