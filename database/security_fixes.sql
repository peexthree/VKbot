-- =====================================================================
-- SECURITY FIXES - 2026-11-08 (по результатам полного аудита)
-- Запускать в Supabase SQL Editor.
--
-- PHASE A - применять сразу (не ломает текущего бота с anon-ключом).
-- PHASE B - применять ТОЛЬКО после того, как в Render добавлена
--           переменная SUPABASE_SERVICE_KEY (bot автоматически начнет
--           её использовать: database/config.py).
-- =====================================================================

-- =====================================================================
-- PHASE A
-- =====================================================================

-- ---------------------------------------------------------------
-- A1. Базовая таблица и недостающие колонки (код пишет email-привязку
--     и created_at, но в схеме их не было)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vk_esoteric_users (
    vk_id BIGINT PRIMARY KEY,
    first_name TEXT DEFAULT '',
    is_registered BOOLEAN DEFAULT FALSE,
    balance INTEGER DEFAULT 50,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS verification_code TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS verification_status TEXT DEFAULT 'none';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- ---------------------------------------------------------------
-- A2. Таблица идемпотентности платежей ЮKassa.
--     Без нее дедупликация вебхуков держалась только на 60-секундном
--     Redis-локе (ретрай ЮKassa = двойное начисление энергии)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_payments (
    payment_id TEXT PRIMARY KEY,
    user_id BIGINT,
    amount_rub INTEGER,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- A3. Атомарное списание энергии с проверкой достаточности.
--     Заменяет read-modify-write (потеря пополнений при гонках)
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION spend_user_balance(p_vk_id BIGINT, p_amount INTEGER)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_new_balance INTEGER;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RETURN jsonb_build_object('status', 'error', 'code', 'BAD_AMOUNT');
    END IF;

    UPDATE vk_esoteric_users
    SET balance = COALESCE(balance, 0) - p_amount
    WHERE vk_id = p_vk_id AND COALESCE(balance, 0) >= p_amount
    RETURNING balance INTO v_new_balance;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'error', 'code', 'INSUFFICIENT_FUNDS');
    END IF;

    RETURN jsonb_build_object('status', 'success', 'new_balance', v_new_balance);
END;
$$;

GRANT EXECUTE ON FUNCTION spend_user_balance(BIGINT, INTEGER) TO anon, authenticated, service_role;

-- ---------------------------------------------------------------
-- A4. CRITICAL: exec_sql выполняет произвольный SQL с правами владельца
--     и был доступен ЛЮБОМУ владельцу anon-ключа (RCE на всю БД).
--     Кнопка SQL-консоли из админки бота удалена в этом же релизе.
-- ---------------------------------------------------------------
REVOKE ALL ON FUNCTION exec_sql(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec_sql(text) FROM anon;
REVOKE ALL ON FUNCTION exec_sql(text) FROM authenticated;

-- ---------------------------------------------------------------
-- A5. secure_modify_balance выдавал ЛЮБОЙ баланс по вызову.
--     Ботом не используется - только service_role.
-- ---------------------------------------------------------------
REVOKE ALL ON FUNCTION secure_modify_balance(BIGINT, INTEGER, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION secure_modify_balance(BIGINT, INTEGER, TEXT) FROM anon;
REVOKE ALL ON FUNCTION secure_modify_balance(BIGINT, INTEGER, TEXT) FROM authenticated;
GRANT EXECUTE ON FUNCTION secure_modify_balance(BIGINT, INTEGER, TEXT) TO service_role;

-- ---------------------------------------------------------------
-- A6. sync_mobile_progress: анти-чит. Раньше любой anon мог вызывать
--     RPC в цикле (+10 энергии за каждые 1000 кликов без ограничений).
--     Теперь: не чаще 1 раза в 2 секунды и кап 3000 кликов/сутки
--     (= максимум 30 энергии в день с кликера)
-- ---------------------------------------------------------------
ALTER TABLE mobile_user_progress ADD COLUMN IF NOT EXISTS daily_clicks BIGINT DEFAULT 0;
ALTER TABLE mobile_user_progress ADD COLUMN IF NOT EXISTS click_day DATE;

CREATE OR REPLACE FUNCTION sync_mobile_progress(
    p_user_id BIGINT,
    p_clicks_delta INTEGER,
    p_familiar_level INTEGER,
    p_timers JSONB DEFAULT '{}'::jsonb
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_max_delta CONSTANT INTEGER := 500;      -- анти-чит: максимум кликов за один синк
    v_daily_cap CONSTANT INTEGER := 3000;     -- анти-чит: максимум кликов в сутки
    v_min_interval CONSTANT INTERVAL := '2 seconds';
    v_new_clicks BIGINT;
    v_current_level INTEGER;
    v_bonus_energy INTEGER := 0;
    v_daily_clicks BIGINT := 0;
    v_click_day DATE;
    v_last_sync TIMESTAMP WITH TIME ZONE;
BEGIN
    IF p_clicks_delta < 0 OR p_clicks_delta > v_max_delta THEN
        RETURN jsonb_build_object('status', 'error', 'code', 'SUSPICIOUS_DELTA');
    END IF;

    SELECT daily_clicks, click_day, last_sync_at
    INTO v_daily_clicks, v_click_day, v_last_sync
    FROM mobile_user_progress
    WHERE user_id = p_user_id
    FOR UPDATE;

    IF FOUND THEN
        IF v_last_sync > NOW() - v_min_interval THEN
            RETURN jsonb_build_object('status', 'error', 'code', 'TOO_FAST');
        END IF;
        IF v_click_day IS DISTINCT FROM CURRENT_DATE THEN
            v_daily_clicks := 0;  -- новый день - кап сбрасывается
        END IF;
        IF v_daily_clicks + p_clicks_delta > v_daily_cap THEN
            RETURN jsonb_build_object('status', 'error', 'code', 'DAILY_CAP_REACHED');
        END IF;
    END IF;

    INSERT INTO mobile_user_progress (user_id, clicker_count, familiar_level, timers, last_sync_at, daily_clicks, click_day)
    VALUES (p_user_id, p_clicks_delta, GREATEST(1, p_familiar_level), p_timers, NOW(), p_clicks_delta, CURRENT_DATE)
    ON CONFLICT (user_id) DO UPDATE
    SET clicker_count = mobile_user_progress.clicker_count + EXCLUDED.clicker_count,
        familiar_level = GREATEST(mobile_user_progress.familiar_level, EXCLUDED.familiar_level),
        timers = COALESCE(EXCLUDED.timers, mobile_user_progress.timers),
        last_sync_at = NOW(),
        daily_clicks = CASE
            WHEN mobile_user_progress.click_day IS DISTINCT FROM CURRENT_DATE
            THEN EXCLUDED.clicker_count
            ELSE mobile_user_progress.daily_clicks + EXCLUDED.clicker_count
        END,
        click_day = CURRENT_DATE
    RETURNING clicker_count, familiar_level INTO v_new_clicks, v_current_level;

    -- Бонус каждые 1000 кликов (+10 энергии), теперь в пределах суточного капа
    IF (v_new_clicks % 1000) < p_clicks_delta THEN
        v_bonus_energy := 10;
        UPDATE vk_esoteric_users
        SET balance = COALESCE(balance, 0) + v_bonus_energy
        WHERE vk_id = p_user_id;
    END IF;

    RETURN jsonb_build_object(
        'status', 'success',
        'clicker_count', v_new_clicks,
        'familiar_level', v_current_level,
        'energy_bonus', v_bonus_energy
    );
END;
$$;

GRANT EXECUTE ON FUNCTION sync_mobile_progress(BIGINT, INTEGER, INTEGER, JSONB) TO anon, authenticated, service_role;

-- =====================================================================
-- PHASE B - ТОЛЬКО после добавления SUPABASE_SERVICE_KEY в Render!
-- (после этого бот ходит в БД через service_role, который обходит RLS,
--  и политика ниже больше не нужна)
-- =====================================================================
-- DROP POLICY IF EXISTS "Users can read own profile" ON vk_esoteric_users;
--
-- Пояснение: политика называлась "read own", но USING (true) открывала
-- anon-клиентам чтение ВСЕЙ таблицы: email, даты рождения, имена,
-- теги, балансы, история раскладов. service_role в RLS не участвует.
-- Если мобильному клиенту понадобится прямое чтение профилей - верни
-- политику с реальным user-scoping через auth.uid(), а не USING (true).
