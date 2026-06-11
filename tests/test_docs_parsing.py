
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from modules.utils.docs import upload_pdf_to_vk
import os

@pytest.mark.asyncio
async def test_upload_pdf_to_vk_parsing_success():
    # Mock bot_api
    bot_api = AsyncMock()

    # Mock get_messages_upload_server
    server_mock = MagicMock()
    server_mock.upload_url = "http://upload.url"
    bot_api.docs.get_messages_upload_server.return_value = server_mock

    # Mock docs.save response (raw format as described in the issue)
    raw_response = {
        "response": {
            "type": "doc",
            "doc": {
                "id": 702463127,
                "owner_id": 27260796,
                "access_key": "test_access_key"
            }
        }
    }
    bot_api.request.return_value = raw_response

    # Create a dummy file
    filepath = "test_palmistry.pdf"
    with open(filepath, "wb") as f:
        f.write(b"dummy pdf content")

    # Mock aiohttp
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {"file": "uploaded_file_data"}
        mock_resp.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_resp

        attachment = await upload_pdf_to_vk(bot_api, filepath, "palmistry.pdf", 12345)

    assert attachment == "doc27260796_702463127_test_access_key"
    assert not os.path.exists(filepath)

@pytest.mark.asyncio
async def test_upload_pdf_to_vk_parsing_no_access_key():
    # Mock bot_api
    bot_api = AsyncMock()

    # Mock get_messages_upload_server
    server_mock = MagicMock()
    server_mock.upload_url = "http://upload.url"
    bot_api.docs.get_messages_upload_server.return_value = server_mock

    # Mock docs.save response without access_key
    raw_response = {
        "response": {
            "type": "doc",
            "doc": {
                "id": 123456,
                "owner_id": 654321
            }
        }
    }
    bot_api.request.return_value = raw_response

    # Create a dummy file
    filepath = "test_no_key.pdf"
    with open(filepath, "wb") as f:
        f.write(b"dummy pdf content")

    # Mock aiohttp
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {"file": "uploaded_file_data"}
        mock_resp.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_resp

        attachment = await upload_pdf_to_vk(bot_api, filepath, "test.pdf", 12345)

    assert attachment == "doc654321_123456"
    assert not os.path.exists(filepath)
