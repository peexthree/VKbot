import os

URL = os.environ.get("SUPABASE_URL", "")
# service_role ключ обходит RLS-политики и должен использоваться ботом в проде.
# anon-ключ оставлен как fallback для локальной разработки (см. database/security_fixes.sql, Phase B)
KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}
TABLE_NAME = "vk_esoteric_users"
