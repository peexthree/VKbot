import os
from modules.tarot.secret_arts_logic import (
    generate_sigil_image,
    process_oculomancy_eye,
    calculate_alchemy_element,
    get_random_egyptian_oracle,
    get_random_shadow_oracle
)

def test_calculate_alchemy_element():
    # 15.04.1990 -> 1+5+0+4 = 10 -> 1+0 = 1 (Философская Ртуть)
    el = calculate_alchemy_element("15.04.1990")
    assert el["name"] == "ФИЛОСОФСКАЯ РТУТЬ"

    # 16.04.1990 -> 1+6+0+4 = 11 -> 1+1 = 2 (Сера)
    el2 = calculate_alchemy_element("16.04.1990")
    assert el2["name"] == "СЕРА"

    # 17.04.1990 -> 1+7+0+4 = 12 -> 1+2 = 3 (Соль)
    el3 = calculate_alchemy_element("17.04.1990")
    assert el3["name"] == "СОЛЬ"


def test_get_random_oracles():
    egypt = get_random_egyptian_oracle()
    assert len(egypt) == 3
    assert all("name" in d and "desc" in d for d in egypt)

    shadow = get_random_shadow_oracle()
    assert len(shadow) == 3
    assert all("name" in d and "desc" in d for d in shadow)


def test_generate_sigil_image_default_bg(tmp_path):
    output_file = os.path.join(tmp_path, "test_sigil.jpeg")

    # Запускаем генерацию сигила без реального фонового файла (создастся дефолтный фон)
    success = generate_sigil_image("хочу стать великим магом", output_file, background_path="nonexistent.jpeg")
    assert success is True
    assert os.path.exists(output_file)


def test_process_oculomancy_eye_dummy_file(tmp_path):
    output_file = os.path.join(tmp_path, "test_eye_out.jpeg")

    # Создаем фиктивное маленькое изображение глаза для теста
    from PIL import Image
    dummy_eye_path = os.path.join(tmp_path, "dummy_eye.png")
    Image.new("RGBA", (200, 200), (100, 50, 200, 255)).save(dummy_eye_path)

    success = process_oculomancy_eye(dummy_eye_path, output_file, background_path="nonexistent.jpeg")
    assert success is True
    assert os.path.exists(output_file)

def test_service_groups_and_synthesis():
    from prompts.services import SERVICE_GROUP_MAP, get_group_prompt
    from modules.payments.logic import synthesize_chat_text

    # Verify service mappings
    assert SERVICE_GROUP_MAP["sigil"] == "A"
    assert SERVICE_GROUP_MAP["oculomancy"] == "B"
    assert SERVICE_GROUP_MAP["palmistry"] == "B"
    assert SERVICE_GROUP_MAP["totem"] == "C"
    assert SERVICE_GROUP_MAP["alchemist"] == "D"
    assert SERVICE_GROUP_MAP["sex"] == "E"

    # Verify prompt selection
    prompt_a = get_group_prompt("sigil")
    assert "geom_analysis" in prompt_a
    assert "activation_ritual" in prompt_a

    prompt_b = get_group_prompt("oculomancy")
    assert "iris_or_line_decoding" in prompt_b

    # Verify synthesis
    data_a = {
        "geom_analysis": "Круг выражает полноту.",
        "activation_ritual": "Медитируйте 5 минут.",
        "energy_vector": "Действуйте уверенно.",
        "focus_mantras": ["МАНТРА 1", "МАНТРА 2"]
    }
    chat_text_a = synthesize_chat_text(data_a, "sigil")
    assert "СИГИЛ-МАСТЕР" in chat_text_a
    assert "МАНТРА 1" in chat_text_a

    data_b = {
        "iris_or_line_decoding": "У вас глубокая радужка.",
        "spiritual_vulnerability": "Некоторые блоки видны.",
        "intuition_unlk": "Слушайте внутренний голос.",
        "daily_mudras": "Практикуйте по утрам."
    }
    chat_text_b = synthesize_chat_text(data_b, "oculomancy")
    assert "ОКУЛОМАНТИЯ" in chat_text_b
    assert "У вас глубокая радужка" in chat_text_b
