from fastapi import FastAPI, Query, Response
import openai
import requests
import matplotlib.pyplot as plt
import io
import base64

app = FastAPI()


def get_location_by_ip():
    response = requests.get("http://ip-api.com/json/")
    data = response.json()
    return data["lat"], data["lon"]


def find_places_osm(lat: float, lon: float, radius: int, amenity: str):
    url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    node(around:{radius},{lat},{lon})[amenity={amenity}];
    out body;
    """
    response = requests.get(url, params={"data": query})
    data = response.json()
    
    places = []
    for element in data.get("elements", []):
        places.append({
            "name": element.get("tags", {}).get("name", "Unknown"),
            "lat": element["lat"],
            "lon": element["lon"]
        })
    
    return places

@app.get("/nearby")
def get_nearby_places(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius: int = Query(1000, description="Radius in meters"),
    place_type: str = Query("restaurant", description="Type of place")
):
    places = find_places_osm(lat, lon, radius, place_type)
    return {"places": places}


with open("api_key.txt", "r") as f:
    api_key = f.read().strip()

openai.api_key = api_key

def get_weather_data(city: str, api_key: str):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric"
    r = requests.get(url)
    data = r.json()
    temps = [item["main"]["temp"] for item in data["list"][:8]]
    times = [item["dt_txt"] for item in data["list"][:8]]
    return times, temps


@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

@app.get("/answer")
def get_answer(question: str = Query(..., description="Your question")):
    response = openai.chat.completions.create(
    model="gpt-4-1106-preview",
    messages=[
        {"role": "system", "content": "You are an AI assistant that helps with questions about daily routines and everyday life. Do not answer questions outside this topic; politely refuse to respond to unrelated questions."},
        {"role": "user", "content": question}
    ]
)
    answer = response.choices[0].message.content
    return {"answer": answer}

