-- 1. СКРИПТ ДЛЯ СОЗДАНИЯ МОСТА (RPC)
-- Выполни это ОДИН РАЗ в Supabase SQL Editor

CREATE OR REPLACE FUNCTION exec_sql(sql_query text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER -- Дает права обходить RLS и менять структуру
AS $$
DECLARE
    ret jsonb;
BEGIN
    -- Пытаемся выполнить как SELECT и вернуть JSON
    BEGIN
        EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO ret;
        RETURN ret;
    EXCEPTION WHEN OTHERS THEN
        -- Если это не SELECT (например, ALTER, UPDATE, CREATE), просто выполняем
        EXECUTE sql_query;
        RETURN jsonb_build_object('status', 'success', 'message', 'Command executed successfully');
    END;
EXCEPTION WHEN OTHERS THEN
    -- Возвращаем текст ошибки если всё упало
    RETURN jsonb_build_object('error', SQLERRM, 'detail', SQLSTATE);
END;
$$;


-- 2. СКРИПТ ТОТАЛЬНОЙ ЗАЧИСТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ
-- Можно выполнить через новый интерфейс бота или напрямую в Supabase

UPDATE vk_esoteric_users
SET
    birth_date = NULL,
    birth_time = NULL,
    birth_city = NULL,
    core_profile = NULL,
    latest_reading_text = NULL,
    latest_reading_data = '{}'::jsonb,
    readings_history = '[]'::jsonb,
    destiny_card_data = NULL;

-- Опционально: удаление колонок, если они больше не нужны
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS birth_date;
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS birth_time;
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS birth_city;
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS core_profile;
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS latest_reading_text;
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS latest_reading_data;
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS readings_history;
-- ALTER TABLE vk_esoteric_users DROP COLUMN IF EXISTS destiny_card_data;
