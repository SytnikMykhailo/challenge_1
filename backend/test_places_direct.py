import requests
import time
from typing import List, Dict

# ============================================================
# 1. OVERPASS API (OpenStreetMap)
# ============================================================
def test_overpass_api():
    """Тестування Overpass API (OSM)"""
    print("\n" + "="*60)
    print("OVERPASS API (OpenStreetMap)")
    print("="*60)
    
    def find_places_osm(lat: float, lon: float, radius: int, amenity: str) -> List[Dict]:
        url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json];
        node(around:{radius},{lat},{lon})[amenity={amenity}];
        out body;
        """
        
        try:
            response = requests.get(url, params={"data": query}, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ Помилка: статус {response.status_code}")
                return []
            
            if not response.text:
                print("❌ Порожня відповідь від API")
                return []
            
            data = response.json()
            
        except requests.exceptions.JSONDecodeError:
            print(f"❌ Помилка декодування JSON для {amenity}")
            return []
        except Exception as e:
            print(f"❌ Помилка запиту: {e}")
            return []
        
        places = []
        for element in data.get("elements", []):
            tags = element.get("tags", {})
            places.append({
                "name": tags.get("name", "Unknown"),
                "lat": element["lat"],
                "lon": element["lon"],
                "cuisine": tags.get("cuisine", "N/A"),
                "description": tags.get("description", "N/A"),
                "website": tags.get("website", "N/A"),
                "phone": tags.get("phone", "N/A"),
                "opening_hours": tags.get("opening_hours", "N/A"),
                "address": tags.get("addr:street", "N/A"),
                "all_tags": tags
            })
        
        return places
    
    # Тестування
    lat, lon, radius = 48.7164, 21.2611, 300
    
    for amenity in ["restaurant", "cafe"]:
        print(f"\n🔍 Шукаємо {amenity} в радіусі {radius}м...")
        places = find_places_osm(lat, lon, radius, amenity)
        print(f"✅ Знайдено: {len(places)} місць")
        
        if places:
            place = places[0]
            print(f"\n   📍 {place['name']}")
            print(f"   🌐 Координати: ({place['lat']}, {place['lon']})")
            print(f"   🍽️  Кухня: {place['cuisine']}")
            print(f"   📝 Опис: {place['description']}")
            print(f"   🌐 Веб-сайт: {place['website']}")
            print(f"   📞 Телефон: {place['phone']}")
            print(f"   🕒 Години роботи: {place['opening_hours']}")
            print(f"   🏠 Адреса: {place['address']}")
            print(f"   🏷️  Всі теги: {list(place['all_tags'].keys())}")
        
        time.sleep(2)


# ============================================================
# 2. NOMINATIM API (OpenStreetMap Geocoding)
# ============================================================
def test_nominatim_api():
    """Тестування Nominatim API"""
    print("\n" + "="*60)
    print("NOMINATIM API (OSM Geocoding)")
    print("="*60)
    
    def find_places_nominatim(lat: float, lon: float, amenity: str) -> List[Dict]:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "format": "json",
            "q": f"{amenity} near {lat},{lon}",
            "limit": 20,
            "addressdetails": 1,
            "extratags": 1
        }
        headers = {"User-Agent": "TestApp/1.0"}
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            data = response.json()
            
            places = []
            for place in data:
                extratags = place.get("extratags", {})
                address = place.get("address", {})
                places.append({
                    "name": place.get("display_name"),
                    "lat": float(place.get("lat")),
                    "lon": float(place.get("lon")),
                    "type": place.get("type"),
                    "cuisine": extratags.get("cuisine", "N/A"),
                    "website": extratags.get("website", "N/A"),
                    "phone": extratags.get("phone", "N/A"),
                    "opening_hours": extratags.get("opening_hours", "N/A"),
                    "city": address.get("city", "N/A"),
                    "road": address.get("road", "N/A"),
                    "all_tags": extratags
                })
            
            return places
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []
    
    # Тестування
    lat, lon = 48.7164, 21.2611
    
    for amenity in ["restaurant", "cafe"]:
        print(f"\n🔍 Шукаємо {amenity}...")
        places = find_places_nominatim(lat, lon, amenity)
        print(f"✅ Знайдено: {len(places)} місць")
        
        if places:
            place = places[0]
            print(f"\n   📍 {place['name'][:60]}...")
            print(f"   🌐 Координати: ({place['lat']}, {place['lon']})")
            print(f"   🍽️  Кухня: {place['cuisine']}")
            print(f"   🌐 Веб-сайт: {place['website']}")
            print(f"   📞 Телефон: {place['phone']}")
            print(f"   🕒 Години роботи: {place['opening_hours']}")
            print(f"   🏙️  Місто: {place['city']}, {place['road']}")
            print(f"   🏷️  Теги: {list(place['all_tags'].keys())[:5]}")
        
        time.sleep(1)


# ============================================================
# 3. FOURSQUARE API
# ============================================================
def test_foursquare_api():
    """Тестування Foursquare API"""
    print("\n" + "="*60)
    print("FOURSQUARE API")
    print("="*60)
    
    def find_places_foursquare(lat: float, lon: float, query: str, api_key: str) -> List[Dict]:
        url = "https://api.foursquare.com/v3/places/search"
        headers = {
            "Accept": "application/json",
            "Authorization": api_key
        }
        params = {
            "ll": f"{lat},{lon}",
            "radius": 300,
            "query": query,
            "limit": 20,
            "fields": "name,geocodes,categories,rating,stats,description,tel,website,location"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            data = response.json()
            
            places = []
            for place in data.get("results", []):
                location = place.get("location", {})
                places.append({
                    "name": place.get("name"),
                    "lat": place["geocodes"]["main"]["latitude"],
                    "lon": place["geocodes"]["main"]["longitude"],
                    "category": place.get("categories", [{}])[0].get("name", "Unknown"),
                    "rating": place.get("rating", "N/A"),
                    "description": place.get("description", "N/A"),
                    "phone": place.get("tel", "N/A"),
                    "website": place.get("website", "N/A"),
                    "address": location.get("address", "N/A"),
                    "city": location.get("locality", "N/A"),
                    "stats": place.get("stats", {})
                })
            
            return places
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []
    
    # Тестування
    api_key = "YOUR_FOURSQUARE_API_KEY"  # Замініть на ваш ключ
    lat, lon = 48.7164, 21.2611
    
    if api_key == "YOUR_FOURSQUARE_API_KEY":
        print("⚠️  Додайте Foursquare API ключ для тестування")
        return
    
    for query in ["restaurant", "cafe"]:
        print(f"\n🔍 Шукаємо {query}...")
        places = find_places_foursquare(lat, lon, query, api_key)
        print(f"✅ Знайдено: {len(places)} місць")
        
        if places:
            place = places[0]
            print(f"\n   📍 {place['name']}")
            print(f"   🌐 Координати: ({place['lat']}, {place['lon']})")
            print(f"   🏷️  Категорія: {place['category']}")
            print(f"   ⭐ Рейтинг: {place['rating']}")
            print(f"   📝 Опис: {place['description']}")
            print(f"   📞 Телефон: {place['phone']}")
            print(f"   🌐 Веб-сайт: {place['website']}")
            print(f"   🏠 Адреса: {place['address']}, {place['city']}")
        
        time.sleep(1)


# ============================================================
# 4. OPENTRIPMAP API
# ============================================================
def test_opentripmap_api():
    """Тестування OpenTripMap API"""
    print("\n" + "="*60)
    print("OPENTRIPMAP API")
    print("="*60)
    
    def find_places_opentripmap(lat: float, lon: float, radius: int, api_key: str) -> List[Dict]:
        url = "https://api.opentripmap.com/0.1/en/places/radius"
        params = {
            "radius": radius,
            "lon": lon,
            "lat": lat,
            "apikey": api_key,
            "limit": 20
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            places = []
            for place in data.get("features", []):
                props = place["properties"]
                
                # Отримати детальну інформацію
                xid = props.get("xid")
                details = {}
                if xid:
                    detail_url = f"https://api.opentripmap.com/0.1/en/places/xid/{xid}"
                    detail_response = requests.get(detail_url, params={"apikey": api_key}, timeout=10)
                    if detail_response.status_code == 200:
                        details = detail_response.json()
                    time.sleep(0.2)
                
                places.append({
                    "name": props.get("name", "Unknown"),
                    "lat": place["geometry"]["coordinates"][1],
                    "lon": place["geometry"]["coordinates"][0],
                    "kinds": props.get("kinds", ""),
                    "rate": props.get("rate", "N/A"),
                    "description": details.get("wikipedia_extracts", {}).get("text", "N/A"),
                    "wikipedia": details.get("wikipedia", "N/A"),
                    "image": details.get("image", "N/A"),
                    "address": details.get("address", {})
                })
            
            return places
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []
    
    # Тестування
    api_key = "YOUR_OPENTRIPMAP_API_KEY"  # Замініть на ваш ключ
    lat, lon, radius = 48.7164, 21.2611, 300
    
    if api_key == "YOUR_OPENTRIPMAP_API_KEY":
        print("⚠️  Додайте OpenTripMap API ключ для тестування")
        return
    
    print(f"\n🔍 Шукаємо туристичні місця в радіусі {radius}м...")
    places = find_places_opentripmap(lat, lon, radius, api_key)
    print(f"✅ Знайдено: {len(places)} місць")
    
    if places:
        for i, place in enumerate(places[:3], 1):
            print(f"\n   {i}. 📍 {place['name']}")
            print(f"      🏷️  Види: {place['kinds']}")
            print(f"      ⭐ Рейтинг: {place['rate']}")
            print(f"      📝 Опис: {place['description'][:100]}...")
            print(f"      🌐 Wikipedia: {place['wikipedia']}")


# ============================================================
# 5. HERE API
# ============================================================
def test_here_api():
    """Тестування HERE API"""
    print("\n" + "="*60)
    print("HERE API")
    print("="*60)
    
    def find_places_here(lat: float, lon: float, category: str, api_key: str) -> List[Dict]:
        url = "https://browse.search.hereapi.com/v1/browse"
        params = {
            "at": f"{lat},{lon}",
            "categories": category,
            "limit": 20,
            "apiKey": api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            places = []
            for item in data.get("items", []):
                address = item.get("address", {})
                contacts = item.get("contacts", [{}])[0] if item.get("contacts") else {}
                places.append({
                    "name": item.get("title"),
                    "lat": item["position"]["lat"],
                    "lon": item["position"]["lng"],
                    "category": item.get("categories", [{}])[0].get("name", "Unknown"),
                    "address": address.get("label", ""),
                    "street": address.get("street", "N/A"),
                    "city": address.get("city", "N/A"),
                    "postal_code": address.get("postalCode", "N/A"),
                    "phone": contacts.get("phone", [{}])[0].get("value", "N/A") if contacts.get("phone") else "N/A",
                    "website": contacts.get("www", [{}])[0].get("value", "N/A") if contacts.get("www") else "N/A",
                    "opening_hours": item.get("openingHours", "N/A")
                })
            
            return places
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []
    
    # Тестування
    api_key = "YOUR_HERE_API_KEY"  # Замініть на ваш ключ
    lat, lon = 48.7164, 21.2611
    
    if api_key == "YOUR_HERE_API_KEY":
        print("⚠️  Додайте HERE API ключ для тестування")
        return
    
    for category in ["100-1000-0000", "200-2000-0000"]:  # restaurant, cafe
        print(f"\n🔍 Шукаємо категорію {category}...")
        places = find_places_here(lat, lon, category, api_key)
        print(f"✅ Знайдено: {len(places)} місць")
        
        if places:
            place = places[0]
            print(f"\n   📍 {place['name']}")
            print(f"   🏷️  Категорія: {place['category']}")
            print(f"   🏠 Адреса: {place['address']}")
            print(f"   🏙️  Місто: {place['city']}, {place['postal_code']}")
            print(f"   📞 Телефон: {place['phone']}")
            print(f"   🌐 Веб-сайт: {place['website']}")
            print(f"   🕒 Години роботи: {place['opening_hours']}")


# ============================================================
# 6. YELP FUSION API
# ============================================================
def test_yelp_api():
    """Тестування Yelp Fusion API"""
    print("\n" + "="*60)
    print("YELP FUSION API")
    print("="*60)
    
    def find_places_yelp(lat: float, lon: float, term: str, api_key: str) -> List[Dict]:
        url = "https://api.yelp.com/v3/businesses/search"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "latitude": lat,
            "longitude": lon,
            "term": term,
            "radius": 300,
            "limit": 20
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            data = response.json()
            
            places = []
            for business in data.get("businesses", []):
                location = business.get("location", {})
                places.append({
                    "name": business.get("name"),
                    "lat": business["coordinates"]["latitude"],
                    "lon": business["coordinates"]["longitude"],
                    "rating": business.get("rating", "N/A"),
                    "review_count": business.get("review_count", 0),
                    "price": business.get("price", "N/A"),
                    "phone": business.get("phone", "N/A"),
                    "categories": [cat["title"] for cat in business.get("categories", [])],
                    "address": ", ".join(location.get("display_address", [])),
                    "city": location.get("city", "N/A"),
                    "transactions": business.get("transactions", []),
                    "url": business.get("url", "N/A")
                })
            
            return places
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []
    
    # Тестування
    api_key = "YOUR_YELP_API_KEY"  # Замініть на ваш ключ
    lat, lon = 48.7164, 21.2611
    
    if api_key == "YOUR_YELP_API_KEY":
        print("⚠️  Додайте Yelp API ключ для тестування")
        return
    
    for term in ["restaurant", "cafe"]:
        print(f"\n🔍 Шукаємо {term}...")
        places = find_places_yelp(lat, lon, term, api_key)
        print(f"✅ Знайдено: {len(places)} місць")
        
        if places:
            place = places[0]
            print(f"\n   📍 {place['name']}")
            print(f"   ⭐ Рейтинг: {place['rating']} ({place['review_count']} відгуків)")
            print(f"   💰 Ціна: {place['price']}")
            print(f"   📞 Телефон: {place['phone']}")
            print(f"   🏷️  Категорії: {', '.join(place['categories'])}")
            print(f"   🏠 Адреса: {place['address']}, {place['city']}")
            print(f"   🛒 Транзакції: {', '.join(place['transactions']) if place['transactions'] else 'N/A'}")
            print(f"   🌐 URL: {place['url']}")
        
        time.sleep(1)


# ============================================================
# 7. GOOGLE PLACES API
# ============================================================
def test_google_places_api():
    """Тестування Google Places API"""
    print("\n" + "="*60)
    print("GOOGLE PLACES API")
    print("="*60)
    
    def find_places_google(lat: float, lon: float, radius: int, place_type: str, api_key: str) -> List[Dict]:
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat},{lon}",
            "radius": radius,
            "type": place_type,
            "key": api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get("status") != "OK":
                print(f"❌ API статус: {data.get('status')}")
                return []
            
            places = []
            for place in data.get("results", []):
                # Отримати детальну інформацію
                place_id = place.get("place_id")
                details = {}
                if place_id:
                    detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
                    detail_params = {
                        "place_id": place_id,
                        "fields": "name,formatted_phone_number,website,opening_hours,price_level,reviews",
                        "key": api_key
                    }
                    detail_response = requests.get(detail_url, params=detail_params, timeout=10)
                    if detail_response.status_code == 200:
                        details = detail_response.json().get("result", {})
                    time.sleep(0.1)
                
                places.append({
                    "name": place.get("name"),
                    "lat": place["geometry"]["location"]["lat"],
                    "lon": place["geometry"]["location"]["lng"],
                    "rating": place.get("rating", "N/A"),
                    "user_ratings_total": place.get("user_ratings_total", 0),
                    "price_level": place.get("price_level", "N/A"),
                    "address": place.get("vicinity", ""),
                    "types": place.get("types", []),
                    "phone": details.get("formatted_phone_number", "N/A"),
                    "website": details.get("website", "N/A"),
                    "opening_hours": details.get("opening_hours", {}).get("weekday_text", "N/A"),
                    "reviews": [r.get("text", "")[:100] for r in details.get("reviews", [])[:2]]
                })
            
            return places
        except Exception as e:
            print(f"❌ Помилка: {e}")
            return []
    

    with open("api_google.txt", "r") as f:
        api_key = f.read().strip()

    # Тестування
    lat, lon, radius = 48.7164, 21.2611, 300
    
    if api_key == "YOUR_GOOGLE_PLACES_API_KEY":
        print("⚠️  Додайте Google Places API ключ для тестування")
        return
    
    for place_type in ["restaurant", "cafe"]:
        print(f"\n🔍 Шукаємо {place_type}...")
        places = find_places_google(lat, lon, radius, place_type, api_key)
        print(f"✅ Знайдено: {len(places)} місць")
        
        if places:
            place = places[0]
            print(f"\n   📍 {place['name']}")
            print(f"   ⭐ Рейтинг: {place['rating']} ({place['user_ratings_total']} відгуків)")
            print(f"   💰 Рівень цін: {place['price_level']}")
            print(f"   🏠 Адреса: {place['address']}")
            print(f"   🏷️  Типи: {', '.join(place['types'][:3])}")
            print(f"   📞 Телефон: {place['phone']}")
            print(f"   🌐 Веб-сайт: {place['website']}")
            if place['opening_hours'] != "N/A":
                print(f"   🕒 Години роботи: {place['opening_hours'][0] if isinstance(place['opening_hours'], list) else 'N/A'}")
            if place['reviews']:
                print(f"   💬 Відгук: {place['reviews'][0]}...")
        
        time.sleep(1)


# ============================================================
# ГОЛОВНА ФУНКЦІЯ
# ============================================================
def main():
    print("\n" + "🌍 "*20)
    print("ТЕСТУВАННЯ ВСІХ API ДЛЯ ПОШУКУ МІСЦЬ")
    print("🌍 "*20)
    
    # Запуск тестів
    test_overpass_api()
    test_nominatim_api()
    test_foursquare_api()
    test_opentripmap_api()
    test_here_api()
    test_yelp_api()
    test_google_places_api()
    
    print("\n" + "="*60)
    print("✅ ТЕСТУВАННЯ ЗАВЕРШЕНО")
    print("="*60)


if __name__ == "__main__":
    main()