import asyncio
import os
import aiohttp
import json

async def main():
    token = os.environ.get("VK_TOKEN")
    files = ["sex.jpeg", "money.jpeg", "demon.jpeg", "way.jpeg", "full.jpeg", "ora.jpeg"]
    for i in range(78):
        files.append(f"{i}.jpeg")

    tarot_mapping = {}

    # 1. Получить upload_url
    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://api.vk.com/method/photos.getMessagesUploadServer", data={"access_token": token, "v": "5.131"}) as resp:
            data = await resp.json()
            if 'response' not in data:
                print("Error getting upload server", data)
                return
            upload_url = data['response']['upload_url']

        for f in files:
            path = f"cards/{f}"
            if not os.path.exists(path):
                print(f"{f} not found!")
                continue

            content_type = 'image/jpeg'

            # 2. Загрузить файл
            with open(path, 'rb') as file:
                data = aiohttp.FormData()
                data.add_field('photo', file, filename=f, content_type=content_type)
                async with session.post(upload_url, data=data) as resp:
                    upload_res = await resp.json()

            # 3. Сохранить фото
            save_data = {
                "access_token": token,
                "v": "5.131",
                "photo": upload_res['photo'],
                "server": upload_res['server'],
                "hash": upload_res['hash']
            }
            async with session.post(f"https://api.vk.com/method/photos.saveMessagesPhoto", data=save_data) as resp:
                save_res = await resp.json()
                if 'response' in save_res:
                    photo = save_res['response'][0]
                    photo_id = f"photo{photo['owner_id']}_{photo['id']}"

                    if f[0].isdigit(): # It's a tarot card
                        card_num = f.split('.')[0]
                        tarot_mapping[card_num] = photo_id
                    else:
                        print(f"'{f}': '{photo_id}',")
                else:
                    print(f"Error saving {f}", save_res)

        with open('tarot_ids.json', 'w') as f_out:
            json.dump(tarot_mapping, f_out, indent=4)

asyncio.run(main())
