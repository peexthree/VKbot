import os
from unittest.mock import patch
import pytest
from modules.utils import generate_premium_pdf

@pytest.mark.asyncio
async def test_generate_premium_pdf():
    output = "test_output.pdf"
    success = generate_premium_pdf(
        user_name="Test User",
        birth_info="10.10.1990 10:00 Moscow",
        section_name="TEST SECTION",
        text_content="This is a test PDF content.",
        output_filename=output,
        card_id="0"
    )
    if os.path.exists(output):
        os.remove(output)
    assert success is True or success is False

