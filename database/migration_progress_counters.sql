-- Миграция для добавления счетчиков прогресса в таблицу users
-- Миграция для добавления счетчиков прогресса в таблицу vk_esoteric_users
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS used_skins_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS compatibility_partners_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS compatibility_partners_hashes TEXT[] DEFAULT '{}';
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS dreams_analyzed_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS rituals_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS active_referrals_count INTEGER DEFAULT 0;
ALTER TABLE vk_esoteric_users ADD COLUMN IF NOT EXISTS level_3_counted BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN vk_esoteric_users.used_skins_count IS 'Количество уникальных масок, которые применил юзер';
COMMENT ON COLUMN vk_esoteric_users.compatibility_partners_count IS 'Количество уникальных партнеров, с кем юзер проверил совместимость';
COMMENT ON COLUMN vk_esoteric_users.compatibility_partners_hashes IS 'Список хэшей (имя+дата) партнеров для проверки уникальности';
COMMENT ON COLUMN vk_esoteric_users.dreams_analyzed_count IS 'Количество успешных генераций в Соннике';
COMMENT ON COLUMN vk_esoteric_users.rituals_count IS 'Общий счетчик всех вызовов ИИ-сервисов';
COMMENT ON COLUMN vk_esoteric_users.active_referrals_count IS 'Количество рефералов, достигших 3 уровня';
COMMENT ON COLUMN vk_esoteric_users.level_3_counted IS 'Флаг, что данный юзер уже был засчитан как активный реферал 3 уровня для своего пригласившего';
