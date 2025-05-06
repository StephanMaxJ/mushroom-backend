from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from typing import Optional

app = FastAPI()

# Enable CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Suburbs and their respective latitudes and longitudes
SUBURBS = {
    "newlands": {"lat": -33.9644, "lon": 18.4567},
    "stellenbosch": {"lat": -33.9333, "lon": 18.8496},
    "houtbay": {"lat": -34.0309, "lon": 18.3700},
    "tokai": {"lat": -34.0491, "lon": 18.4242},
    "constantia": {"lat": -34.0256, "lon": 18.4252}
}

# Mushroom foraging profiles
MUSHROOM_PROFILES = {
    "porcini": {
        "temp_range": (12, 28),
        "humidity_min": 70,
        "rain_min": 5,
        "rain_max": 40,
        "wind_max": 10
    },
    "pine_rings": {
        "temp_range": (10, 22),
        "humidity_min": 65,
        "rain_min": 5,
        "rain_max": 20,
        "wind_max": 10
    },
    "poplar_boletes": {
        "temp_range": (12, 23),
        "humidity_min": 60,
        "rain_min": 3,
        "rain_max": 35,
        "wind_max": 10
    },
    "agaricus": {
        "temp_range": (14, 26),
        "humidity_min": 65,
        "rain_min": 0,
        "rain_max": 25,
        "wind_max": 8
    },
    "white_parasols": {
        "temp_range": (18, 28),
        "humidity_min": 60,
        "rain_min": 0,
        "rain_max": 30,
        "wind_max": 6
    },
    "wood_blewits": {
        "temp_range": (4, 8),
        "humidity_min": 80,
        "rain_min": 5020,
        "rain_max": 50,
        "wind_max": 5
    },
    "morels": {
        "temp_range": (12, 21),
        "humidity_min": 70,
        "rain_min": 10,
        "rain_max": 50,
        "wind_max": 4
    }
}

@app.get("/check")
def check_weather(suburb: str = "newlands"):
    if suburb not in SUBURBS:
        raise HTTPException(status_code=400, detail="Invalid suburb provided.")

    lat = SUBURBS[suburb]["lat"]
    lon = SUBURBS[suburb]["lon"]

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,precipitation_probability,relative_humidity_2m,wind_speed_10m"
        f"&timezone=auto"
    )

    try:
        print(f"Making API request to: {url}")
        response = requests.get(url)

        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch weather data from Open-Meteo. Status Code: {response.status_code}"
            )

        data = response.json()
        print("Received data:", data)

        hourly = data.get("hourly", {})
        temp = hourly.get("temperature_2m", [])
        humidity = hourly.get("relative_humidity_2m", [])
        rain = hourly.get("precipitation_probability", [])
        wind = hourly.get("wind_speed_10m", [])

        if not temp or not humidity or not rain or not wind:
            raise HTTPException(status_code=500, detail="Incomplete weather data received.")

        avg_temp = sum(temp) / len(temp)
        avg_humidity = sum(humidity) / len(humidity)
        avg_rain = sum(rain) / len(rain)
        avg_wind = sum(wind) / len(wind)

        # Evaluating if it's a good day for foraging
        good_day = (
            10 <= avg_temp <= 25 and
            avg_rain < 40 and
            avg_humidity >= 60 and
            avg_wind <= 10
        )

        # Check mushroom profiles based on weather
        mushroom_recommendations = []

        for name, profile in MUSHROOM_PROFILES.items():
            t_min, t_max = profile["temp_range"]
            if (
                t_min <= avg_temp <= t_max and
                profile["humidity_min"] <= avg_humidity and
                profile["rain_min"] <= avg_rain <= profile["rain_max"] and
                avg_wind <= profile["wind_max"]
            ):
                mushroom_recommendations.append(name)

        return {
            "suburb": suburb,
            "good_day": good_day,
            "avg_temperature": round(avg_temp, 1),
            "avg_precipitation_probability": round(avg_rain, 1),
            "avg_humidity": round(avg_humidity, 1),
            "avg_wind_speed": round(avg_wind, 1),
            "recommended_mushrooms": mushroom_recommendations
        }

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        raise HTTPException(status_code=500, detail="Error during the weather request.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
