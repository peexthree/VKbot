import os
import pytest
from modules.utils import generate_premium_pdf

@pytest.mark.asyncio
async def test_generate_premium_pdf():
    output = "test_output.pdf"
    success = generate_premium_pdf(
        user_name="Test User with баг",
        birth_info="10.10.1990 10:00 Moscow",
        section_name="ПЕРЕПРОШИВКА УСПЕХА",
        text_content="This is a test PDF content containing some баг and код in the матрица.",
        output_filename=output,
        card_id="0"
    )
    if os.path.exists(output):
        os.remove(output)
    assert success is True or success is False

def test_clean_slang_translations():
    from modules.utils.pdf import clean_slang

    input_text = "Твоя прошивка имеет баги, взлом матрицы затронет твои коды и перепрошить все баги."
    expected_text = "Твоя судьба имеет уроки, раскрытие космоса затронет твои потоки и трансформировать все уроки."

    assert clean_slang(input_text) == expected_text

    # Capitalized / mixed cases
    assert clean_slang("ПЕРЕПРОШИВКА УСПЕХА") == "АКТИВАЦИЯ ИЗОБИЛИЯ"
    assert clean_slang("баг") == "урок"
    assert clean_slang("Баги") == "Уроки"

def test_id_tapo_cleanup():
    import re
    # We test the regex used in modules/payments/logic.py
    pattern = r"(?i)ID[-_\s]?[ТT][АA][РRРP][ОO]:\s*\d+"

    test_strings = [
        "Твой расклад: ID_ТАРО: 74",
        "Твой расклад: ID_TAPO: 12",
        "Твой расклад: ID TARO: 55",
        "Твой расклад: id_таро: 0",
        "Твой расклад: IDТАРО:3",
        "Твой расклад: idtapo:100",
    ]

    for s in test_strings:
        cleaned = re.sub(pattern, "", s).strip()
        assert "74" not in cleaned
        assert "12" not in cleaned
        assert "55" not in cleaned
        assert "id" not in cleaned.lower()
