import os
from vkbottle import Bot

vk_token = os.environ.get("VK_TOKEN", "")
bot = Bot(token=vk_token)
bot.state_dispenser.strict = False
