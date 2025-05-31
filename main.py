from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mushroom profiles
MUSHROOM_PROFILES = {
    "porcini": {"temp_range": (12, 28), "humidity_min": 70, "rain_min": 0.1, "rain_max": 80, "wind_max": 15},
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

def get_season():
    month = datetime.utcnow().month
    if 12 <= month <= 2:
        return "Summer 🌞"
    elif 3 <= month <= 5:
        return "Autumn 🍂"
    elif 6 <= month <= 8:
        return "Winter 🌧️"
    else:
        return "Spring 🌸"

def average(values):
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else 0

@app.get("/check")
def check_conditions(lat: float = Query(...), lon: float = Query(...)):
    weatherapi_key = "b5c1991aa27149c881e173752250505"  # <== Replace with your real key
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=6)

    # --- Open-Meteo historical data ---
    open_meteo_url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={today}"
        f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=auto"
    )
    meteo_response = requests.get(open_meteo_url)
    if meteo_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Open-Meteo data error")
    meteo_data = meteo_response.json().get("hourly", {})

    avg_temp = average(meteo_data.get("temperature_2m", []))
    avg_humidity = average(meteo_data.get("relative_humidity_2m", []))
    avg_wind = average(meteo_data.get("wind_speed_10m", []))

    # --- WeatherAPI rainfall (daily loop) ---
    rain_values = []
    for i in range(7):
        date = today - timedelta(days=i)
        url = f"http://api.weatherapi.com/v1/history.json?key={weatherapi_key}&q={lat},{lon}&dt={date}"
        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"WeatherAPI error for {date}")
        day_data = response.json().get("forecast", {}).get("forecastday", [{}])[0].get("day", {})
        rain_values.append(day_data.get("totalprecip_mm", 0))

    avg_rain = average(rain_values)

    # --- Foraging conditions ---
    if avg_temp >= 19 and avg_rain <= 40 and avg_humidity >= 90 and avg_wind <= 8:
        quality = "🍄‍🟫 Perfect day, there should be lots out"
    elif avg_temp >= 15 and avg_rain <= 20 and avg_humidity >= 70 and avg_wind <= 12:
        quality = "✅ Good day, go check your spots you may get lucky"
    elif avg_temp >= 12 and avg_rain <= 10 and avg_humidity >= 60 and avg_wind <= 15:
        quality = "❔ Average day, some mushrooms around but not much"
    else:
        quality = "❌ Not a good day, you could still check microclimates you know of"

    # --- Mushroom recommendations ---
    recommended = []
    for name, profile in MUSHROOM_PROFILES.items():
        t_min, t_max = profile["temp_range"]
        if (
            t_min <= avg_temp <= t_max and
            profile["humidity_min"] <= avg_humidity and
            profile["rain_min"] <= avg_rain <= profile["rain_max"] and
            avg_wind <= profile["wind_max"]
        ):
            recommended.append(name)

    # --- Forecast box (WeatherAPI current) ---
    forecast_url = f"http://api.weatherapi.com/v1/current.json?key={weatherapi_key}&q={lat},{lon}"
    forecast_response = requests.get(forecast_url)
    current = forecast_response.json().get("current", {})

    return {
        "location": {"lat": lat, "lon": lon},
        "season": get_season(),
        "foraging_quality": quality,
        "avg_temperature": round(avg_temp, 1),
        "avg_precipitation": round(avg_rain, 1),
        "avg_humidity": round(avg_humidity, 1),
        "avg_wind_speed": round(avg_wind, 1),
        "forecast_temperature": current.get("temp_c"),
        "forecast_humidity": current.get("humidity"),
        "forecast_precipitation": current.get("precip_mm", 0),
        "forecast_wind_speed": current.get("wind_kph"),
        "recommended_mushrooms": recommended
    }
