-- SQL Script to synchronize Supabase database with current bot version
-- Run this in Supabase SQL Editor

ALTER TABLE vk_esoteric_users
ADD COLUMN IF NOT EXISTS first_name TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS birth_date TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS birth_time TEXT DEFAULT '12:00',
ADD COLUMN IF NOT EXISTS birth_city TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS free_teaser_used BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_subscribed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS compatibility_balance INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS core_profile TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS partners JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS free_card_used BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS purchased_sections JSONB DEFAULT '{"sex": false, "money": false, "shadow": false, "final": false, "sex_val": 0, "oracle_access": false, "card_of_day_last_used": null, "conversion_step": "started"}',
ADD COLUMN IF NOT EXISTS has_full_chart BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS forecast_time TEXT,
ADD COLUMN IF NOT EXISTS balance INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS oracle_last_used TEXT,
ADD COLUMN IF NOT EXISTS has_priority_access BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS bonuses INTEGER,
ADD COLUMN IF NOT EXISTS last_active_date TEXT,
ADD COLUMN IF NOT EXISTS active_skin TEXT DEFAULT 'olesya',
ADD COLUMN IF NOT EXISTS purchased_skins JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS transit_trial_days INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS transit_sub_expires_at TEXT,
ADD COLUMN IF NOT EXISTS unlocked_cards JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS weekly_log JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS visit_streak INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_cards_received INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_daily_bonus_date TEXT,
ADD COLUMN IF NOT EXISTS welcome_bonus_received BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS latest_reading_text TEXT,
ADD COLUMN IF NOT EXISTS latest_reading_data JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS readings_history JSONB DEFAULT '[]';

-- Table for transactions tracking (if missing)
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    action TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
