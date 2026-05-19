import asyncio
import pytest
from modules.utils.geo import get_geo_data, local_to_utc
from modules.utils.astro import calculate_natal_data
from modules.utils.viz import generate_natal_wheel
from unittest.mock import AsyncMock, MagicMock
import os

@pytest.mark.asyncio
async def test_astro_flow():
    # Mock Redis to avoid connection errors in test environment
    import modules.utils.geo
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    modules.utils.geo.redis_client = mock_redis

    city = "Moscow"
    print(f"Testing geocoding for {city}...")
    # Nominatim should work without Redis if mocked properly
    geo = await get_geo_data(city)
    if not geo:
        pytest.fail("Geocoding failed")
    print(f"Geo data: {geo}")

    birth_date = "15.05.1990"
    birth_time = "14:30"
    print(f"Testing UTC conversion for {birth_date} {birth_time} in {geo['timezone']}...")
    utc_dt = local_to_utc(birth_date, birth_time, geo['timezone'])
    print(f"UTC datetime: {utc_dt}")

    print("Testing Swiss Ephemeris calculations...")
    astro_data = calculate_natal_data(utc_dt, geo['lat'], geo['lon'])
    if not astro_data:
        pytest.fail("Astro calculations failed")

    print("Planets found:", list(astro_data['planets'].keys()))
    print("Sun position:", astro_data['planets']['Sun'])
    print("Aspects count:", len(astro_data['aspects']))

    print("Testing natal wheel generation...")
    output_path = "test_natal_wheel.png"
    success = generate_natal_wheel(astro_data, output_path)
    if success and os.path.exists(output_path):
        print(f"Natal wheel generated at {output_path}")
        if os.path.exists(output_path):
            os.remove(output_path)
    else:
        pytest.fail("Natal wheel generation failed")

if __name__ == "__main__":
    asyncio.run(test_astro_flow())
