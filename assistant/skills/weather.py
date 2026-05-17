"""
Weather Skill for Shweta AI Desktop Assistant.
Uses Open-Meteo free API (no API key required).
"""

import logging
from typing import Dict

import requests

from config import DEFAULT_CITY

logger = logging.getLogger(__name__)

# WMO Weather interpretation codes mapped to Hindi descriptions
WMO_CODES: Dict[int, str] = {
    0: "saaf aasmaan",
    1: "zyaadatar saaf",
    2: "aadha badal",
    3: "badal chhaye hue",
    45: "kohra",
    48: "jami hui kohra",
    51: "halki boondi",
    53: "boondi",
    55: "tez boondi",
    56: "jami hui halki boondi",
    57: "jami hui tez boondi",
    61: "halki baarish",
    63: "baarish",
    65: "tez baarish",
    66: "jami hui halki baarish",
    67: "jami hui tez baarish",
    71: "halki barfbaari",
    73: "barfbaari",
    75: "tez barfbaari",
    77: "baraf ke daane",
    80: "halki bauchhaar",
    81: "bauchhaar",
    82: "tez bauchhaar",
    85: "halki baraf ki bauchhaar",
    86: "tez baraf ki bauchhaar",
    95: "toofaan",
    96: "toofaan aur ole",
    99: "tez toofaan aur bade ole",
}

# City coordinates for geocoding (common Indian cities)
CITY_COORDS: Dict[str, Dict[str, float]] = {
    "pune": {"lat": 18.5204, "lon": 73.8567},
    "mumbai": {"lat": 19.0760, "lon": 72.8777},
    "delhi": {"lat": 28.6139, "lon": 77.2090},
    "bangalore": {"lat": 12.9716, "lon": 77.5946},
    "bengaluru": {"lat": 12.9716, "lon": 77.5946},
    "hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "chennai": {"lat": 13.0827, "lon": 80.2707},
    "kolkata": {"lat": 22.5726, "lon": 88.3639},
    "jaipur": {"lat": 26.9124, "lon": 75.7873},
    "ahmedabad": {"lat": 23.0225, "lon": 72.5714},
    "lucknow": {"lat": 26.8467, "lon": 80.9462},
    "nagpur": {"lat": 21.1458, "lon": 79.0882},
    "indore": {"lat": 22.7196, "lon": 75.8577},
    "bhopal": {"lat": 23.2599, "lon": 77.4126},
    "patna": {"lat": 25.6093, "lon": 85.1376},
}


def _get_coordinates(city: str) -> Dict[str, float]:
    """
    Get latitude and longitude for a city.
    Uses local lookup first, then Open-Meteo geocoding API.

    Args:
        city: City name.

    Returns:
        Dictionary with 'lat' and 'lon' keys.
    """
    city_lower = city.lower().strip()

    # Check local cache first
    if city_lower in CITY_COORDS:
        return CITY_COORDS[city_lower]

    # Use Open-Meteo geocoding API
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        response = requests.get(url, timeout=10)
        data = response.json()

        if "results" in data and len(data["results"]) > 0:
            result = data["results"][0]
            return {"lat": result["latitude"], "lon": result["longitude"]}
    except Exception as e:
        logger.error(f"Geocoding failed for {city}: {e}")

    # Default to Pune if all else fails
    return CITY_COORDS["pune"]


def get_weather(city: str = "") -> Dict[str, str]:
    """
    Get current weather for a city using Open-Meteo API.

    Args:
        city: City name (defaults to DEFAULT_CITY from config).

    Returns:
        Result dictionary with weather information.
    """
    if not city:
        city = DEFAULT_CITY

    try:
        coords = _get_coordinates(city)
        lat = coords["lat"]
        lon = coords["lon"]

        # Open-Meteo current weather API
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            f"&timezone=Asia/Kolkata"
        )

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data.get("current", {})
        temp = current.get("temperature_2m", "N/A")
        humidity = current.get("relative_humidity_2m", "N/A")
        weather_code = current.get("weather_code", 0)
        wind_speed = current.get("wind_speed_10m", "N/A")

        # Get Hindi weather description
        condition = WMO_CODES.get(weather_code, "pata nahi")

        message = (
            f"{city.title()} mein abhi {temp}°C hai, "
            f"mausam {condition} hai, "
            f"humidity {humidity}% aur hawa {wind_speed} km/h chal rahi hai."
        )

        logger.info(f"Weather fetched for {city}: {temp}°C, {condition}")

        return {
            "status": "success",
            "message": message,
            "temperature": f"{temp}°C",
            "condition": condition,
            "humidity": f"{humidity}%",
            "wind_speed": f"{wind_speed} km/h",
            "city": city.title()
        }

    except requests.ConnectionError:
        logger.error("No internet connection for weather.")
        return {"status": "error", "message": "Internet connection nahi hai."}
    except requests.Timeout:
        logger.error("Weather API timeout.")
        return {"status": "error", "message": "Weather service slow hai, baad mein try karein."}
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return {"status": "error", "message": f"Weather nahi mil paya: {str(e)}"}
