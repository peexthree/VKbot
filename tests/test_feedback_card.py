import os
import io
import pytest
from PIL import Image
from modules.support import create_neon_feedback_card

def test_create_neon_feedback_card_placeholder():
    output_path = "cards/test_feedback_placeholder.png"
    if os.path.exists(output_path):
        os.remove(output_path)

    try:
        # Standard generation with placeholder avatar (None)
        create_neon_feedback_card(
            user_name="Алексей Проводник",
            section_name="Денежный канал",
            rating=5,
            comment="Этот расклад полностью открыл мне глаза на финансовые потоки! Спасибо Вселенной за интуицию и проводников.",
            output_path=output_path,
            user_avatar_bytes=None,
            active_skin="nostradamus",
            feedback_id=12345,
            created_at="2024-12-01T15:30:00Z"
        )

        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0

        # Verify it's a valid image with correct dimensions
        with Image.open(output_path) as img:
            assert img.size == (1200, 800)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_create_neon_feedback_card_with_avatar():
    output_path = "cards/test_feedback_avatar.png"
    if os.path.exists(output_path):
        os.remove(output_path)

    try:
        # Create a dummy user avatar in bytes
        dummy_avatar = Image.new('RGBA', (200, 200), (142, 68, 173, 255))
        buffer = io.BytesIO()
        dummy_avatar.save(buffer, format="PNG")
        avatar_bytes = buffer.getvalue()

        # Generation with custom avatar bytes
        create_neon_feedback_card(
            user_name="Мария",
            section_name="Сексуальность",
            rating=4,
            comment="Очень глубокий разбор моей теневой стороны. Помогло проработать блоки.",
            output_path=output_path,
            user_avatar_bytes=avatar_bytes,
            active_skin="olesya",
            feedback_id=98765,
            created_at="2024-11-28T09:15:00Z"
        )

        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0

        with Image.open(output_path) as img:
            assert img.size == (1200, 800)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_create_neon_feedback_card_font_scaling():
    output_path = "cards/test_feedback_scaling.png"
    if os.path.exists(output_path):
        os.remove(output_path)

    try:
        # Create a very long comment to trigger font scaling and text truncation
        very_long_comment = (
            "Это просто невероятно огромный отзыв, который точно превысит обычные лимиты "
            "и заставит алгоритм автоподбора размера шрифта уменьшать его на лету. Мы пишем "
            "очень много текста, чтобы проверить, как работает наш бинарный поиск или "
            "шаговое уменьшение шрифта. Текст должен красиво завернуться во внутреннюю рамку "
            "карточки, не пересекаясь со знаком проводника в правом нижнем углу и сохраняя "
            "отступ снизу минимум в 45 пикселей. Давайте добавим еще предложений, чтобы "
            "быть уверенными, что лимит в 280 символов сработает отлично и обрежет "
            "этот гигантский отзыв на лету, оставив красивое троеточие в конце."
        )

        create_neon_feedback_card(
            user_name="Екатерина Великая",
            section_name="Теневая матрица",
            rating=5,
            comment=very_long_comment,
            output_path=output_path,
            user_avatar_bytes=None,
            active_skin="cleopatra",
            feedback_id=55555,
            created_at="2024-12-05T22:11:00Z"
        )

        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0

        with Image.open(output_path) as img:
            assert img.size == (1200, 800)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
