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
