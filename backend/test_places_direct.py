import requests
import time

def find_places_osm(lat: float, lon: float, radius: int, amenity: str):
    url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    node(around:{radius},{lat},{lon})[amenity={amenity}];
    out body;
    """
    
    try:
        response = requests.get(url, params={"data": query}, timeout=30)
        
        if response.status_code != 200:
            print(f"Помилка: статус {response.status_code}")
            return []
        
        if not response.text:
            print("Порожня відповідь від API")
            return []
        
        data = response.json()
        
    except requests.exceptions.JSONDecodeError:
        print(f"Помилка декодування JSON для {amenity}")
        return []
    except Exception as e:
        print(f"Помилка запиту: {e}")
        return []
    
    places = []
    for element in data.get("elements", []):
        places.append({
            "name": element.get("tags", {}).get("name", "Unknown"),
            "lat": element["lat"],
            "lon": element["lon"],
            "tags": element.get("tags", {})
        })
    
    return places

# Тестування
lat = 48.7164  # Кошице центр
lon = 21.2611
radius = 300  # 1 км
amenity = "restaurant"

print(f"Шукаємо {amenity} в радіусі {radius}м від координат ({lat}, {lon})")
print("-" * 60)

places = find_places_osm(lat, lon, radius, amenity)

print(f"\nЗнайдено місць: {len(places)}\n")

for i, place in enumerate(places[:10], 1):
    print(f"{i}. Назва: {place['name']}")
    print(f"   Координати: ({place['lat']}, {place['lon']})")
    print(f"   Додаткові теги: {place['tags']}")
    print()

# Тест з різними типами місць
print("\n" + "="*60)
print("Тестування різних типів місць:")
print("="*60)

test_types = ["cafe"]
for amenity_type in test_types:
    print(f"\nШукаємо {amenity_type}...")
    time.sleep(2)  # Затримка 2 секунди між запитами
    places = find_places_osm(lat, lon, radius, amenity_type)
    print(f"{amenity_type.upper()}: знайдено {len(places)} місць")
    if places:
        print(f"  Приклад: {places[0]['name']}")