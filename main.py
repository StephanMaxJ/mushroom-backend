from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import requests

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Suburb coordinates
SUBURBS = {
    "newlands": {"lat": -33.9644, "lon": 18.4567},
    "stellenbosch": {"lat": -33.9333, "lon": 18.8496},
    "stormsrivier": {"lat": -33.9674, "lon": 23.8898},
    "tsitsikamma": {"lat": -34.0133, "lon": 23.8892},
    "kzn_midlands": {"lat": -29.5667, "lon": 30.2167},
    "houtbay": {"lat": -34.0309, "lon": 18.3700},
    "tokai": {"lat": -34.0491, "lon": 18.4242},
    "constantia": {"lat": -34.0256, "lon": 18.4252},
    "franschhoek": {"lat": -33.9333, "lon": 18.8496},
    "noordhoek": {"lat": -34.1139, "lon": 18.3778},
    "swellendam": {"lat": -34.0207, "lon": 20.4418},
    "riversdale": {"lat": -34.0892, "lon": 21.2642},
    "knysna": {"lat": -34.0359, "lon": 23.0471},
    "tulbagh": {"lat": -33.2855, "lon": 19.1454},
    "ceres": {"lat": -33.3689, "lon": 19.3100}
}

# Mushroom profiles (no changes needed here)
MUSHROOM_PROFILES = {
    "porcini": {"temp_range": (12, 28), "humidity_min": 70, "rain_min": 5, "rain_max": 40, "wind_max": 10},
    "pine_rings": {"temp_range": (10, 22), "humidity_min": 65, "rain_min": 5, "rain_max": 20, "wind_max": 10},
    "poplar_boletes": {"temp_range": (12, 23), "humidity_min": 60, "rain_min": 3, "rain_max": 35, "wind_max": 10},
    "agaricus": {"temp_range": (14, 26), "humidity_min": 65, "rain_min": 0, "rain_max": 25, "wind_max": 8},
    "white_parasols": {"temp_range": (18, 28), "humidity_min": 60, "rain_min": 0, "rain_max": 30, "wind_max": 6},
    "wood_blewits": {"temp_range": (4, 8), "humidity_min": 80, "rain_min": 20, "rain_max": 50, "wind_max": 5},
    "morels": {"temp_range": (12, 21), "humidity_min": 70, "rain_min": 10, "rain_max": 50, "wind_max": 4},
    "blushers": {"temp_range": (14, 26), "humidity_min": 70, "rain_min": 5, "rain_max": 35, "wind_max": 8},
    "slippery_jills": {"temp_range": (12, 24), "humidity_min": 65, "rain_min": 5, "rain_max": 30, "wind_max": 9},
    "weeping_bolete": {"temp_range": (11, 23), "humidity_min": 60, "rain_min": 3, "rain_max": 25, "wind_max": 10},
    "bovine_bolete": {"temp_range": (10, 22), "humidity_min": 60, "rain_min": 4, "rain_max": 28, "wind_max": 9},
    "chicken_of_the_woods": {"temp_range": (15, 30), "humidity_min": 70, "rain_min": 10, "rain_max": 40, "wind_max": 6},
    "termitomyces": {"temp_range": (20, 32), "humidity_min": 80, "rain_min": 15, "rain_max": 50, "wind_max": 4}
    }

@app.get("/check")
def check_weather(
    suburb: Optional[str] = "newlands",  # Default to 'newlands' if no suburb provided
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None)
):
    # If suburb is passed, override default
    if suburb:
        if suburb not in SUBURBS:
            raise HTTPException(status_code=400, detail="Invalid suburb provided.")
        lat = SUBURBS[suburb]["lat"]
        lon = SUBURBS[suburb]["lon"]
    
    # Ensure lat and lon are provided if no suburb
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="Provide either a suburb or both lat and lon.")

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,precipitation_probability,relative_humidity_2m,wind_speed_10m"
        f"&timezone=auto"
    )

    try:
        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Weather API failed.")

        data = response.json()
        hourly = data.get("hourly", {})
        temp = hourly.get("temperature_2m", [])
        humidity = hourly.get("relative_humidity_2m", [])
        rain = hourly.get("precipitation_probability", [])
        wind = hourly.get("wind_speed_10m", [])

        if not all([temp, humidity, rain, wind]):
            raise HTTPException(status_code=500, detail="Incomplete weather data received.")

        avg_temp = sum(temp) / len(temp)
        avg_humidity = sum(humidity) / len(humidity)
        avg_rain = sum(rain) / len(rain)
        avg_wind = sum(wind) / len(wind)

        good_day = (
            10 <= avg_temp <= 25 and
            avg_rain < 40 and
            avg_humidity >= 60 and
            avg_wind <= 10
        )

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
            "location": suburb if suburb else {"lat": lat, "lon": lon},
            "good_day": good_day,
            "avg_temperature": round(avg_temp, 1),
            "avg_precipitation_probability": round(avg_rain, 1),
            "avg_humidity": round(avg_humidity, 1),
            "avg_wind_speed": round(avg_wind, 1),
            "recommended_mushrooms": mushroom_recommendations
        }

    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="Failed to fetch weather data.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
