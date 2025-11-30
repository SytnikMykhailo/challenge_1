import requests
import time
from typing import List, Dict, Optional

# ============================================================
# 1. OVERPASS API (OpenStreetMap) - NO API KEY NEEDED
# ============================================================
def find_places_osm(lat: float, lon: float, radius: int, amenity: str) -> List[Dict]:
    """
    Search for places using Overpass API (OpenStreetMap)
    
    Args:
        lat: Latitude
        lon: Longitude
        radius: Search radius in meters
        amenity: Type of place (restaurant, cafe, bar, museum, etc.)
    
    Returns:
        List of places with details
    """
    url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    node(around:{radius},{lat},{lon})[amenity={amenity}];
    out body;
    """
    
    try:
        response = requests.get(url, params={"data": query}, timeout=30)
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        
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
                "rating": "N/A",  # OSM doesn't have ratings
                "source": "OpenStreetMap"
            })
        
        return places
    
    except Exception as e:
        print(f"❌ OSM Error: {e}")
        return []


# ============================================================
# 2. NOMINATIM API (OpenStreetMap Geocoding) - NO API KEY NEEDED
# ============================================================
def find_places_nominatim(lat: float, lon: float, amenity: str, limit: int = 20) -> List[Dict]:
    """
    Search for places using Nominatim API
    
    Args:
        lat: Latitude
        lon: Longitude
        amenity: Type of place (restaurant, cafe, bar, etc.)
        limit: Maximum number of results
    
    Returns:
        List of places with details
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "format": "json",
        "q": f"{amenity} near {lat},{lon}",
        "limit": limit,
        "addressdetails": 1,
        "extratags": 1
    }
    headers = {"User-Agent": "TripPlannerApp/1.0"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        data = response.json()
        
        places = []
        for place in data:
            extratags = place.get("extratags", {})
            address = place.get("address", {})
            places.append({
                "name": place.get("display_name", "Unknown").split(",")[0],
                "lat": float(place.get("lat")),
                "lon": float(place.get("lon")),
                "type": place.get("type"),
                "cuisine": extratags.get("cuisine", "N/A"),
                "website": extratags.get("website", "N/A"),
                "phone": extratags.get("phone", "N/A"),
                "opening_hours": extratags.get("opening_hours", "N/A"),
                "city": address.get("city", address.get("town", "N/A")),
                "address": address.get("road", "N/A"),
                "rating": "N/A",
                "source": "Nominatim"
            })
        
        return places
    
    except Exception as e:
        print(f"❌ Nominatim Error: {e}")
        return []


# ============================================================
# 3. GOOGLE PLACES API - REQUIRES API KEY
# ============================================================
def find_places_google(lat: float, lon: float, radius: int, place_type: str, api_key: str) -> List[Dict]:
    """
    Search for places using Google Places API
    
    Args:
        lat: Latitude
        lon: Longitude
        radius: Search radius in meters
        place_type: Type of place (restaurant, cafe, bar, museum, etc.)
        api_key: Google Places API key
    
    Returns:
        List of places with details
    """
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
            print(f"❌ Google API status: {data.get('status')}")
            return []
        
        places = []
        for place in data.get("results", []):
            places.append({
                "name": place.get("name"),
                "lat": place["geometry"]["location"]["lat"],
                "lon": place["geometry"]["location"]["lng"],
                "rating": place.get("rating", "N/A"),
                "user_ratings_total": place.get("user_ratings_total", 0),
                "price_level": place.get("price_level", "N/A"),
                "address": place.get("vicinity", ""),
                "types": place.get("types", []),
                "phone": "N/A",
                "website": "N/A",
                "opening_hours": "N/A",
                "source": "Google Places"
            })
        
        return places
    
    except Exception as e:
        print(f"❌ Google Places Error: {e}")
        return []


# ============================================================
# 4. UNIVERSAL SEARCH FUNCTION
# ============================================================
def search_places(
    lat: float,
    lon: float,
    radius: int = 500,
    place_type: str = "restaurant",
    limit: int = 20,
    use_google: bool = False,
    google_api_key: Optional[str] = None
) -> List[Dict]:
    """
    Universal function to search for places using multiple APIs
    
    Args:
        lat: Latitude
        lon: Longitude
        radius: Search radius in meters
        place_type: Type of place (restaurant, cafe, bar, museum, park, etc.)
        limit: Maximum number of results
        use_google: Whether to use Google Places API (requires API key)
        google_api_key: Google Places API key (optional)
    
    Returns:
        List of places with combined results from multiple sources
    """
    all_places = []
    
    # Try OpenStreetMap Overpass API first (no API key needed)
    try:
        osm_places = find_places_osm(lat, lon, radius, place_type)
        all_places.extend(osm_places)
        print(f"✅ OSM: Found {len(osm_places)} places")
    except Exception as e:
        print(f"⚠️ OSM failed: {e}")
    
    # Try Nominatim API (no API key needed)
    if len(all_places) < limit:
        try:
            time.sleep(1)  # Rate limiting
            nominatim_places = find_places_nominatim(lat, lon, place_type, limit)
            all_places.extend(nominatim_places)
            print(f"✅ Nominatim: Found {len(nominatim_places)} places")
        except Exception as e:
            print(f"⚠️ Nominatim failed: {e}")
    
    # Try Google Places API if enabled and API key provided
    if use_google and google_api_key and len(all_places) < limit:
        try:
            time.sleep(0.5)
            google_places = find_places_google(lat, lon, radius, place_type, google_api_key)
            all_places.extend(google_places)
            print(f"✅ Google Places: Found {len(google_places)} places")
        except Exception as e:
            print(f"⚠️ Google Places failed: {e}")
    
    # Remove duplicates based on name and location
    unique_places = []
    seen = set()
    
    for place in all_places:
        key = (place["name"], round(place["lat"], 4), round(place["lon"], 4))
        if key not in seen:
            seen.add(key)
            unique_places.append(place)
    
    # Sort by rating if available
    def get_rating(place):
        rating = place.get("rating", "N/A")
        return float(rating) if rating != "N/A" else 0
    
    unique_places.sort(key=get_rating, reverse=True)
    
    return unique_places[:limit]


# ============================================================
# 5. HELPER FUNCTIONS
# ============================================================
def get_place_types():
    """
    Get list of supported place types
    
    Returns:
        Dictionary with categories and their types
    """
    return {
        "food": ["restaurant", "cafe", "bar", "fast_food", "pub", "bistro"],
        "culture": ["museum", "theatre", "cinema", "gallery", "library"],
        "nature": ["park", "garden", "viewpoint", "natural_reserve"],
        "shopping": ["mall", "market", "shop", "department_store"],
        "entertainment": ["nightclub", "casino", "amusement_park"],
        "accommodation": ["hotel", "hostel", "guest_house"],
        "transport": ["bus_station", "train_station", "airport"],
        "services": ["bank", "atm", "pharmacy", "hospital", "police"]
    }


def format_place_for_display(place: Dict) -> str:
    """
    Format place data for nice display
    
    Args:
        place: Place dictionary
    
    Returns:
        Formatted string
    """
    output = f"📍 **{place['name']}**\n"
    output += f"🌐 Coordinates: ({place['lat']:.4f}, {place['lon']:.4f})\n"
    
    if place.get("rating") != "N/A":
        output += f"⭐ Rating: {place['rating']}\n"
    
    if place.get("cuisine") != "N/A":
        output += f"🍽️ Cuisine: {place['cuisine']}\n"
    
    if place.get("address") != "N/A":
        output += f"🏠 Address: {place['address']}\n"
    
    if place.get("phone") != "N/A":
        output += f"📞 Phone: {place['phone']}\n"
    
    if place.get("website") != "N/A":
        output += f"🌐 Website: {place['website']}\n"
    
    if place.get("opening_hours") != "N/A":
        output += f"🕒 Hours: {place['opening_hours']}\n"
    
    output += f"ℹ️ Source: {place.get('source', 'Unknown')}\n"
    
    return output


# ============================================================
# 6. TESTING FUNCTION
# ============================================================
def test_search():
    """Test the search functionality"""
    print("\n🔍 Testing place search...\n")
    
    # Košice coordinates
    lat, lon = 48.7164, 21.2611
    
    # Test different place types
    for place_type in ["restaurant", "cafe", "museum"]:
        print(f"\n{'='*60}")
        print(f"Searching for: {place_type}")
        print('='*60)
        
        places = search_places(lat, lon, radius=500, place_type=place_type, limit=5)
        
        print(f"\n✅ Found {len(places)} places\n")
        
        for i, place in enumerate(places[:3], 1):
            print(f"{i}.")
            print(format_place_for_display(place))
            print()
        
        time.sleep(2)  # Rate limiting


if __name__ == "__main__":
    test_search()