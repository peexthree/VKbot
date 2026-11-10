import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

import cache
import modules.admin as admin
from modules.utils import keepalive


@pytest.fixture(autouse=True)
async def _cleanup_keepalive():
    """Сбрасывает in-memory кэш настроек и останавливает фоновую задачу после каждого теста."""
    cache._system_config_cache.clear()
    await keepalive.stop_keepalive_task()
    yield
    await keepalive.stop_keepalive_task()
    cache._system_config_cache.clear()


@pytest.mark.asyncio
async def test_keepalive_disabled_by_default():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    with patch("cache.redis_client", mock_redis):
        assert await keepalive.is_keepalive_enabled() is False
        started = await keepalive.sync_keepalive_task(initial_delay=0.0)
        assert started is False
        assert keepalive._keepalive_task is None


@pytest.mark.asyncio
async def test_keepalive_starts_pings_and_stops_cleanly():
    config_store = {"system_config:keepalive_active": "1"}

    async def fake_get(key):
        return config_store.get(key)

    mock_redis = AsyncMock()
    mock_redis.get.side_effect = fake_get

    pinged_urls = []

    class FakeResp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            pinged_urls.append(url)
            # После первого пинга отключаем флаг, чтобы цикл вышел без бесконечного сна
            config_store["system_config:keepalive_active"] = "0"
            cache._system_config_cache.clear()
            return FakeResp()

    real_sleep = asyncio.sleep

    async def fast_sleep(_delay):
        await real_sleep(0)

    with (
        patch("cache.redis_client", mock_redis),
        patch("modules.utils.keepalive.aiohttp.ClientSession", FakeSession),
        patch("modules.utils.keepalive.asyncio.sleep", side_effect=fast_sleep),
    ):
        started = await keepalive.sync_keepalive_task(initial_delay=0.0)
        assert started is True
        task = keepalive._keepalive_task
        assert task is not None

        # Повторный вызов не плодит дубликат задачи
        started_again = await keepalive.sync_keepalive_task(initial_delay=0.0)
        assert started_again is True
        assert keepalive._keepalive_task is task

        await asyncio.wait_for(task, timeout=2.0)

        assert len(pinged_urls) == 1
        assert pinged_urls[0].endswith("/")
        assert keepalive._keepalive_task is None


@pytest.mark.asyncio
async def test_keepalive_stop_cancels_running_task():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "1"

    with patch("cache.redis_client", mock_redis):
        started = await keepalive.sync_keepalive_task(initial_delay=60.0)
        assert started is True
        task = keepalive._keepalive_task
        assert task is not None and not task.done()

        await keepalive.stop_keepalive_task()
        assert task.done()
        assert keepalive._keepalive_task is None


@pytest.mark.asyncio
async def test_admin_system_menu_shows_keepalive_off_by_default():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.keys.return_value = []

    with (
        patch("cache.redis_client", mock_redis),
        patch("modules.admin.redis_client", mock_redis),
        patch("modules.admin.ghost_edit", new_callable=AsyncMock) as mock_ghost_edit,
    ):
        await admin.show_admin_system(peer_id=123456, conversation_message_id=99, page=0)

        mock_ghost_edit.assert_awaited_once()
        _, peer_id, text = mock_ghost_edit.call_args.args
        keyboard_json = mock_ghost_edit.call_args.kwargs["keyboard"]

        assert peer_id == 123456
        assert "МОНИТОР СНА (9 МИН): 🔴 ВЫКЛ" in text

        kb = json.loads(keyboard_json)
        buttons = kb["buttons"]
        # Ограничения VK inline-клавиатуры: максимум 6 рядов и 10 кнопок
        assert len(buttons) <= 6
        flat_buttons = [btn for row in buttons for btn in row]
        assert len(flat_buttons) <= 10

        def _parse_payload(btn):
            raw = btn["action"]["payload"]
            return raw if isinstance(raw, dict) else json.loads(raw)

        keepalive_btns = [
            btn
            for btn in flat_buttons
            if _parse_payload(btn).get("action") == "toggle_keepalive"
        ]
        assert len(keepalive_btns) == 1
        assert keepalive_btns[0]["action"]["label"] == "🟢 ВКЛ МОНИТОР (9М)"

        # Проверяем также страницу 1 (очистка кэша + назад + в меню)
        await admin.show_admin_system(peer_id=123456, conversation_message_id=99, page=1)
        kb_p1 = json.loads(mock_ghost_edit.call_args.kwargs["keyboard"])
        assert len(kb_p1["buttons"]) <= 6
        assert any(
            btn["action"]["label"] == "🏠 В МЕНЮ"
            for row in kb_p1["buttons"]
            for btn in row
        )


@pytest.mark.asyncio
async def test_admin_toggle_keepalive_updates_config_and_syncs_task():
    store: dict[str, str] = {}

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, val):
        store[key] = val
        return True

    mock_redis = AsyncMock()
    mock_redis.get.side_effect = fake_get
    mock_redis.set.side_effect = fake_set
    mock_redis.keys.return_value = []

    with (
        patch("cache.redis_client", mock_redis),
        patch("modules.admin.redis_client", mock_redis),
        patch("modules.admin.ghost_edit", new_callable=AsyncMock) as mock_ghost_edit,
    ):
        # Не-админ игнорируется
        await admin.process_admin_cmd(
            vk_id=admin.ADMIN_ID + 1,
            peer_id=admin.ADMIN_ID + 1,
            payload={"cmd": "admin_cmd", "action": "toggle_keepalive", "page": 0},
        )
        assert "system_config:keepalive_active" not in store
        assert keepalive._keepalive_task is None

        # Админ включает монитор
        await admin.process_admin_cmd(
            vk_id=admin.ADMIN_ID,
            peer_id=admin.ADMIN_ID,
            payload={"cmd": "admin_cmd", "action": "toggle_keepalive", "page": 0},
            conversation_message_id=101,
        )
        assert store["system_config:keepalive_active"] == "1"
        assert keepalive._keepalive_task is not None and not keepalive._keepalive_task.done()
        text_on = mock_ghost_edit.call_args.args[2]
        assert "МОНИТОР СНА (9 МИН): 🟢 ВКЛ" in text_on
        kb_on = json.loads(mock_ghost_edit.call_args.kwargs["keyboard"])
        assert any(
            btn["action"]["label"] == "🔴 ВЫКЛ МОНИТОР (9М)"
            for row in kb_on["buttons"]
            for btn in row
        )

        # Админ выключает монитор обратно
        await admin.process_admin_cmd(
            vk_id=admin.ADMIN_ID,
            peer_id=admin.ADMIN_ID,
            payload={"cmd": "admin_cmd", "action": "toggle_keepalive", "page": 0},
            conversation_message_id=101,
        )
        assert store["system_config:keepalive_active"] == "0"
        assert keepalive._keepalive_task is None
        text_off = mock_ghost_edit.call_args.args[2]
        assert "МОНИТОР СНА (9 МИН): 🔴 ВЫКЛ" in text_off
