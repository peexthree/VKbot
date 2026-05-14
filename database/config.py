import os

URL = os.environ.get("SUPABASE_URL", "")
KEY = os.environ.get("SUPABASE_KEY", "")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}
TABLE_NAME = "vk_esoteric_users"
FSM_TABLE = "user_fsm"
