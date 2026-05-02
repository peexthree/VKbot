import re

with open('ai_service.py', 'r') as f:
    content = f.read()

fallback_logic = """    print(f"All keys exhausted or failed for image generation. Last error: {last_exception}")

    # Fallback placeholder image
    try:
        import os
        import random
        fallback_dir = 'assets/fallback_images'
        if os.path.exists(fallback_dir):
            images = [os.path.join(fallback_dir, f) for f in os.listdir(fallback_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
            if images:
                chosen = random.choice(images)
                with open(chosen, 'rb') as f:
                    return f.read()

        # Ultimate fallback
        from PIL import Image
        import io
        img = Image.new('RGB', (1024, 1024), color = '#2A2A2A')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        return img_byte_arr.getvalue()
    except Exception as e:
        print(f"Failed to generate fallback image: {e}")
        return None"""

content = re.sub(r'    print\(f"All keys exhausted or failed for image generation.*?return None', fallback_logic, content, flags=re.DOTALL)

with open('ai_service.py', 'w') as f:
    f.write(content)
