import swisseph as swe
from datetime import datetime
from loguru import logger

# Планеты для расчета
PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Uranus": swe.URANUS,
    "Neptune": swe.NEPTUNE,
    "Pluto": swe.PLUTO,
    "Mean Node": swe.MEAN_NODE,
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

SIGNS_RU = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"
]

ASPECT_TYPES = [
    {"name": "Conjunction", "angle": 0, "orb": 8},
    {"name": "Opposition", "angle": 180, "orb": 8},
    {"name": "Trine", "angle": 120, "orb": 8},
    {"name": "Square", "angle": 90, "orb": 8},
    {"name": "Sextile", "angle": 60, "orb": 6},
]

def get_sign(lon, ru=False):
    return SIGNS_RU[int(lon / 30)] if ru else SIGNS[int(lon / 30)]

def get_degree(lon):
    return lon % 30

def calculate_natal_data(utc_dt: datetime, lat: float, lon: float):
    """
    Рассчитывает натальную карту пользователя.
    """
    try:
        # Установка времени для Swiss Ephemeris (Julian Day)
        jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0)

        results = {
            "planets": {},
            "houses": {},
            "aspects": [],
            "angles": {}
        }

        # Расчет планет
        for name, id_ in PLANETS.items():
            # Используем Moshier ephemeris если файлы не найдены
            res, ret = swe.calc_ut(jd, id_, swe.FLG_MOSEPH)
            lon_p = res[0]
            speed = res[3]

            results["planets"][name] = {
                "lon": lon_p,
                "sign": get_sign(lon_p),
                "sign_ru": get_sign(lon_p, ru=True),
                "degree": get_degree(lon_p),
                "retrograde": speed < 0
            }

        # Расчет домов (Placidus)
        # cusps[0] is unused, cusps[1..12] are the house cusps
        cusps, ascmc = swe.houses(jd, lat, lon, b'P')

        results["angles"] = {
            "Asc": {"lon": ascmc[0], "sign": get_sign(ascmc[0]), "sign_ru": get_sign(ascmc[0], ru=True), "degree": get_degree(ascmc[0])},
            "MC": {"lon": ascmc[1], "sign": get_sign(ascmc[1]), "sign_ru": get_sign(ascmc[1], ru=True), "degree": get_degree(ascmc[1])},
            "Dsc": {"lon": (ascmc[0] + 180) % 360, "sign": get_sign((ascmc[0] + 180) % 360), "sign_ru": get_sign((ascmc[0] + 180) % 360, ru=True)},
            "IC": {"lon": (ascmc[1] + 180) % 360, "sign": get_sign((ascmc[1] + 180) % 360), "sign_ru": get_sign((ascmc[1] + 180) % 360, ru=True)}
        }

        # Fix: cusps are 0-indexed and have 12 elements (House 1 at index 0)
        for i in range(1, 13):
            results["houses"][i] = {
                "lon": cusps[i-1],
                "sign": get_sign(cusps[i-1]),
                "sign_ru": get_sign(cusps[i-1], ru=True),
                "degree": get_degree(cusps[i-1])
            }

        # Определение дома для каждой планеты
        for p_name, p_data in results["planets"].items():
            p_lon = p_data["lon"]
            house_num = 0
            for i in range(1, 13):
                h_start = cusps[i-1]
                h_end = cusps[i] if i < 12 else cusps[0]

                # Обработка перехода через 0/360 градусов
                if h_start < h_end:
                    if h_start <= p_lon < h_end:
                        house_num = i
                        break
                else:
                    if p_lon >= h_start or p_lon < h_end:
                        house_num = i
                        break
            p_data["house"] = house_num

        # Расчет аспектов
        results["aspects"] = _calculate_aspects(results["planets"])

        return results

    except Exception as e:
        logger.error(f"Astro calculation error: {e}")
        return None

def _calculate_aspects(planets_data):
    aspects = []
    planet_names = list(planets_data.keys())
    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            p1 = planet_names[i]
            p2 = planet_names[j]
            lon1 = planets_data[p1]["lon"]
            lon2 = planets_data[p2]["lon"]

            diff = abs(lon1 - lon2)
            if diff > 180:
                diff = 360 - diff

            for aspect in ASPECT_TYPES:
                orb = abs(diff - aspect["angle"])
                if orb <= aspect["orb"]:
                    aspects.append({
                        "p1": p1,
                        "p2": p2,
                        "type": aspect["name"],
                        "orb": round(orb, 2),
                        "exact": orb < 1.0
                    })
    return aspects

def calculate_transits(natal_data, current_dt: datetime):
    """
    Рассчитывает аспекты текущих транзитных планет к натальным планетам.
    """
    try:
        jd_now = swe.julday(current_dt.year, current_dt.month, current_dt.day, current_dt.hour + current_dt.minute / 60.0)

        transit_planets = {}
        for name, id_ in PLANETS.items():
            res, ret = swe.calc_ut(jd_now, id_, swe.FLG_MOSEPH)
            transit_planets[name] = {
                "lon": res[0],
                "sign": get_sign(res[0]),
                "degree": get_degree(res[0]),
                "retrograde": res[3] < 0
            }

        transit_aspects = []
        for tp_name, tp_data in transit_planets.items():
            for np_name, np_data in natal_data["planets"].items():
                lon1 = tp_data["lon"]
                lon2 = np_data["lon"]

                diff = abs(lon1 - lon2)
                if diff > 180:
                    diff = 360 - diff

                for aspect in ASPECT_TYPES:
                    orb = abs(diff - aspect["angle"])
                    if orb <= aspect["orb"]: # Для транзитов можно брать меньший орбис, но оставим стандарт
                        transit_aspects.append({
                            "transit_planet": tp_name,
                            "natal_planet": np_name,
                            "type": aspect["name"],
                            "orb": round(orb, 2)
                        })
        return {
            "transit_planets": transit_planets,
            "transit_aspects": transit_aspects
        }
    except Exception as e:
        logger.error(f"Transit calculation error: {e}")
        return None

def calculate_synastry(data1, data2):
    """
    Рассчитывает аспекты совместимости между двумя картами.
    """
    aspects = []
    p_names1 = data1["planets"].keys()
    p_names2 = data2["planets"].keys()

    for p1 in p_names1:
        for p2 in p_names2:
            lon1 = data1["planets"][p1]["lon"]
            lon2 = data2["planets"][p2]["lon"]

            diff = abs(lon1 - lon2)
            if diff > 180:
                diff = 360 - diff

            for aspect in ASPECT_TYPES:
                orb = abs(diff - aspect["angle"])
                if orb <= aspect["orb"]:
                    aspects.append({
                        "p1": p1,
                        "p2": p2,
                        "type": aspect["name"],
                        "orb": round(orb, 2),
                        "exact": orb < 1.0
                    })
    return aspects
