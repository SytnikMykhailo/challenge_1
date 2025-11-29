from fastapi import FastAPI, Query, Response
import openai
import requests
import matplotlib.pyplot as plt
import io
import base64
import json
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse



app = FastAPI()

with open("api_key.txt", "r") as f:
    api_key = f.read().strip()

openai.api_key = api_key

tags_for_places = []
settings = {}

@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

@app.get("/scrape-website-images")
def scrape_website_images(
    website: str = Query(..., description="Website URL"),
    max_pages: int = Query(5, description="Maximum pages to scrape"),
    max_images: int = Query(20, description="Maximum images to collect")
):
    """
    Парсить зображення з веб-сайту (без SVG), включаючи внутрішні сторінки
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        visited_urls = set()
        images_found = set()
        urls_to_visit = [website]
        base_domain = urlparse(website).netloc
        
        def is_valid_url(url):
            """Перевіряє, чи URL належить до того ж домену"""
            parsed = urlparse(url)
            return parsed.netloc == base_domain and parsed.scheme in ['http', 'https']
        
        def extract_images_and_links(url):
            """Витягує зображення та посилання зі сторінки"""
            if url in visited_urls or len(visited_urls) >= max_pages:
                return [], []
            
            visited_urls.add(url)
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Знайти всі зображення
                page_images = []
                for img in soup.find_all('img'):
                    img_url = img.get('src') or img.get('data-src')
                    if img_url:
                        # Конвертувати відносні URL в абсолютні
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            img_url = urljoin(url, img_url)
                        elif not img_url.startswith('http'):
                            img_url = urljoin(url, img_url)
                        
                        # Фільтрувати SVG, логотипи та іконки
                        img_lower = img_url.lower()
                        if all([
                            '.svg' not in img_lower,
                            'logo' not in img_lower,
                            'icon' not in img_lower,
                            'sprite' not in img_lower,
                            'placeholder' not in img_lower,
                            'favicon' not in img_lower,
                            'banner' not in img_lower,
                            img_url.startswith('http')
                        ]):
                            page_images.append(img_url)
                
                # Знайти всі внутрішні посилання
                page_links = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    # Конвертувати відносні URL
                    if href.startswith('/'):
                        href = urljoin(url, href)
                    elif not href.startswith('http'):
                        href = urljoin(url, href)
                    
                    # Фільтрувати тільки внутрішні посилання
                    if is_valid_url(href) and href not in visited_urls:
                        # Ігнорувати посилання на файли та якорі
                        if not any(ext in href.lower() for ext in ['.pdf', '.doc', '.zip', '#']):
                            page_links.append(href)
                
                return page_images, page_links
            
            except Exception as e:
                print(f"❌ Помилка при обробці {url}: {e}")
                return [], []
        
        # Обхід сторінок
        while urls_to_visit and len(visited_urls) < max_pages and len(images_found) < max_images:
            current_url = urls_to_visit.pop(0)
            
            print(f"🔍 Сканування: {current_url}")
            page_images, page_links = extract_images_and_links(current_url)
            
            # Додати знайдені зображення
            for img in page_images:
                if len(images_found) < max_images:
                    images_found.add(img)
            
            # Додати нові посилання для обходу
            for link in page_links[:3]:  # Обмежити кількість посилань з кожної сторінки
                if link not in urls_to_visit and link not in visited_urls:
                    urls_to_visit.append(link)
        
        return {
            "status": "success",
            "website": website,
            "pages_visited": len(visited_urls),
            "visited_urls": list(visited_urls),
            "total_images": len(images_found),
            "images": list(images_found)[:max_images]
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


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

