# Docker-вариант деплоя АНТИ-ТАР (2026-11-09)
#
# ЗАЧЕМ: в нативном Python-рантайме Render файловая система при сборке
# read-only - apt-get там не работает, поэтому системную библиотеку Pango
# (обязательна для WeasyPrint, т.е. платных PDF-отчетов) поставить нельзя.
# Dockerfile ставит Pango в образ.
#
# КАК ВКЛЮЧИТЬ: Render -> твой сервис -> Settings -> Language/Runtime ->
# Docker. Render сам найдет Dockerfile в корне. Environment Variables и
# Health Check Path ( / ) сохраняются. Start Command для Docker не нужен.
#
# Локальная проверка: docker build -t vkbot . && docker run -p 10000:10000 --env-file .env vkbot

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

# Pango (>= 1.44) и друзья для WeasyPrint 68 + кириллический фолбэк-шрифт
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Зависимости - отдельным слоем (кэш Docker не пересобирает их при правке кода).
# poetry 2.4.1 - ровно та версия, что сгенерировала poetry.lock (мismatch
# версий poetry читается как "pyproject changed significantly")
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry==2.4.1 \
    && poetry install --no-root --no-cache

COPY . .

EXPOSE 10000
CMD ["python", "-u", "main.py"]
