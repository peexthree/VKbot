import re

with open('ai_service.py', 'r') as f:
    content = f.read()

# Add asyncio if not present (it's not imported at top level currently)
if 'import asyncio' not in content:
    content = 'import asyncio\n' + content

# 1. Add retry logic to generate_text
text_retry_regex = r'(async with session\.post.*?as resp:.*?)elif resp\.status == 429:\s*print\(f"Rate limit hit for text generation.*?\)\s*continue'

new_text_retry = r"""\1elif resp.status == 429:
                            print(f"Rate limit hit for text generation ({model}). Retrying with backoff...")
                            await asyncio.sleep(2)  # Simple static backoff to avoid blocking too long, but let's do a short loop
                            # Actually, a better approach is to retry the request directly here a few times
                            retry_count = 0
                            success = False
                            while retry_count < 3 and not success:
                                retry_count += 1
                                await asyncio.sleep(2 ** retry_count)
                                async with session.post(url, json=payload) as retry_resp:
                                    if retry_resp.status == 200:
                                        res_data = await retry_resp.json()
                                        try:
                                            text = res_data['candidates'][0]['content']['parts'][0]['text']
                                            if not json_mode:
                                                text = text.replace('*', '').replace('#', '').replace('_', '')
                                            return text
                                        except (KeyError, IndexError):
                                            pass
                                    elif retry_resp.status != 429:
                                        break
                            continue"""

content = re.sub(text_retry_regex, new_text_retry, content, flags=re.DOTALL)


# 2. Add retry logic to generate_image
image_retry_regex = r'(async with session\.post.*?as resp:.*?)elif resp\.status == 429:\s*print\(f"Rate limit hit for image generation\. Rotating\.\.\."\)\s*continue'

new_image_retry = r"""\1elif resp.status == 429:
                        print(f"Rate limit hit for image generation. Retrying with backoff...")
                        retry_count = 0
                        success = False
                        while retry_count < 3 and not success:
                            retry_count += 1
                            await asyncio.sleep(2 ** retry_count)
                            async with session.post(url, json=payload) as retry_resp:
                                if retry_resp.status == 200:
                                    res_data = await retry_resp.json()
                                    try:
                                        output_b64 = res_data['predictions'][0]['bytesBase64Encoded']
                                        return base64.b64decode(output_b64)
                                    except (KeyError, IndexError):
                                        pass
                                elif retry_resp.status != 429:
                                    break
                        continue"""

content = re.sub(image_retry_regex, new_image_retry, content, flags=re.DOTALL)

with open('ai_service.py', 'w') as f:
    f.write(content)
