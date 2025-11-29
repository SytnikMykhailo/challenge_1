from fastapi import FastAPI, Query, Response
import openai
import requests
import matplotlib.pyplot as plt
import io
import base64
import json


app = FastAPI()

with open("api_key.txt", "r") as f:
    api_key = f.read().strip()

openai.api_key = api_key

tags_for_places = []
settings = {}


print('abobba')

@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

@app.get("/request")
def process_request(request: str = Query(..., description="Your request")):
    """
    Обробляє запит користувача, визначає тип активності/місця та преференції.
    Повертає структуровані дані у форматі JSON.
    """
    global tags_for_places, settings
    
    # Використовуйте gpt-3.5-turbo замість gpt-4 (швидше і дешевше)
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",  # Змінено з gpt-4-1106-preview
        messages=[
            {
                "role": "system", 
                "content": """You are an AI assistant that helps with tourism and activities.
Your task is to analyze the user's request and extract structured information in JSON format.

Output JSON structure:
{
  "activity_type": "string (e.g., dining, sightseeing, entertainment, sports, shopping)",
  "place_types": ["array of place types (e.g., restaurant, cafe, museum, park)"],
  "cuisine": "string or null (if restaurant/cafe)",
  "preferences": {
    "budget": "low/medium/high or null",
    "rating_min": number or null,
    "distance_max": number in meters or null,
    "wheelchair_accessible": boolean or null,
    "outdoor_seating": boolean or null,
    "dog_friendly": boolean or null,
    "delivery": boolean or null,
    "takeaway": boolean or null
  },
  "location": {
    "city": "string or null",
    "coordinates": {"lat": number, "lon": number} or null
  },
  "time_constraints": {
    "date": "string or null",
    "time": "string or null"
  },
  "additional_notes": "string or null"
}

Only return valid JSON, nothing else."""
            },
            {"role": "user", "content": request}
        ],
        temperature=0.3,  # Нижча температура = швидша відповідь
        max_tokens=500     # Обмеження токенів
    )
    
    # Отримати відповідь від GPT
    gpt_response = response.choices[0].message.content
    
    try:
        # Парсинг JSON відповіді
        parsed_data = json.loads(gpt_response)
        
        # Оновити глобальні змінні
        tags_for_places = parsed_data.get("place_types", [])
        settings = {
            "activity_type": parsed_data.get("activity_type"),
            "cuisine": parsed_data.get("cuisine"),
            "preferences": parsed_data.get("preferences", {}),
            "location": parsed_data.get("location", {}),
            "time_constraints": parsed_data.get("time_constraints", {}),
            "additional_notes": parsed_data.get("additional_notes")
        }
        
        # Повернути структуровані дані
        return {
            "status": "success",
            "original_request": request,
            "parsed_data": parsed_data,
            "tags_for_places": tags_for_places,
            "settings": settings,
            "next_step": "Use /search endpoint to find places based on these parameters"
        }
        
    except json.JSONDecodeError as e:
        # Якщо GPT не повернув валідний JSON
        return {
            "status": "error",
            "message": "Failed to parse GPT response",
            "raw_response": gpt_response,
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "An error occurred while processing the request",
            "error": str(e)
        }

@app.get("/answer")
def get_answer(question: str = Query(..., description="Your question")):
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",  # Змінено з gpt-4-1106-preview
        messages=[
            {"role": "system", "content": "You are an AI assistant that helps with questions about daily routines and everyday life. Do not answer questions outside this topic; politely refuse to respond to unrelated questions."},
            {"role": "user", "content": question}
        ],
        temperature=0.5,
        max_tokens=300
    )
    answer = response.choices[0].message.content
    return {"answer": answer}

