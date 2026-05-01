import os
import aiohttp
import base64

async def process_image(prompt_type: str, image_bytes: bytes) -> bytes | None:
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

    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    last_exception = None

    for api_key in api_keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3:predict?key={api_key}"
        payload = {
            "instances": [{"prompt": prompt, "image": {"bytesBase64Encoded": image_base64}}],
            "parameters": {"sampleCount": 1}
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        res_data = await resp.json()
                        output_b64 = res_data['predictions'][0]['bytesBase64Encoded']
                        return base64.b64decode(output_b64)
                    elif resp.status == 429:
                        print(f"Rate limit hit for key. Rotating...")
                        continue
                    else:
                        print(f"API Error status {resp.status}. Trying next key if available.")
                        error_text = await resp.text()
                        print(f"Error details: {error_text}")
                        continue
            except Exception as e:
                last_exception = e
                print(f"API Error: {e}. Trying next key if available.")
                continue

    print(f"All keys exhausted or failed. Last error: {last_exception}")
    return None
