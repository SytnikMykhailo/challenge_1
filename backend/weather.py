import os
from datetime import datetime, timedelta
import requests
from dateparser.search import search_dates
from openai import OpenAI
from dotenv import load_dotenv
import re

load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Geocode place using OpenStreetMap ---
def geocode(place: str):

    print(place)
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={place}&limit=1"
    resp = requests.get(url, headers={"User-Agent": "weather-assistant/1.0"})
    data = resp.json()
    print(float(data[0]["lat"]))
    print(float(data[0]["lon"]))
    if not data:
        raise ValueError(f"Location not found: {place}")
    return {
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"]),
        "display_name": data[0]["display_name"]
    }

# --- Fetch hourly weather from Open-Meteo ---
def fetch_weather(lat: float, lon: float):
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relativehumidity_2m,precipitation,weathercode,windspeed_10m,cloudcover"
        f"&timezone=auto"
    )
    resp = requests.get(url)
    data = resp.json()
    return data["hourly"]

# --- Round time to nearest 10 minutes ---
def round_to_nearest_10(hour: int, minute: int):
    rounded_min = round(minute / 10) * 10
    h, m = hour, rounded_min
    if rounded_min == 60:
        h = (hour + 1) % 24
        m = 0
    return h, m

# --- Get closest time entry in hourly data ---
def get_closest_hourly_data(hourly: dict, target_time: datetime):
    closest_index = None
    min_diff = float("inf")
    for i, t_str in enumerate(hourly["time"]):
        t = datetime.fromisoformat(t_str)
        diff = abs((t - target_time).total_seconds())
        if diff < min_diff:
            min_diff = diff
            closest_index = i

    if closest_index is None:
        return None

    return {
        "time": hourly["time"][closest_index],
        "temperature": hourly["temperature_2m"][closest_index],
        "humidity": hourly["relativehumidity_2m"][closest_index],
        "precipitation": hourly["precipitation"][closest_index],
        "wind": hourly["windspeed_10m"][closest_index],
        "cloudcover": hourly["cloudcover"][closest_index],
        "weathercode": hourly["weathercode"][closest_index]
    }

# --- Generate human-readable forecast via GPT ---
def generate_ai_response(user_query: str, weather_data: dict):
    prompt = f"""
You are a friendly weather assistant.
User query: "{user_query}"
Weather data: {weather_data}

Provide a short, human-readable weather summary including temperature, humidity, precipitation, wind, cloud cover, and a natural description (sunny, rainy, snowy, overcast, etc.).
"""
    response = openai_client.responses.create(
        model="gpt-5-nano",
        input=prompt,
    )
    return response.output_text or "No response from AI"

# --- Parse query for date/time and location ---
def parse_query_datetime(user_query: str):
    # Extract date/time
    date_matches = search_dates(user_query, settings={'PREFER_DATES_FROM': 'future'})
    if date_matches:
        parsed_dt = date_matches[0][1]
        # Remove date parts from query
        location_query = user_query
        for text, _ in date_matches:
            location_query = location_query.replace(text, "")
    else:
        parsed_dt = datetime.now()
        location_query = user_query

    # Clean location string
    location_query = re.sub(r'\b(weather|in)\b', '', location_query, flags=re.IGNORECASE).strip()

    # If the string is too short, fallback
    if len(location_query) < 3:
        location_query = "Berlin"

    # Round minutes to nearest 10
    hour, minute = round_to_nearest_10(parsed_dt.hour, parsed_dt.minute)
    parsed_dt = parsed_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Shift to next day if in the past
    if parsed_dt < datetime.now():
        parsed_dt += timedelta(days=1)

    return parsed_dt, location_query

# --- Main assistant function ---
def weather_assistant(user_query: str):
    parsed_dt, location_query = parse_query_datetime(user_query)
    loc = geocode(location_query)
    hourly = fetch_weather(loc["lat"], loc["lon"])
    closest_data = get_closest_hourly_data(hourly, parsed_dt)
    ai_answer = generate_ai_response(user_query, closest_data)
    print(f"Location: {loc['display_name']}")
    print(f"Time: {parsed_dt.isoformat()}")
    print(ai_answer)


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "Weather in Berlin tomorrow at noon"
    weather_assistant(query)
