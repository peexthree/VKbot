-- МИГРАЦИЯ ДЛЯ АВТОПОСТЕРА 2.0 (Генератор-Комбинатор)
-- Выполнить в SQL Editor Supabase

-- 1. Таблица для хранения активных опросов и анализа результатов
CREATE TABLE IF NOT EXISTS active_polls (
    id SERIAL PRIMARY KEY,
    poll_id BIGINT NOT NULL,
    owner_id BIGINT NOT NULL,
    topic_name TEXT NOT NULL,
    options JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Таблица для контроля повторов персонажей и тем (лог за 24 часа)
CREATE TABLE IF NOT EXISTS post_daily_log (
    id SERIAL PRIMARY KEY,
    skin_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для ускорения поиска
CREATE INDEX IF NOT EXISTS idx_post_daily_log_published_at ON post_daily_log(published_at);
CREATE INDEX IF NOT EXISTS idx_active_polls_is_active ON active_polls(is_active);
