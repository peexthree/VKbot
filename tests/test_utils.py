import json
import pytest
from unittest.mock import MagicMock
import sys

# Pre-mocking to avoid import errors in modules.utils
mock_vkbottle = MagicMock()
sys.modules['vkbottle'] = mock_vkbottle
sys.modules['aiohttp'] = MagicMock()
sys.modules['aiofiles'] = MagicMock()
sys.modules['loguru'] = MagicMock()
sys.modules['jinja2'] = MagicMock()
sys.modules['weasyprint'] = MagicMock()
sys.modules['upstash_redis'] = MagicMock()
sys.modules['upstash_redis.asyncio'] = MagicMock()
sys.modules['database'] = MagicMock()
sys.modules['cache'] = MagicMock()
sys.modules['modules.bot_init'] = MagicMock()

def test_get_dynamic_keyboard():
    # Setup mock behavior for Keyboard
    mock_instance = MagicMock()
    mock_vkbottle.Keyboard.return_value = mock_instance

    # Track buttons and structure
    buttons = []
    current_row = []

    def mock_add(text_obj, color=None):
        current_row.append({"label": text_obj["label"] if isinstance(text_obj, dict) else str(text_obj), "color": str(color)})
        return mock_instance

    def mock_row():
        nonlocal current_row
        buttons.append(current_row)
        current_row = []
        return mock_instance

    def mock_get_json():
        if current_row:
            buttons.append(current_row)
        return json.dumps({"inline": mock_instance.inline, "buttons": buttons})

    mock_instance.add.side_effect = mock_add
    mock_instance.row.side_effect = mock_row
    mock_instance.get_json.side_effect = mock_get_json
    mock_instance.inline = False

    mock_vkbottle.Text.side_effect = lambda t: {"label": t}
    mock_vkbottle.KeyboardButtonColor.PRIMARY = "primary"
    mock_vkbottle.KeyboardButtonColor.SECONDARY = "secondary"

    # Now import the function to test
    from modules.utils import get_dynamic_keyboard
    keyboard_json = get_dynamic_keyboard()

    # Verify it returns a string
    assert isinstance(keyboard_json, str)

    # Parse the JSON to verify its structure
    keyboard_data = json.loads(keyboard_json)

    # Check that it's not an inline keyboard
    assert keyboard_data.get("inline") is False

    # Extract all button labels
    all_buttons = keyboard_data.get("buttons", [])
    labels = []
    for row in all_buttons:
        for button in row:
            labels.append(button.get("label"))

    # Check for expected button labels
    expected_labels = [
        "✦ Услуги",
        "🛰 ТАРИФЫ",
        "🃏 Карта дня",
        "✦ Мой профиль",
        "📖 Путеводитель"
    ]

    for expected in expected_labels:
        assert expected in labels, f"Button with label '{expected}' not found in keyboard"

    # Verify specific structure
    assert len(all_buttons) == 3
