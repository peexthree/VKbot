import asyncio
from loguru import logger
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import pytz
from datetime import datetime
from cache import redis_client

geolocator = Nominatim(user_agent="anti_tar_bot")
tf = TimezoneFinder()

async def get_geo_data(city_name: str) -> dict | None:
    """
    Получает координаты и часовой пояс города.
    Использует кэш Redis.
    """
    cache_key = f"geo_data:{city_name.lower().strip()}"

    # Пытаемся взять из кэша
    cached = await redis_client.get(cache_key)
    if cached:
        try:
            import json
            return json.loads(cached)
        except Exception:
            pass

    try:
        # Nominatim синхронный, но мы можем обернуть его в run_in_executor если нужно.
        # Для простоты пока так, учитывая низкую частоту запросов при онбординге.
        loop = asyncio.get_event_loop()
        location = await loop.run_in_executor(None, lambda: geolocator.geocode(city_name, language="en"))

        if not location:
            logger.warning(f"Город не найден: {city_name}")
            return None

        lat, lon = location.latitude, location.longitude
        timezone_str = tf.timezone_at(lng=lon, lat=lat)

        res = {
            "lat": lat,
            "lon": lon,
            "timezone": timezone_str,
            "display_name": location.address
        }

        # Кэшируем надолго (город не убежит)
        import json
        await redis_client.set(cache_key, json.dumps(res), ex=86400 * 30)
        return res

    except Exception as e:
        logger.error(f"Ошибка геокодирования {city_name}: {e}")
        return None

def local_to_utc(date_str: str, time_str: str, timezone_str: str) -> datetime | None:
    """
    Конвертирует локальное время в UTC datetime.
    date_str: DD.MM.YYYY
    time_str: HH:MM
    """
    try:
        local_tz = pytz.timezone(timezone_str)
        local_dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        local_dt = local_tz.localize(local_dt)
        return local_dt.astimezone(pytz.UTC)
    except Exception as e:
        logger.error(f"Ошибка конвертации времени: {e}")
        return None
