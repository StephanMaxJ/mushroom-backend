from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mushroom profiles
MUSHROOM_PROFILES = {
    "porcini": {"temp_range": (12, 28), "humidity_min": 75, "rain_min": 0.1, "rain_max": 80, "wind_max": 15},
    "pine_rings": {"temp_range": (10, 22), "humidity_min": 65, "rain_min": 0.1, "rain_max": 80, "wind_max": 16},
    "poplar_boletes": {"temp_range": (10, 23), "humidity_min": 60, "rain_min": 0.1, "rain_max": 35, "wind_max": 15},
    "agaricus": {"temp_range": (14, 26), "humidity_min": 65, "rain_min": 3, "rain_max": 50, "wind_max": 11},
    "white_parasols": {"temp_range": (18, 28), "humidity_min": 60, "rain_min": 0, "rain_max": 30, "wind_max": 6},
    "wood_blewits": {"temp_range": (4, 8), "humidity_min": 80, "rain_min": 20, "rain_max": 50, "wind_max": 5},
    "morels": {"temp_range": (12, 21), "humidity_min": 70, "rain_min": 10, "rain_max": 50, "wind_max": 4},
    "blushers": {"temp_range": (8, 26), "humidity_min": 60, "rain_min": 0.1, "rain_max": 35, "wind_max": 16},
    "slippery_jills": {"temp_range": (12, 24), "humidity_min": 65, "rain_min": 0.5, "rain_max": 30, "wind_max": 9},
    "weeping_bolete": {"temp_range": (11, 23), "humidity_min": 60, "rain_min": 2, "rain_max": 25, "wind_max": 12},
    "bovine_bolete": {"temp_range": (10, 22), "humidity_min": 60, "rain_min": 2, "rain_max": 28, "wind_max": 12},
    "chicken_of_the_woods": {"temp_range": (23, 30), "humidity_min": 70, "rain_min": 10, "rain_max": 40, "wind_max": 10},
    "termitomyces": {"temp_range": (20, 32), "humidity_min": 80, "rain_min": 15, "rain_max": 50, "wind_max": 4}
}

# Helper function to determine the current season
def get_season():
    today = datetime.utcnow()
    month = today.month
    if 12 <= month <= 2:
        return "Summer 🌞"
    elif 3 <= month <= 5:
        return "Autumn 🍂"
    elif 6 <= month <= 8:
        return "Winter 🌧️"
    else:
        return "Spring 🌸"

# Helper function to calculate average
def average(values):
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else 0

@app.get("/check")
def check_conditions(lat: float = Query(...), lon: float = Query(...)):
    today = datetime.utcnow().date()
    seven_days_ago = today - timedelta(days=7)

    start_date = seven_days_ago.strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={end_date}"
        f"&hourly=temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m"
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
        rain = hourly.get("precipitation", [])
        wind = hourly.get("wind_speed_10m", [])

        if not all([temp, humidity, rain, wind]):
            raise HTTPException(status_code=500, detail="Incomplete weather data received.")

        avg_temp = average(temp)
        avg_humidity = average(humidity)
        avg_rain = average(rain)
        avg_wind = average(wind)

        # Foraging day quality rating
        if avg_temp >= 19 and avg_rain <= 40 and avg_humidity >= 90 and avg_wind <= 8:
            foraging_quality = "🍄‍🟫 Perfect day, there should be lots out"
        elif avg_temp >= 15 and avg_rain <= 20 and avg_humidity >= 70 and avg_wind <= 12:
            foraging_quality = "✅ Good day, go check your spots you may get lucky"
        elif avg_temp >= 12 and avg_rain <= 10 and avg_humidity >= 60 and avg_wind <= 15:
            foraging_quality = "❔ Average day, some mushrooms around but not much"
        else:
            foraging_quality = "❌ Not a good day, you could still check microclimates you know of"

        # Matching mushroom species
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
            "location": {"lat": lat, "lon": lon},
            "season": get_season(),
            "foraging_quality": foraging_quality,
            "avg_temperature": round(avg_temp, 1),
            "avg_precipitation": round(avg_rain, 1),
            "avg_humidity": round(avg_humidity, 1),
            "avg_wind_speed": round(avg_wind, 1),
            "recommended_mushrooms": mushroom_recommendations
        }

    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="Failed to fetch weather data.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
