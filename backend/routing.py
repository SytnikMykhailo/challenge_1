import os
import re
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from dateparser.search import search_dates
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta

load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Geocoding

def geocode(place: str):
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={place}&limit=1"
    resp = requests.get(url, headers={"User-Agent": "transport-assistant/1.0"})
    data = resp.json()
    if not data:
        raise ValueError(f"Location not found: {place}")
    return {
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"]),
        "name": data[0]["display_name"]
    }


# Find nearest stops (very naive version)

def fetch_osm_stops(lat, lon):
    """Query OpenStreetMap Overpass for nearby public-transport stops."""
    query = f"""
    [out:json];
    (
      node(around:600,{lat},{lon})[public_transport=platform];
      node(around:600,{lat},{lon})[highway=bus_stop];
      node(around:600,{lat},{lon})[railway=station];
      node(around:600,{lat},{lon})[railway=tram_stop];
    );
    out;
    """

    resp = requests.post(
        "https://overpass-api.de/api/interpreter",
        data=query.encode("utf-8"),
        headers={"User-Agent": "transport-assistant/1.0"}
    )
    data = resp.json()

    stops = []
    for el in data.get("elements", []):
        name = el.get("tags", {}).get("name")
        if name:
            stops.append(name)
    return list(set(stops))


# Query CP.sk for route (HTML API)

def query_cp_route(origin_stop: str, dest_stop: str, when: datetime):
    date_str = when.strftime("%d.%m.%Y")
    time_str = when.strftime("%H:%M")

    url = (
        "https://cp.sk/vlakbus/spojenie/"
        f"?f={origin_stop}"
        f"&t={dest_stop}"
        f"&date={date_str}"
        f"&time={time_str}"
        "&submit=Vyhľadať"
    )

    resp = requests.get(url, headers={"User-Agent": "transport-assistant/1.0"})
    return resp.text


# Parse CP.sk HTML into structured legs

def parse_cp_html(html: str):
    soup = BeautifulSoup(html, "html.parser")

    results = []

    # CP.sk uses tables and divs for each connection.
    # This is a simplified version.
    connections = soup.select(".connection-row, .spojenie-row, .row")  # fallback selectors

    for conn in connections:
        text = conn.get_text(" ", strip=True)
        if not text:
            continue
        results.append(text)

    return results[:3]  # return 3 best candidates


# GPT Summary

def generate_ai_summary(user_query: str, origin: str, dest: str, time: datetime, routes: list):
    prompt = f"""
You are a transport assistant.
User asked: "{user_query}"

Origin stop: {origin}
Destination stop: {dest}
Time: {time}

Raw CP.sk route candidates:
{routes}

Write a short, human-readable route summary.
Include transfers, approximate travel time, and stop names.
"""

    response = openai_client.responses.create(
        model="gpt-5-nano",
        input=prompt,
    )
    return response.output_text or "No response."


# Parse user query (origin, destination, date/time)

def parse_query(user_query):
    # Extract datetime first
    date_matches = search_dates(user_query, settings={'PREFER_DATES_FROM': 'future'})
    if date_matches:
        dt = date_matches[0][1]
        for text, _ in date_matches:
            user_query = user_query.replace(text, "")
    else:
        dt = datetime.now() + timedelta(hours=1)  # fallback

    # Extract origin/destination using regex
    match = re.search(r'from\s+(.*?)\s+to\s+(.*)', user_query, re.IGNORECASE)
    if not match:
        raise ValueError("Could not detect origin and destination.")

    origin_text = match.group(1).strip()
    dest_text = match.group(2).strip()

    return origin_text, dest_text, dt


# Main assistant

def transport_assistant(user_query: str):

    origin_text, dest_text, when = parse_query(user_query)

    # Geocode
    origin_geo = geocode(origin_text)
    dest_geo = geocode(dest_text)

    # Find nearby stops
    origin_stops = fetch_osm_stops(origin_geo["lat"], origin_geo["lon"])
    dest_stops = fetch_osm_stops(dest_geo["lat"], dest_geo["lon"])

    if not origin_stops or not dest_stops:
        raise RuntimeError("Could not find public-transport stops near origin or destination.")

    # Choose best stop (naive: first match)
    origin_stop = origin_stops[0]
    dest_stop = dest_stops[0]

    # Query CP.sk
    html = query_cp_route(origin_stop, dest_stop, when)

    # Parse routes
    parsed_routes = parse_cp_html(html)

    # AI summary
    result = generate_ai_summary(user_query, origin_stop, dest_stop, when, parsed_routes)

    print("Origin:", origin_geo["name"])
    print("Destination:", dest_geo["name"])
    print("Stops:", origin_stop, "→", dest_stop)
    print("Time:", when.isoformat())
    print(result)



# CLI entrypoint

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "travel from Krajsky Sud to Stodolova tomorrow at 18"
    transport_assistant(query)
