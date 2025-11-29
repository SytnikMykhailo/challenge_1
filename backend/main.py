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


@app.get("/filter-images")
def filter_images_by_ai(
    website: str = Query(..., description="Website URL"),
    context: str = Query(..., description="What are you looking for?"),
    max_pages: int = Query(3, description="Maximum pages to scrape"),
    max_images: int = Query(20, description="Maximum images to collect")
):
    """
    Scrapes images and uses GPT to select the best image based on filenames
    """
    # 1. Get all images
    scrape_result = scrape_website_images(website, max_pages, max_images)
    
    if scrape_result.get("status") != "success":
        return scrape_result
    
    all_images = scrape_result.get("images", [])
    
    if not all_images:
        return {
            "status": "error",
            "message": "No images found on the website"
        }
    
    # 2. Create list of image filenames for GPT
    image_list = []
    for i, img_url in enumerate(all_images):
        filename = img_url.split('/')[-1]
        image_list.append(f"{i}: {filename} ({img_url})")
    
    images_text = "\n".join(image_list[:30])  # Limit to 30 images
    
    # 3. Ask GPT to select best images
    try:
        selection_response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": """You analyze image filenames and URLs to find the most relevant images.
Select the top 5 most relevant image indices based on their filenames.
Return ONLY a JSON array of indices, e.g., [0, 3, 7, 12, 15]"""
                },
                {
                    "role": "user",
                    "content": f"""Context: {context}

Available images:
{images_text}

Select the 5 most relevant image indices for the context. If less than 5 are relevant, select fewer. Return JSON array."""
                }
            ],
            temperature=0.3,
            max_tokens=100
        )
        
        selected_indices = json.loads(selection_response.choices[0].message.content.strip())
        print(f"🤖 GPT selected indices: {selected_indices}")
        
        # Get selected images
        filtered_images = []
        for idx in selected_indices:
            if 0 <= idx < len(all_images):
                filtered_images.append({
                    "url": all_images[idx],
                    "filename": all_images[idx].split('/')[-1],
                    "index": idx,
                    "confidence": 1.0 - (selected_indices.index(idx) * 0.15),  # Decrease by rank
                    "description": f"Selected by AI as rank {selected_indices.index(idx) + 1}"
                })
        
        # Fallback: if no images selected, return first one
        if not filtered_images:
            filtered_images.append({
                "url": all_images[0],
                "filename": all_images[0].split('/')[-1],
                "index": 0,
                "confidence": 0.1,
                "description": "Fallback: first image (AI found no good matches)"
            })
        
        return {
            "status": "success",
            "website": website,
            "context": context,
            "selection_method": "AI-powered",
            "total_images_analyzed": len(all_images),
            "matched_images": len(filtered_images),
            "filtered_images": filtered_images
        }
        
    except Exception as e:
        print(f"❌ Error with AI selection: {e}")
        # Fallback: return first image
        return {
            "status": "success",
            "website": website,
            "context": context,
            "selection_method": "fallback",
            "total_images_analyzed": len(all_images),
            "matched_images": 1,
            "filtered_images": [{
                "url": all_images[0],
                "filename": all_images[0].split('/')[-1],
                "confidence": 0.1,
                "description": "Fallback: first image"
            }]
        }


@app.get("/search-images-by-name")
def search_images_by_name(
    place_name: str = Query(..., description="Name of the place"),
    location: str = Query(None, description="City or location"),
    max_results: int = Query(5, description="Maximum number of images"),
    use_mock: bool = Query(False, description="Use mock data for testing")
):
    """
    Searches for images by place name using Google Custom Search API
    """
    # Mock data for testing
    if use_mock:
        return {
            "status": "success",
            "source": "mock_data",
            "place_name": place_name,
            "location": location,
            "search_query": f"{place_name} {location or ''}",
            "total_results": 3,
            "images": [
                {
                    "url": f"https://via.placeholder.com/800x600/4A90E2/FFFFFF?text={place_name.replace(' ', '+')}",
                    "thumbnail": f"https://via.placeholder.com/200x150/4A90E2/FFFFFF?text={place_name.replace(' ', '+')}",
                    "title": f"{place_name} - Main Photo",
                    "source": "placeholder.com",
                    "width": 800,
                    "height": 600
                },
                {
                    "url": f"https://via.placeholder.com/800x600/E24A4A/FFFFFF?text={place_name.replace(' ', '+')}+2",
                    "thumbnail": f"https://via.placeholder.com/200x150/E24A4A/FFFFFF?text={place_name.replace(' ', '+')}+2",
                    "title": f"{place_name} - Front View",
                    "source": "placeholder.com",
                    "width": 800,
                    "height": 600
                },
                {
                    "url": f"https://via.placeholder.com/800x600/4AE290/FFFFFF?text={place_name.replace(' ', '+')}+3",
                    "thumbnail": f"https://via.placeholder.com/200x150/4AE290/FFFFFF?text={place_name.replace(' ', '+')}+3",
                    "title": f"{place_name} - Detail View",
                    "source": "placeholder.com",
                    "width": 800,
                    "height": 600
                }
            ]
        }
    
    try:
        # Read Google API keys
        with open("api_google.txt", "r") as f:
            google_api_key = f.read().strip()
        
        with open("google_cx.txt", "r") as f:
            google_cx = f.read().strip()
        
        # Build search query
        search_query = place_name
        if location:
            search_query += f" {location}"
        
        # Google Custom Search API
        search_url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": google_api_key,
            "cx": google_cx,
            "q": search_query,
            "searchType": "image",
            "num": min(max_results, 10),
            "safe": "active",
            "imgSize": "large"
        }
        
        print(f"🔍 Searching Google for: {search_query}")
        print(f"   API Key (first 10 chars): {google_api_key[:10]}...")
        print(f"   CX (first 15 chars): {google_cx[:15]}...")
        
        response = requests.get(search_url, params=params, timeout=10)
        
        if response.status_code != 200:
            # Get detailed error message
            error_data = {}
            try:
                error_data = response.json()
            except:
                error_data = {"raw_response": response.text}
            
            return {
                "status": "error",
                "message": f"Google API error: {response.status_code}",
                "error_details": error_data,
                "api_key_prefix": google_api_key[:10] + "...",
                "cx_prefix": google_cx[:15] + "...",
                "search_query": search_query,
                "suggestion": "Check if API keys are correct and Custom Search API is enabled",
                "fallback": "Add ?use_mock=true to use mock data for testing"
            }
        
        data = response.json()
        
        # Check if there are results
        if not data.get("items"):
            return {
                "status": "success",
                "place_name": place_name,
                "location": location,
                "search_query": search_query,
                "total_results": 0,
                "images": [],
                "message": "No images found for this query"
            }
        
        # Extract image URLs
        images = []
        for item in data.get("items", []):
            images.append({
                "url": item.get("link"),
                "thumbnail": item.get("image", {}).get("thumbnailLink"),
                "title": item.get("title"),
                "source": item.get("displayLink"),
                "width": item.get("image", {}).get("width"),
                "height": item.get("image", {}).get("height")
            })
        
        return {
            "status": "success",
            "place_name": place_name,
            "location": location,
            "search_query": search_query,
            "total_results": len(images),
            "images": images
        }
    
    except FileNotFoundError as e:
        return {
            "status": "error",
            "message": "API key files not found. Create api_google.txt and google_cx.txt",
            "missing_file": str(e),
            "fallback": "Add ?use_mock=true to use mock data for testing"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error searching images: {str(e)}",
            "fallback": "Add ?use_mock=true to use mock data for testing"
        }

@app.get("/get-place-images")
def get_place_images(
    place_name: str = Query(None, description="Name of the place"),
    location: str = Query(None, description="City or location"),
    website: str = Query(None, description="Website URL (if available)"),
    context: str = Query("main photo", description="Context for filtering"),
    use_mock: bool = Query(False, description="Use mock data for testing")
):
    """
    Universal endpoint: gets images from website OR Google search
    Use when you have either website OR place name + location
    """
    # Strategy 1: If website is provided, scrape it
    if website:
        print(f"🌐 Strategy: Scraping website {website}")
        try:
            result = filter_images_by_ai(
                website=website,
                context=context,
                max_pages=2,
                max_images=15
            )
            
            if result.get("status") == "success" and result.get("filtered_images"):
                return {
                    "status": "success",
                    "source": "website",
                    "place_name": place_name or "Unknown",
                    "website": website,
                    "images": result.get("filtered_images", [])
                }
        except Exception as e:
            print(f"⚠️ Website scraping failed: {e}")
    
    # Strategy 2: Search by name using Google
    if place_name:
        print(f"🔍 Strategy: Google search for '{place_name}'")
        result = search_images_by_name(
            place_name=place_name,
            location=location,
            max_results=5,
            use_mock=use_mock
        )
        
        if result.get("status") == "success":
            return {
                "status": "success",
                "source": result.get("source", "google_search"),
                "place_name": place_name,
                "location": location,
                "images": result.get("images", [])
            }
        else:
            # Return error from search_images_by_name
            return result
    
    # Strategy 3: No valid input
    return {
        "status": "error",
        "message": "Please provide either 'website' OR 'place_name' (+ optional 'location')",
        "received_params": {
            "place_name": place_name,
            "location": location,
            "website": website
        },
        "example_usage": {
            "with_website": "/get-place-images?website=https://example.com&context=bar",
            "with_name": "/get-place-images?place_name=Singing Fountain&location=Košice",
            "with_mock": "/get-place-images?place_name=St. Elisabeth Cathedral&location=Košice&use_mock=true"
        }
    }

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
    Scrapes images from a website (without SVG), including internal pages
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
            """Check if URL belongs to the same domain"""
            parsed = urlparse(url)
            return parsed.netloc == base_domain and parsed.scheme in ['http', 'https']
        
        def extract_images_and_links(url):
            """Extract images and links from a page"""
            if url in visited_urls or len(visited_urls) >= max_pages:
                return [], []
            
            visited_urls.add(url)
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find all images
                page_images = []
                for img in soup.find_all('img'):
                    img_url = img.get('src') or img.get('data-src')
                    if img_url:
                        # Convert relative URLs to absolute
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            img_url = urljoin(url, img_url)
                        elif not img_url.startswith('http'):
                            img_url = urljoin(url, img_url)
                        
                        # Filter SVG, logos and icons
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
                
                # Find all internal links
                page_links = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    # Convert relative URLs
                    if href.startswith('/'):
                        href = urljoin(url, href)
                    elif not href.startswith('http'):
                        href = urljoin(url, href)
                    
                    # Filter only internal links
                    if is_valid_url(href) and href not in visited_urls:
                        # Ignore links to files and anchors
                        if not any(ext in href.lower() for ext in ['.pdf', '.doc', '.zip', '#']):
                            page_links.append(href)
                
                return page_images, page_links
            
            except Exception as e:
                print(f"❌ Error processing {url}: {e}")
                return [], []
        
        # Traverse pages
        while urls_to_visit and len(visited_urls) < max_pages and len(images_found) < max_images:
            current_url = urls_to_visit.pop(0)
            
            print(f"🔍 Scanning: {current_url}")
            page_images, page_links = extract_images_and_links(current_url)
            
            # Add found images
            for img in page_images:
                if len(images_found) < max_images:
                    images_found.add(img)
            
            # Add new links for traversal
            for link in page_links[:3]:  # Limit number of links from each page
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
    Processes user request, determines activity type/place and preferences.
    Returns structured data in JSON format.
    """
    global tags_for_places, settings
    
    # Use gpt-3.5-turbo instead of gpt-4 (faster and cheaper)
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
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
        temperature=0.3,  # Lower temperature = faster response
        max_tokens=500     # Token limit
    )
    
    # Get response from GPT
    gpt_response = response.choices[0].message.content
    
    try:
        # Parse JSON response
        parsed_data = json.loads(gpt_response)
        
        # Update global variables
        tags_for_places = parsed_data.get("place_types", [])
        settings = {
            "activity_type": parsed_data.get("activity_type"),
            "cuisine": parsed_data.get("cuisine"),
            "preferences": parsed_data.get("preferences", {}),
            "location": parsed_data.get("location", {}),
            "time_constraints": parsed_data.get("time_constraints", {}),
            "additional_notes": parsed_data.get("additional_notes")
        }
        
        # Return structured data
        return {
            "status": "success",
            "original_request": request,
            "parsed_data": parsed_data,
            "tags_for_places": tags_for_places,
            "settings": settings,
            "next_step": "Use /search endpoint to find places based on these parameters"
        }
        
    except json.JSONDecodeError as e:
        # If GPT didn't return valid JSON
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
    """
    Answers general questions about daily life
    """
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an AI assistant that helps with questions about daily routines and everyday life. Do not answer questions outside this topic; politely refuse to respond to unrelated questions."},
            {"role": "user", "content": question}
        ],
        temperature=0.5,
        max_tokens=300
    )
    answer = response.choices[0].message.content
    return {"answer": answer}

