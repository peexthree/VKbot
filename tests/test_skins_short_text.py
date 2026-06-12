import pytest
from unittest.mock import AsyncMock, patch
from modules.skins import get_short_quest_text

@pytest.mark.asyncio
async def test_get_short_quest_text_length():
    # Mock user data for all skins
    mock_user = {
        "active_referrals_count": 2,
        "visit_streak": 3,
        "rituals_count": 15,
        "dreams_analyzed_count": 5,
        "compatibility_partners_count": 1,
        "used_skins_count": 1,
        "tags": ["выход-из-кризиса"],
        "readings_history": [{"section": "sex"}, {"section": "money"}],
        "balance": 1000
    }

    skins = ["fluffy", "vanga", "ai_mom", "pythia", "freud", "cleopatra", "anubis", "honest_oracle", "jack_sparrow", "saint_germain"]

    with patch("modules.skins.get_user", new_callable=AsyncMock) as mock_get_user, \
         patch("cache.get_temp_birth_data", new_callable=AsyncMock) as mock_get_temp_birth:
        mock_get_user.return_value = mock_user
        mock_get_temp_birth.return_value = {"date": "10.10.1990", "time": "10:00", "city": "Moscow"}

        for skin in skins:
            text = await get_short_quest_text(12345, skin)
            print(f"Skin: {skin}, Text: {text}, Length: {len(text)}")
            assert len(text) <= 80
            assert "\n" not in text

@pytest.mark.asyncio
async def test_get_short_quest_text_anubis_special():
    mock_user = {
        "unlocked_cards": {},
        "total_cards_received": 0,
        "readings_history": [{"section": s} for s in ["sex", "money", "shadow", "final", "synastry", "palmistry", "dream", "oracle", "antitaro"]]
    }

    with patch("modules.skins.get_user", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = mock_user
        text = await get_short_quest_text(12345, "anubis")
        assert "Разделы: 9/9" in text
        assert len(text) <= 80
