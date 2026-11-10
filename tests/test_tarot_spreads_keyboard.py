import json
from unittest.mock import AsyncMock, patch

import pytest

from configs.tarot_spreads import TAROT_SPREADS
from modules.tarot import spreads_logic


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spread_key",
    [k for k, v in TAROT_SPREADS.items() if v["cards_count"] <= 10],
)
async def test_interactive_spreads_respect_vk_inline_button_limit(spread_key):
    saved_states: list[str] = []

    async def fake_set_state(_vk_id, data):
        saved_states.append(data)

    with (
        patch("modules.tarot.spreads_logic.set_user_state", side_effect=fake_set_state),
        patch("modules.tarot.spreads_logic.upload_local_photo", new_callable=AsyncMock, return_value="photo-1_2"),
        patch("modules.tarot.spreads_logic.ghost_edit", new_callable=AsyncMock),
    ):
        await spreads_logic.initiate_spread_flow(
            vk_id=1001, peer_id=1001, spread_key=spread_key, edit_msg_id=55
        )

    state = json.loads(saved_states[-1])
    pool = state["pool"]
    expected_count = TAROT_SPREADS[spread_key]["cards_count"]
    assert len(pool) <= 10
    assert len(pool) >= expected_count

    with (
        patch("modules.tarot.spreads_logic.get_fsm_step", new_callable=AsyncMock, return_value=state),
        patch("modules.tarot.spreads_logic.set_user_state", side_effect=fake_set_state),
        patch("modules.tarot.spreads_logic.safe_edit", new_callable=AsyncMock) as mock_safe_edit,
    ):
        await spreads_logic.handle_spread_cut(
            vk_id=1001, peer_id=1001, spread_key=spread_key, edit_msg_id=55
        )

    mock_safe_edit.assert_awaited_once()
    kb = json.loads(mock_safe_edit.call_args.kwargs["keyboard"])
    rows = kb["buttons"]
    flat = [btn for row in rows for btn in row]
    assert len(rows) <= 6
    assert all(len(row) <= 5 for row in rows)
    assert len(flat) == len(pool) <= 10


@pytest.mark.asyncio
async def test_handle_spread_cut_caps_legacy_oversized_pool():
    # Имитируем старое состояние из Redis, где pool содержал 11 карт для расклада на 7 карт
    legacy_state = {
        "step": "spread_cut",
        "spread_key": "tarot_future",
        "pool": list(range(11)),
        "full_deck": list(range(78)),
        "drawn_cards": [],
    }
    saved_states: list[str] = []

    async def fake_set_state(_vk_id, data):
        saved_states.append(data)

    with (
        patch("modules.tarot.spreads_logic.get_fsm_step", new_callable=AsyncMock, return_value=legacy_state),
        patch("modules.tarot.spreads_logic.set_user_state", side_effect=fake_set_state),
        patch("modules.tarot.spreads_logic.safe_edit", new_callable=AsyncMock) as mock_safe_edit,
    ):
        await spreads_logic.handle_spread_cut(
            vk_id=27260796, peer_id=27260796, spread_key="tarot_future", edit_msg_id=777
        )

    kb = json.loads(mock_safe_edit.call_args.kwargs["keyboard"])
    flat = [btn for row in kb["buttons"] for btn in row]
    assert len(flat) == 10
    persisted = json.loads(saved_states[-1])
    assert len(persisted["pool"]) == 10


@pytest.mark.asyncio
async def test_handle_spread_card_draw_progression_and_completion():
    state = {
        "step": "spread_draw",
        "spread_key": "tarot_future",
        "pool": list(range(10)),
        "full_deck": list(range(78)),
        "drawn_cards": [0, 1, 2, 3, 4, 5],
    }
    saved_states: list[str] = []

    async def fake_set_state(_vk_id, data):
        saved_states.append(data)

    # 6/7 -> кликаем карту 6, остается еще? Нет, 7-я карта завершает расклад!
    # Сначала проверим 5/7 -> 6/7 (промежуточный шаг)
    state_5 = dict(state, drawn_cards=[0, 1, 2, 3, 4])
    with (
        patch("modules.tarot.spreads_logic.get_fsm_step", new_callable=AsyncMock, return_value=state_5),
        patch("modules.tarot.spreads_logic.set_user_state", side_effect=fake_set_state),
        patch("modules.tarot.spreads_logic.safe_edit", new_callable=AsyncMock) as mock_safe_edit,
    ):
        await spreads_logic.handle_spread_card_draw(
            vk_id=1001, peer_id=1001, card_id=5, spread_key="tarot_future", edit_msg_id=88
        )

    assert "6/7" in mock_safe_edit.call_args.kwargs["message"]
    kb = json.loads(mock_safe_edit.call_args.kwargs["keyboard"])
    assert sum(len(r) for r in kb["buttons"]) == 4  # 10 - 6 drawn = 4 remaining

    # Финальная 7-я карта -> запуск execute_spread_reading
    def fake_create_task(coro):
        coro.close()
        return None

    with (
        patch("modules.tarot.spreads_logic.get_fsm_step", new_callable=AsyncMock, return_value=state),
        patch("modules.tarot.spreads_logic.set_user_state", side_effect=fake_set_state),
        patch("modules.tarot.spreads_logic.safe_edit", new_callable=AsyncMock) as mock_safe_edit,
        patch("modules.tarot.spreads_logic.asyncio.create_task", side_effect=fake_create_task) as mock_task,
    ):
        await spreads_logic.handle_spread_card_draw(
            vk_id=1001, peer_id=1001, card_id=6, spread_key="tarot_future", edit_msg_id=88
        )

    assert saved_states[-1] == ""
    assert "ВСЕ 7 КАРТ СОБРАНЫ" in mock_safe_edit.call_args.kwargs["message"]
    mock_task.assert_called_once()
