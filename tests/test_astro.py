import asyncio
from modules.utils.geo import get_geo_data, local_to_utc
from modules.utils.astro import calculate_natal_data
from modules.utils.viz import generate_natal_wheel
from unittest.mock import MagicMock
import os
import sys

# Mock Redis to avoid connection errors in test environment
import modules.utils.geo
modules.utils.geo.redis_client = MagicMock()
modules.utils.geo.redis_client.get = MagicMock(return_value=asyncio.Future())
modules.utils.geo.redis_client.get.return_value.set_result(None)
modules.utils.geo.redis_client.set = MagicMock(return_value=asyncio.Future())
modules.utils.geo.redis_client.set.return_value.set_result(True)

async def test_astro_flow():
    city = "Moscow"
    print(f"Testing geocoding for {city}...")
    # Nominatim should work without Redis if mocked properly
    geo = await get_geo_data(city)
    if not geo:
        print("Geocoding failed")
        return
    print(f"Geo data: {geo}")

    birth_date = "15.05.1990"
    birth_time = "14:30"
    print(f"Testing UTC conversion for {birth_date} {birth_time} in {geo['timezone']}...")
    utc_dt = local_to_utc(birth_date, birth_time, geo['timezone'])
    print(f"UTC datetime: {utc_dt}")

    print("Testing Swiss Ephemeris calculations...")
    astro_data = calculate_natal_data(utc_dt, geo['lat'], geo['lon'])
    if not astro_data:
        print("Astro calculations failed")
        return

    print("Planets found:", list(astro_data['planets'].keys()))
    print("Sun position:", astro_data['planets']['Sun'])
    print("Aspects count:", len(astro_data['aspects']))

    print("Testing natal wheel generation...")
    output_path = "test_natal_wheel.png"
    success = generate_natal_wheel(astro_data, output_path)
    if success and os.path.exists(output_path):
        print(f"Natal wheel generated at {output_path}")
    else:
        print("Natal wheel generation failed")

if __name__ == "__main__":
    asyncio.run(test_astro_flow())
