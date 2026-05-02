import re

with open('main.py', 'r') as f:
    content = f.read()

# 1. Fix the missing check in process_payment_and_generate
process_regex = r'    async def process_payment_and_generate\(vk_id: int\):\n        user = await get_user\(vk_id\)\n        if not user:\n            return\n\n        active_tasks\.add\(vk_id\)'
process_new = """    async def process_payment_and_generate(vk_id: int):
        if vk_id in active_tasks:
            return
        user = await get_user(vk_id)
        if not user:
            return

        active_tasks.add(vk_id)"""

content = re.sub(process_regex, process_new, content)

# 2. Make webhook at least a dummy POST or add a token/secret check
webhook_regex = r'    async def payment_webhook\(request\):\n        try:\n            # We simulate a webhook via GET for ease of clicking a link in VK \(which opens browser\)\n            # In real prod this would be POST from YooKassa\n            user_id_str = request\.query\.get\(\'user_id\'\)\n            if not user_id_str:\n                return web\.Response\(text="Missing user_id", status=400\)\n            user_id = int\(user_id_str\)'
webhook_new = """    async def payment_webhook(request):
        try:
            # We simulate a webhook via POST to simulate real YooKassa
            data = await request.post() if request.method == "POST" else request.query
            user_id_str = data.get('user_id')
            secret = data.get('secret')

            # Simple security check for our dummy webhook
            if secret != "dummy_secret_123":
                return web.Response(text="Unauthorized", status=401)

            if not user_id_str:
                return web.Response(text="Missing user_id", status=400)
            user_id = int(user_id_str)"""

content = re.sub(webhook_regex, webhook_new, content)


# 3. Update get_inline_buy_full_chart to include the secret
btn_regex = r'payment_url = f"\{host\}/payment/webhook\?user_id=\{user_id\}&amount=990"'
btn_new = 'payment_url = f"{host}/payment/webhook?user_id={user_id}&amount=990&secret=dummy_secret_123"'
content = re.sub(btn_regex, btn_new, content)

# Ensure app route allows POST
app_regex = r"app\.router\.add_get\('/payment/webhook', payment_webhook\)"
app_new = "app.router.add_route('*', '/payment/webhook', payment_webhook)"
content = re.sub(app_regex, app_new, content)


with open('main.py', 'w') as f:
    f.write(content)
