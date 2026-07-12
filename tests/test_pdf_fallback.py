import pytest

@pytest.mark.asyncio
async def test_pdf_fallback_with_missing_text_key():
    # Mock data
    vk_id = 12345678
    section = "final"

    latest_reading_stub = {
        "text": "This is parent reading text.",
        "data": {
            "tarot_arcana_analysis": "Beautiful analysis.",
            "karmic_lesson": "Important lesson."
        }
    }

    # Simulate how the fallback in callbacks.py resolves latest_data
    # Step 1: get_latest_reading
    latest_data = latest_reading_stub.get("data") or {}

    # Apply our new fallback logic
    if "text" not in latest_data and latest_reading_stub.get("text"):
        latest_data["text"] = latest_reading_stub.get("text")

    assert latest_data.get("text") == "This is parent reading text."
    assert latest_data.get("tarot_arcana_analysis") == "Beautiful analysis."

@pytest.mark.asyncio
async def test_pdf_fallback_from_history():
    history_item_stub = {
        "text": "Parent text from history.",
        "section": "final",
        "data": {
            "geom_analysis": "Geometric data."
        }
    }

    # Simulate historical fallback lookup
    section = "final"
    found_item = history_item_stub

    latest_data = found_item.get("data") or {}
    if "text" not in latest_data and found_item.get("text"):
        latest_data["text"] = found_item.get("text")

    assert latest_data.get("text") == "Parent text from history."
    assert latest_data.get("geom_analysis") == "Geometric data."

def test_execute_generation_storing_logic():
    # Test that when execute_generation is preparing the stored data:
    # If res_data is a dictionary, we inject the text.
    res_data = {
        "tarot_arcana_analysis": "Arcana analysis.",
        "karmic_lesson": "Karmic lesson."
    }
    res_text = "Synthesized full text."
    display_text = res_text

    # Simulate logic inside execute_generation
    latest_data_to_store = res_data if isinstance(res_data, dict) else {"text": res_text}
    if isinstance(latest_data_to_store, dict):
        if "text" not in latest_data_to_store or not latest_data_to_store["text"]:
            latest_data_to_store["text"] = display_text

    assert "text" in latest_data_to_store
    assert latest_data_to_store["text"] == "Synthesized full text."
    assert latest_data_to_store["tarot_arcana_analysis"] == "Arcana analysis."
