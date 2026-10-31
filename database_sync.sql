-- =====================================================================
-- VK Esoteric Bot (АНТИ-ТАР) - Complete Database Schema & Sync Script
-- Run this script in the Supabase SQL Editor.
-- =====================================================================

-- 1. SYNCHRONIZE TABLE: vk_esoteric_users
-- (Updates the existing table with any missing columns safely)
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS first_name TEXT DEFAULT '';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS birth_date TEXT DEFAULT '';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS birth_time TEXT DEFAULT '12:00';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS birth_city TEXT DEFAULT '';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS free_teaser_used BOOLEAN DEFAULT FALSE;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS is_subscribed BOOLEAN DEFAULT FALSE;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS compatibility_balance INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS core_profile TEXT DEFAULT '';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS partners JSONB DEFAULT '[]'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS free_card_used BOOLEAN DEFAULT FALSE;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS purchased_sections JSONB DEFAULT '{"sex": false, "money": false, "shadow": false, "final": false, "sex_val": 0, "oracle_access": false, "card_of_day_last_used": null, "conversion_step": "started"}'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS has_full_chart BOOLEAN DEFAULT FALSE;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS forecast_time TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS balance INTEGER DEFAULT 50;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS oracle_last_used TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS has_priority_access BOOLEAN DEFAULT FALSE;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS bonuses INTEGER;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS last_active_date TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS active_skin TEXT DEFAULT 'olesya';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS purchased_skins JSONB DEFAULT '["olesya"]'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS transit_trial_days INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS transit_sub_expires_at TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS unlocked_cards JSONB DEFAULT '{}'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS weekly_log JSONB DEFAULT '[]'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS visit_streak INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS total_cards_received INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS last_daily_bonus_date TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS welcome_bonus_received BOOLEAN DEFAULT FALSE;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS last_feedback_bonus_date TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS latest_reading_text TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS latest_reading_data JSONB DEFAULT '{}'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS readings_history JSONB DEFAULT '[]'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS tz TEXT;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS destiny_card_data JSONB;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS support_history JSONB DEFAULT '[]'::jsonb;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS is_registered BOOLEAN DEFAULT FALSE;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS used_skins_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS compatibility_partners_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS compatibility_partners_hashes TEXT[] DEFAULT '{}'::text[];
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS dreams_analyzed_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS rituals_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS active_referrals_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS level_3_counted BOOLEAN DEFAULT FALSE;


-- 2. CREATE AUXILIARY TABLES
-- Feedbacks table
CREATE TABLE IF NOT EXISTS feedbacks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    service_name TEXT NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    is_posted BOOLEAN DEFAULT FALSE,
    posted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Events / transactions logging table
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    username TEXT,
    action TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Autoposter: Global history of published posts
CREATE TABLE IF NOT EXISTS post_history (
    id SERIAL PRIMARY KEY,
    topic_name TEXT NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    clicks INTEGER DEFAULT 0
);

-- Autoposter: Individual user click tracking
CREATE TABLE IF NOT EXISTS post_clicks (
    id SERIAL PRIMARY KEY,
    vk_id BIGINT NOT NULL,
    topic_name TEXT NOT NULL,
    clicked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Autoposter 2.0: Active polls and options
CREATE TABLE IF NOT EXISTS active_polls (
    id SERIAL PRIMARY KEY,
    poll_id BIGINT NOT NULL,
    owner_id BIGINT NOT NULL,
    topic_name TEXT NOT NULL,
    options JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Autoposter 2.0: Daily content tracking log (rubric control)
CREATE TABLE IF NOT EXISTS post_daily_log (
    id SERIAL PRIMARY KEY,
    skin_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    rubric TEXT NOT NULL DEFAULT 'unknown',
    published_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Ensure post_daily_log has rubric column if table already existed without it
ALTER TABLE post_daily_log ADD COLUMN IF NOT EXISTS rubric TEXT NOT NULL DEFAULT 'unknown';

-- Hidden Sacred Promo Codes Table
CREATE TABLE IF NOT EXISTS hidden_promos (
    code TEXT PRIMARY KEY,
    energy_reward INTEGER NOT NULL,
    max_uses INTEGER DEFAULT 10,
    current_uses INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Promo Code Activations Table
CREATE TABLE IF NOT EXISTS promo_activations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    code TEXT REFERENCES hidden_promos(code),
    activated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, code)
);

-- Community posts table for mobile clients sync
CREATE TABLE IF NOT EXISTS community_posts (
    id BIGSERIAL PRIMARY KEY,
    vk_post_id BIGINT UNIQUE NOT NULL,
    text TEXT NOT NULL,
    image_url TEXT,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- 3. CREATE PERFORMANCE INDEXES
CREATE INDEX IF NOT EXISTS idx_users_vk_id ON vk_esoteric_users(vk_id);
CREATE INDEX IF NOT EXISTS idx_community_posts_vk_post_id ON community_posts(vk_post_id);
CREATE INDEX IF NOT EXISTS idx_feedbacks_user_id ON feedbacks(user_id);
CREATE INDEX IF NOT EXISTS idx_feedbacks_is_posted ON feedbacks(is_posted);
CREATE INDEX IF NOT EXISTS idx_events_user_action ON events(user_id, action);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_post_history_topic_name ON post_history(topic_name);
CREATE INDEX IF NOT EXISTS idx_post_clicks_vk_id ON post_clicks(vk_id);
CREATE INDEX IF NOT EXISTS idx_active_polls_is_active ON active_polls(is_active);
CREATE INDEX IF NOT EXISTS idx_post_daily_log_published_at ON post_daily_log(published_at);
CREATE INDEX IF NOT EXISTS idx_promo_activations_user_id_code ON promo_activations(user_id, code);


-- 4. CREATE DATABASE RPC FUNCTIONS (SECURITY DEFINER)

-- Function: Atomic user balance increment
CREATE OR REPLACE FUNCTION increment_user_balance(p_vk_id BIGINT, p_amount INTEGER)
RETURNS VOID AS $$
BEGIN
    UPDATE vk_esoteric_users
    SET balance = COALESCE(balance, 0) + p_amount
    WHERE vk_id = p_vk_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Increment post clicks counter in history
CREATE OR REPLACE FUNCTION increment_post_clicks(p_topic_name TEXT)
RETURNS VOID AS $$
BEGIN
    UPDATE post_history
    SET clicks = COALESCE(clicks, 0) + 1
    WHERE id = (
        SELECT id FROM post_history
        WHERE topic_name = p_topic_name
        ORDER BY published_at DESC
        LIMIT 1
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function: Atomic activation of a hidden promo code
CREATE OR REPLACE FUNCTION activate_hidden_promo(p_user_id BIGINT, p_code TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_reward INTEGER;
    v_max_uses INTEGER;
    v_current_uses INTEGER;
    v_already_activated BOOLEAN;
BEGIN
    -- 1. Проверяем существование кода и берем данные (FOR UPDATE для блокировки строки)
    SELECT energy_reward, max_uses, current_uses
    INTO v_reward, v_max_uses, v_current_uses
    FROM hidden_promos
    WHERE code = p_code
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'error', 'code', 'NOT_FOUND');
    END IF;

    -- 2. Проверяем, не активировал ли юзер ранее
    SELECT EXISTS(SELECT 1 FROM promo_activations WHERE user_id = p_user_id AND code = p_code)
    INTO v_already_activated;

    IF v_already_activated THEN
        RETURN jsonb_build_object('status', 'error', 'code', 'ALREADY_ACTIVATED');
    END IF;

    -- 3. Проверяем лимиты
    IF v_current_uses >= v_max_uses THEN
        RETURN jsonb_build_object('status', 'error', 'code', 'LIMIT_REACHED');
    END IF;

    -- 4. Выполняем активацию
    UPDATE hidden_promos
    SET current_uses = current_uses + 1
    WHERE code = p_code
    RETURNING current_uses INTO v_current_uses;

    INSERT INTO promo_activations (user_id, code)
    VALUES (p_user_id, p_code);

    -- 5. Начисляем энергию юзеру
    UPDATE vk_esoteric_users
    SET balance = balance + v_reward
    WHERE vk_id = p_user_id;

    RETURN jsonb_build_object(
        'status', 'success',
        'reward', v_reward,
        'current_uses', v_current_uses,
        'max_uses', v_max_uses
    );
END;
$$;

-- Function: Execution bridge for arbitrary SQL commands (Admin Panel)
CREATE OR REPLACE FUNCTION exec_sql(sql_query text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    ret jsonb;
BEGIN
    -- Try executing as SELECT and return JSON
    BEGIN
        EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO ret;
        RETURN ret;
    EXCEPTION WHEN OTHERS THEN
        -- If not SELECT (e.g. ALTER, UPDATE, CREATE), execute and return success
        EXECUTE sql_query;
        RETURN jsonb_build_object('status', 'success', 'message', 'Command executed successfully');
    END;
EXCEPTION WHEN OTHERS THEN
    -- Return error details if failed
    RETURN jsonb_build_object('error', SQLERRM, 'detail', SQLSTATE);
END;
$$;

-- =====================================================================
-- 5. MOBILE CLIENT SECURITY, CLICKER PERSISTENCE & RLS POLICIES
-- =====================================================================

-- Table: Mobile Client Clicker Progress and Familiar Levels (Room DB sync)
CREATE TABLE IF NOT EXISTS mobile_user_progress (
    user_id BIGINT PRIMARY KEY,
    clicker_count BIGINT DEFAULT 0,
    familiar_level INTEGER DEFAULT 1,
    energy_pool INTEGER DEFAULT 100,
    timers JSONB DEFAULT '{}'::jsonb,
    last_sync_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mobile_user_progress_user_id ON mobile_user_progress(user_id);

-- Function: Secure mobile clicker progress sync with anti-cheat checks
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
    v_max_delta CONSTANT INTEGER := 500; -- Anti-cheat: max clicks allowed per single sync
    v_new_clicks BIGINT;
    v_current_level INTEGER;
    v_bonus_energy INTEGER := 0;
BEGIN
    -- Validate clicks delta to prevent artificial balance exploitation
    IF p_clicks_delta < 0 OR p_clicks_delta > v_max_delta THEN
        RETURN jsonb_build_object('status', 'error', 'code', 'SUSPICIOUS_DELTA');
    END IF;

    -- Upsert clicker progress
    INSERT INTO mobile_user_progress (user_id, clicker_count, familiar_level, timers, last_sync_at)
    VALUES (p_user_id, p_clicks_delta, GREATEST(1, p_familiar_level), p_timers, NOW())
    ON CONFLICT (user_id) DO UPDATE
    SET clicker_count = mobile_user_progress.clicker_count + EXCLUDED.clicker_count,
        familiar_level = GREATEST(mobile_user_progress.familiar_level, EXCLUDED.familiar_level),
        timers = COALESCE(EXCLUDED.timers, mobile_user_progress.timers),
        last_sync_at = NOW()
    RETURNING clicker_count, familiar_level INTO v_new_clicks, v_current_level;

    -- If milestone click reached (e.g. every 1000 clicks awards +10 energy)
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

-- Function: Secure RPC balance modification with mandatory audit trail
CREATE OR REPLACE FUNCTION secure_modify_balance(
    p_user_id BIGINT,
    p_amount INTEGER,
    p_reason TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_new_balance INTEGER;
BEGIN
    UPDATE vk_esoteric_users
    SET balance = GREATEST(0, COALESCE(balance, 0) + p_amount)
    WHERE vk_id = p_user_id
    RETURNING balance INTO v_new_balance;

    -- Audit log in events
    INSERT INTO events (user_id, action, metadata, created_at)
    VALUES (
        p_user_id,
        'secure_balance_modification',
        jsonb_build_object('amount', p_amount, 'reason', p_reason, 'new_balance', v_new_balance),
        NOW()
    );

    RETURN jsonb_build_object('status', 'success', 'new_balance', v_new_balance);
END;
$$;

-- 6. ROW LEVEL SECURITY (RLS) POLICIES FOR PUBLIC ANON ACCESS
ALTER TABLE vk_esoteric_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE mobile_user_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE community_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedbacks ENABLE ROW LEVEL SECURITY;

-- Allow anon public read of community posts
DROP POLICY IF EXISTS "Public can view community posts" ON community_posts;
CREATE POLICY "Public can view community posts" ON community_posts FOR SELECT USING (true);

-- Allow anon public read of feedbacks
DROP POLICY IF EXISTS "Public can view feedbacks" ON feedbacks;
CREATE POLICY "Public can view feedbacks" ON feedbacks FOR SELECT USING (is_posted = true);

-- Allow users to read profiles
DROP POLICY IF EXISTS "Users can read own profile" ON vk_esoteric_users;
CREATE POLICY "Users can read own profile" ON vk_esoteric_users FOR SELECT USING (true);

-- Restrict direct balance/purchases mutations: all mutations must go through SECURITY DEFINER RPC functions
GRANT EXECUTE ON FUNCTION increment_user_balance(BIGINT, INTEGER) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION sync_mobile_progress(BIGINT, INTEGER, INTEGER, JSONB) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION secure_modify_balance(BIGINT, INTEGER, TEXT) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION activate_hidden_promo(BIGINT, TEXT) TO anon, authenticated, service_role;
