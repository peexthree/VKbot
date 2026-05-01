import os
import asyncio
from google import genai
from google.genai import types

def process_image(prompt_type: str, image_bytes: bytes) -> bytes | None:
    api_keys_str = os.environ.get('GEMINI_API_KEYS', '')
    if not api_keys_str:
        # Fallback to single key if multiple not provided
        api_keys_str = os.environ.get('GEMINI_API_KEY', '')

    api_keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
    if not api_keys:
        print("No API keys provided")
        return None

    base_instruction = (
        "Важнейшее правило: приоритет отдается чертам лица и объекта из исходника. "
        "Сохранять точную идентичность, адаптируя только позу, освещение и фон. "
        "Не изменять основную структуру. "
    )

    if prompt_type == "Премиум минимализм":
        style_instruction = "Сделать картинку строгой, убрать лишний шум и добавить бизнес-эстетику."
    elif prompt_type == "Продающий стиль":
        style_instruction = "Добавить коммерческий лоск и продающий стиль."
    elif prompt_type == "Улучшить свет":
        style_instruction = "Сделать профессиональную цветокоррекцию и улучшить свет."
    else:
        style_instruction = ""

    prompt = base_instruction + style_instruction

    last_exception = None

    for api_key in api_keys:
        client = genai.Client(api_key=api_key)
        try:
            result = client.models.edit_image(
                model='imagen-4-generate',
                prompt=prompt,
                reference_images=[
                    types.RawReferenceImage(
                        reference_id=1,
                        reference_image=types.Image(
                            image_bytes=image_bytes,
                            mime_type="image/jpeg"
                        )
                    )
                ],
                config=types.EditImageConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg"
                )
            )
            return result.generated_images[0].image.image_bytes
        except Exception as e:
            last_exception = e
            error_msg = str(e).lower()
            # If rate limit or quota exceeded, rotate key
            if "429" in error_msg or "resource exhausted" in error_msg or "quota" in error_msg:
                print(f"Rate limit hit for key. Rotating... Error: {e}")
                continue
            else:
                # Some other error, break out or rotate as well?
                # Best effort is to rotate in case other keys work, but let's just log and continue
                print(f"API Error: {e}. Trying next key if available.")
                continue

    print(f"All keys exhausted or failed. Last error: {last_exception}")
    return None
