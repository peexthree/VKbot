-- Создание таблиц для Скрытых Сакральных Шифров
CREATE TABLE IF NOT EXISTS hidden_promos (
    code TEXT PRIMARY KEY,
    energy_reward INTEGER NOT NULL,
    max_uses INTEGER DEFAULT 10,
    current_uses INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS promo_activations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    code TEXT REFERENCES hidden_promos(code),
    activated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE(user_id, code)
);

-- RPC функция для атомарной активации
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

    -- 5. Начисляем энергию юзеру (используем имя таблицы из конфига, обычно vk_esoteric_users)
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
