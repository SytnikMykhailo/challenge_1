from fastapi import FastAPI, Query, Response, Body
from fastapi.middleware.cors import CORSMiddleware
import openai
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from typing import Optional, List, Dict
from places_api import search_places, format_place_for_display, get_place_types

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

with open("api_key.txt", "r") as f:
    api_key = f.read().strip()

openai.api_key = api_key

try:
    with open("api_google.txt", "r") as f:
        google_places_api_key = f.read().strip()
except:
    google_places_api_key = None

tags_for_places = []
settings = {}


def is_valid_image_url(url):
    """Check if URL is a valid image (not tracking pixel or analytics)"""
    url_lower = url.lower()
    
    # Block tracking and analytics
    blocked_patterns = [
        'facebook.com/tr', 'google-analytics', 'googletagmanager',
        'doubleclick.net', 'analytics', 'pixel', 'tracking', '1x1',
        'noscript', 'tr?id=', '&ev=', 'fbq', 'gtag', '_ga', 'collect?',
        'ad.', 'ads.', 'adserver', 'beacon', 'counter'
    ]
    
    if any(blocked in url_lower for blocked in blocked_patterns):
        return False
    
    # Check for valid image extensions
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.avif']
    has_valid_extension = any(url_lower.endswith(ext) for ext in valid_extensions)
    
    if has_valid_extension:
        return True
    
    # Check query parameters for tracking
    if '?' in url:
        query_part = url.split('?')[1].lower()
        tracking_params = ['ev=', 'noscript', 'tr?', 'pixel', 'analytics']
        if any(param in query_part for param in tracking_params):
            return False
    
    # Allow URLs without extension if they don't match blocked patterns
    return True


def should_visit_url_for_context(url: str, context: str) -> tuple[bool, float]:
    """
    Determines if URL is relevant for given context
    Returns: (should_visit, relevance_score)
    """
    url_lower = url.lower()
    path = urlparse(url).path.lower()
    
    context_lower = context.lower()
    
    # Define context-specific URL patterns with MORE SPECIFIC matching
    context_patterns = {
        "interior": {
            "high_priority": [
                "interior", "interiér", "priestory", "miestnosti",
                "gallery", "galeria", "photos", "fotografie", "fotky",
                "inside", "rooms", "space"
            ],
            "medium_priority": ["about", "o-nas", "o-nás"],
            "skip": [
                "menu", "jedálny", "jedalny", "delivery", "donáška", "donaska",
                "objednavka", "objednávka", "order", "contact", "kontakt",
                "rezervacia", "rezervácia", "booking", "shop", "obchod",
                "career", "kariera", "job", "práca", "tea", "čaj", "caj"  # ← ADD tea
            ]
        },
        "tea": {  # ← NEW CONTEXT
            "high_priority": [
                "tea", "čaj", "caj", "cajovna", "čajovňa",
                "menu", "ponuka", "sortiment", "nabidka", "nabídka",
                "gallery", "galeria", "photos", "fotografie"
            ],
            "medium_priority": ["about", "o-nas", "o-nás"],
            "skip": [
                "contact", "kontakt", "rezervacia", "booking",
                "delivery", "career", "job", "miestnosti", "priestory", "rooms"  # ← Skip rooms for tea
            ]
        },
        "food": {
            "high_priority": [
                "menu", "jedálny", "jedalny", "dishes", "food", "jedla",
                "gallery", "photos", "fotografie", "cuisine", "kuchyna"
            ],
            "medium_priority": ["about", "o-nas", "restauracia", "restaurant"],
            "skip": [
                "contact", "kontakt", "rezervacia", "booking",
                "delivery", "career", "job", "miestnosti", "interior"
            ]
        },
        "atmosphere": {
            "high_priority": [
                "gallery", "galeria", "photos", "fotografie",
                "interior", "interiér", "atmosphere", "atmosfera",
                "events", "podujatia", "akcie"
            ],
            "medium_priority": ["about", "o-nas", "bar", "restaurant"],
            "skip": [
                "menu", "contact", "kontakt", "delivery",
                "order", "rezervacia", "career"
            ]
        }
    }
    
    # Detect context category with BETTER MATCHING
    detected_context = None
    
    # Check for specific keywords in context
    if any(word in context_lower for word in ["tea", "čaj", "caj", "cajovna"]):
        detected_context = "tea"
    elif any(word in context_lower for word in ["interior", "interiér", "priestor", "miestnost"]):
        detected_context = "interior"
    elif any(word in context_lower for word in ["food", "jedlo", "menu", "dish"]):
        detected_context = "food"
    elif any(word in context_lower for word in ["atmosphere", "atmosfera", "event"]):
        detected_context = "atmosphere"
    else:
        # Default: try to guess from context
        detected_context = "tea"  # Default for this case
    
    patterns = context_patterns.get(detected_context, context_patterns["tea"])
    
    # Check high priority patterns
    for pattern in patterns["high_priority"]:
        if pattern in path or pattern in url_lower:
            print(f"      ✅ HIGH priority ({detected_context}): '{pattern}' found")
            return True, 0.95  # ← Increased from 0.9
    
    # Check skip patterns FIRST (before medium)
    for pattern in patterns["skip"]:
        if pattern in path or pattern in url_lower:
            print(f"      ❌ SKIP ({detected_context}): '{pattern}' found (not relevant)")
            return False, 0.0
    
    # Check medium priority patterns
    for pattern in patterns["medium_priority"]:
        if pattern in path or pattern in url_lower:
            print(f"      ℹ️ MEDIUM priority ({detected_context}): '{pattern}' found")
            return True, 0.5  # ← Decreased from 0.6
    
    # Default: low priority (generic page)
    print(f"      ⚠️ LOW priority ({detected_context}): generic page")
    return True, 0.2  # ← Decreased from 0.3


@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}


def ai_score_url_relevance(url: str, context: str, page_title: str = "", link_text: str = "") -> float:
    """
    Uses GPT to score URL relevance for given context
    Returns: relevance score 0.0-1.0
    """
    try:
        # Prepare URL info for GPT
        path = urlparse(url).path
        
        prompt = f"""You are analyzing a URL to determine if it's relevant for the context: "{context}"

URL: {url}
URL Path: {path}
Page Title: {page_title or "N/A"}
Link Text: {link_text or "N/A"}

Analyze this URL and determine how relevant it is for finding images about "{context}".

Consider:
- URL path keywords (e.g., /gallery/, /menu/, /interior/, /ponuka/)
- Slovakian language patterns (e.g., "čaj" = tea, "ponuka" = offer/menu, "miestnosti" = rooms)
- Page purpose based on path structure
- Whether this page likely contains relevant images

Return ONLY a number between 0.0 and 1.0:
- 1.0 = Perfect match (e.g., /gallery/ for "interior")
- 0.8 = Very relevant (e.g., /ponuka/ for "tea")
- 0.5 = Somewhat relevant
- 0.2 = Low relevance
- 0.0 = Not relevant (e.g., /contact/ for any context)

Return ONLY the number, nothing else."""

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at analyzing URLs for content relevance. Return only a decimal number."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=10
        )
        
        score_text = response.choices[0].message.content.strip()
        
        # Extract number from response
        import re
        match = re.search(r'(\d+\.?\d*)', score_text)
        if match:
            score = float(match.group(1))
            score = min(max(score, 0.0), 1.0)  # Clamp to 0.0-1.0
            return score
        else:
            return 0.3  # Default if parsing fails
    
    except Exception as e:
        print(f"⚠️ AI scoring failed: {e}")
        return 0.3  # Default fallback


@app.get("/scrape-website-images")
def scrape_website_images(
    website: str = Query(..., description="Website URL"),
    max_pages: int = Query(50, description="Maximum pages to scrape"),
    max_images: int = Query(200, description="Maximum images to collect"),
    context: str = Query("interior", description="Context for smart URL filtering"),
    min_images_per_page: int = Query(5, description="Stop if page has enough good images"),
    use_ai_scoring: bool = Query(True, description="Use AI to score URL relevance")
):
    """
    TWO-PHASE approach with AI-powered URL scoring:
    1. Fast scan all pages with AI scoring URLs
    2. Deep scrape only the best page
    """
    # Initialize variables
    visited_urls = set()
    skipped_urls = set()
    
    # Track all pages with their potential
    page_scores = []
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        initial_url = website.split('#')[0]
        urls_to_visit = [(website, 1.0, "Main page", "")]  # (url, priority, title, link_text)
        
        base_domain = urlparse(initial_url).netloc
        
        def is_valid_url(url):
            clean_url = url.split('#')[0]
            parsed = urlparse(clean_url)
            return parsed.netloc == base_domain and parsed.scheme in ['http', 'https']
        
        def normalize_url(url):
            return url.split('#')[0].rstrip('/')
        
        def quick_scan_page(url, priority, page_title, link_text):
            """PHASE 1: Quick scan with AI-powered URL scoring"""
            normalized = normalize_url(url)
            
            if normalized in visited_urls:
                return [], 0
            
            visited_urls.add(normalized)
            
            try:
                print(f"\n⚡ Quick scan [{len(visited_urls)}/{max_pages}]: {url}")
                print(f"   Initial priority: {priority:.2f} | Context: '{context}'")
                
                # AI SCORING: Ask GPT if this URL is relevant
                if use_ai_scoring:
                    ai_score = ai_score_url_relevance(url, context, page_title, link_text)
                    print(f"   🤖 AI relevance score: {ai_score:.2f}")
                    
                    # Blend initial priority with AI score (AI has 70% weight)
                    priority = priority * 0.3 + ai_score * 0.7
                    print(f"   📊 Final priority: {priority:.2f} (blended)")
                
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Get page title for better AI analysis
                page_title_tag = soup.find('title')
                page_title = page_title_tag.get_text() if page_title_tag else ""
                
                # Count potential images (with deduplication)
                img_tags = soup.find_all('img')
                
                valid_count = 0
                seen_base_names = set()
                
                for img in img_tags:
                    src = img.get('src', '').lower()
                    if not src:
                        continue
                    
                    if any(bad in src for bad in ['logo', 'icon', 'favicon', 'sprite', '1x1']):
                        continue
                    
                    import re
                    filename = src.split('/')[-1]
                    base_name = re.sub(r'-\d+x\d+\.', '.', filename)
                    base_name = re.sub(r'_(thumb|thumbnail|small|medium)\.', '.', base_name)
                    
                    if base_name not in seen_base_names:
                        seen_base_names.add(base_name)
                        valid_count += 1
                
                print(f"   📊 Found ~{valid_count} unique potential images")
                
                # SCORING: AI priority is 80%, image count is 20%
                context_score = priority * 0.8
                image_score = min(valid_count / 30, 1.0) * 0.2
                combined_score = context_score + image_score
                
                # Penalty for too few images
                if valid_count < 3:
                    combined_score *= 0.3
                    print(f"   ⚠️ Low image count penalty applied")
                
                print(f"   🎯 Score: {combined_score:.2f} (context={context_score:.2f} + images={image_score:.2f})")
                
                # Store page score
                page_scores.append({
                    "url": url,
                    "priority": priority,
                    "ai_score": ai_score if use_ai_scoring else None,
                    "estimated_images": valid_count,
                    "score": combined_score,
                    "context_score": context_score,
                    "image_score": image_score,
                    "page_title": page_title
                })
                
                # Find internal links with metadata
                page_links = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    link_text = link.get_text(strip=True)
                    
                    if href.startswith('/'):
                        href = urljoin(url.split('#')[0], href)
                    elif href.startswith('#'):
                        continue
                    elif not href.startswith('http'):
                        href = urljoin(url.split('#')[0], href)
                    
                    if is_valid_url(href):
                        normalized_href = normalize_url(href)
                        if normalized_href not in visited_urls and normalized_href not in skipped_urls:
                            if not any(ext in href.lower() for ext in ['.pdf', '.doc', '.zip', '.mp4', '.mp3', '.xml', '.json']):
                                # Rule-based quick filter (to save API calls)
                                should_visit, relevance = should_visit_url_for_context(href, context)
                                
                                if should_visit:
                                    page_links.append((href, relevance, page_title, link_text))
                                else:
                                    skipped_urls.add(normalized_href)
                
                return page_links, valid_count
            
            except Exception as e:
                print(f"❌ Error: {e}")
                return [], 0
        
        # PHASE 1: Quick scan with AI scoring
        print("\n🔍 PHASE 1: AI-powered page scanning...")
        
        while urls_to_visit and len(visited_urls) < max_pages:
            # Sort by current priority
            urls_to_visit.sort(key=lambda x: x[1], reverse=True)
            current_url, priority, page_title, link_text = urls_to_visit.pop(0)
            
            page_links, img_count = quick_scan_page(current_url, priority, page_title, link_text)
            
            # Add new links with metadata
            for link, relevance, title, text in page_links:
                normalized_link = normalize_url(link)
                if not any(normalize_url(u[0]) == normalized_link for u in urls_to_visit):
                    if normalized_link not in visited_urls:
                        urls_to_visit.append((link, relevance, title, text))
        
        # Sort pages by combined score
        page_scores.sort(key=lambda x: x["score"], reverse=True)
        
        print(f"\n✅ Phase 1 complete: Scanned {len(page_scores)} pages")
        
        # Show top 5 candidates with AI scores
        print(f"\n🏆 Top 5 page candidates:")
        for i, page in enumerate(page_scores[:5]):
            ai_info = f" | AI: {page.get('ai_score', 0):.2f}" if use_ai_scoring else ""
            print(f"   {i+1}. Score: {page['score']:.2f} (context: {page.get('context_score', 0):.2f} + images: {page.get('image_score', 0):.2f}{ai_info})")
            print(f"      Priority: {page['priority']:.2f} | ~{page['estimated_images']} images")
            print(f"      Title: {page.get('page_title', 'N/A')[:60]}")
            print(f"      {page['url']}")
        
        if not page_scores:
            return {
                "status": "error",
                "message": "No valid pages found",
                "pages_visited": len(visited_urls),
                "pages_skipped": len(skipped_urls)
            }
        
        # Select best page
        best_page = page_scores[0]
        
        print(f"\n🎯 PHASE 2: Deep scraping best page...")
        print(f"   URL: {best_page['url']}")
        print(f"   Score: {best_page['score']:.2f}")
        if use_ai_scoring:
            print(f"   AI Score: {best_page.get('ai_score', 0):.2f}")
        print(f"   Estimated images: {best_page['estimated_images']}")
        
        # PHASE 2: Deep scrape (same as before)
        def deep_scrape_page(url):
            """PHASE 2: Full image extraction with validation"""
            try:
                print(f"\n📥 Downloading images from: {url}")
                
                response = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                page_images = []
                
                # Strategy 1: <img> tags
                for img in soup.find_all('img'):
                    img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
                    
                    if not img_url and img.get('srcset'):
                        srcset = img.get('srcset').split(',')
                        if srcset:
                            img_url = srcset[-1].strip().split(' ')[0]
                    
                    if img_url:
                        page_images.append(img_url)
                
                # Strategy 2: Background images
                for elem in soup.find_all(style=True):
                    style = elem.get('style', '')
                    if 'background-image' in style or 'background:' in style:
                        import re
                        urls = re.findall(r'url\(["\']?([^"\')]+)["\']?\)', style)
                        page_images.extend(urls)
                
                # Strategy 3: <source> tags
                for source in soup.find_all('source'):
                    src = source.get('srcset') or source.get('src')
                    if src:
                        if ',' in src:
                            src = src.split(',')[-1].strip().split(' ')[0]
                        page_images.append(src)
                
                print(f"   Found {len(page_images)} raw image URLs")
                
                # Validate and normalize URLs (with deduplication)
                validated_images = []
                seen_base_urls = set()
                
                for img_url in page_images:
                    # Convert to absolute URL
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = urljoin(url.split('#')[0], img_url)
                    elif not img_url.startswith('http'):
                        img_url = urljoin(url.split('#')[0], img_url)
                    
                    img_lower = img_url.lower()
                    
                    # Skip bad patterns
                    if any(bad in img_lower for bad in ['favicon', 'sprite', 'spacer', '1x1', 'logo', 'icon', 'banner']):
                        continue
                    
                    if not img_url.startswith('http') or not is_valid_image_url(img_url):
                        continue
                    
                    # DEDUPLICATION
                    import re
                    base_url = img_url
                    base_url = re.sub(r'-\d+x\d+\.(jpg|jpeg|png|webp|gif)', r'.\1', base_url, flags=re.IGNORECASE)
                    base_url = re.sub(r'_(thumb|thumbnail|small|medium|large)\.(jpg|jpeg|png|webp|gif)', r'.\2', base_url, flags=re.IGNORECASE)
                    base_url = re.sub(r'-scaled\.(jpg|jpeg|png|webp|gif)', r'.\1', base_url, flags=re.IGNORECASE)
                    
                    if base_url in seen_base_urls:
                        continue
                    
                    seen_base_urls.add(base_url)
                    validated_images.append(img_url)
                
                print(f"   ✅ Validated: {len(validated_images)} unique high-quality images")
                
                return validated_images
            
            except Exception as e:
                print(f"❌ Error deep scraping: {e}")
                return []
        
        # Deep scrape the winner
        final_images = deep_scrape_page(best_page["url"])
        
        print(f"\n✅ FINAL RESULTS:")
        print(f"   Pages scanned: {len(page_scores)}")
        print(f"   Pages skipped: {len(skipped_urls)}")
        print(f"   Best page: {best_page['url']}")
        print(f"   Images collected: {len(final_images)}")
        
        return {
            "status": "success",
            "website": website,
            "context": context,
            "optimization": "AI-powered URL scoring + two-phase scraping",
            "ai_scoring_enabled": use_ai_scoring,
            "phase_1": {
                "pages_scanned": len(page_scores),
                "pages_skipped": len(skipped_urls),
                "top_5_candidates": page_scores[:5]
            },
            "phase_2": {
                "best_page": best_page,
                "images_downloaded": len(final_images)
            },
            "total_images": len(final_images),
            "images": final_images,
            "best_page_url": best_page["url"]
        }
    
    except Exception as e:
        print(f"❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "status": "error",
            "message": str(e),
            "pages_scanned": len(page_scores) if page_scores else 0
        }


@app.get("/scrape-website-images-js")
def scrape_website_images_with_js(
    website: str = Query(..., description="Website URL"),
    max_pages: int = Query(50, description="Maximum pages to scrape"),
    max_images: int = Query(200, description="Maximum images to collect"),
    wait_time: int = Query(3, description="Seconds to wait for JS content to load"),
    context: str = Query("interior", description="Context for smart URL filtering"),
    min_images_per_page: int = Query(5, description="Stop if page has enough good images")
):
    """
    Scrapes images using Selenium with SMART early stopping
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        driver = webdriver.Chrome(options=chrome_options)
        
        visited_urls = set()
        skipped_urls = set()
        images_found = set()
        urls_to_visit = [(website, 1.0)]
        base_domain = urlparse(website.split('#')[0]).netloc
        
        best_page = {"url": None, "images": 0, "priority": 0}
        
        def normalize_url(url):
            return url.split('#')[0].rstrip('/')
        
        def scrape_with_selenium(url, priority):
            normalized = normalize_url(url)
            
            if normalized in visited_urls:
                return [], [], 0
            
            visited_urls.add(normalized)
            
            try:
                print(f"🔍 Loading [{len(visited_urls)}/{max_pages}]: {url}")
                print(f"   Priority: {priority:.2f} | Context: '{context}'")
                
                driver.get(url)
                time.sleep(wait_time)
                
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.TAG_NAME, "img"))
                    )
                except:
                    pass
                
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                page_images = []
                for img in soup.find_all('img'):
                    img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    
                    if not img_url and img.get('srcset'):
                        srcset = img.get('srcset').split(',')
                        if srcset:
                            img_url = srcset[-1].strip().split(' ')[0]
                    
                    if img_url:
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            img_url = urljoin(url.split('#')[0], img_url)
                        elif not img_url.startswith('http'):
                            img_url = urljoin(url.split('#')[0], img_url)
                        
                        img_lower = img_url.lower()
                        if all([
                            '.svg' not in img_lower,
                            'logo' not in img_lower,
                            'icon' not in img_lower,
                            'sprite' not in img_lower,
                            'placeholder' not in img_lower,
                            'favicon' not in img_lower,
                            'banner' not in img_lower,
                            img_url.startswith('http'),
                            is_valid_image_url(img_url)
                        ]):
                            page_images.append(img_url)
                
                quality_score = len(page_images)
                print(f"   ✅ Found {quality_score} valid images")
                
                if quality_score > best_page["images"]:
                    best_page = {"url": url, "images": quality_score, "priority": priority}
                    print(f"   🏆 NEW BEST PAGE!")
                
                # Early stop check
                if quality_score >= min_images_per_page:
                    print(f"   ✨ EARLY STOP: Excellent page found!")
                    return page_images, [], quality_score
                
                # Find relevant links
                page_links = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    if href.startswith('/'):
                        href = urljoin(url.split('#')[0], href)
                    elif href.startswith('#'):
                        continue
                    elif not href.startswith('http'):
                        href = urljoin(url.split('#')[0], href)
                    
                    parsed = urlparse(href.split('#')[0])
                    if parsed.netloc == base_domain:
                        normalized_href = normalize_url(href)
                        if normalized_href not in visited_urls and normalized_href not in skipped_urls:
                            if not any(ext in href.lower() for ext in ['.pdf', '.doc', '.zip', '.xml']):
                                should_visit, relevance = should_visit_url_for_context(href, context)
                                
                                if should_visit:
                                    page_links.append((href, relevance))
                                else:
                                    skipped_urls.add(normalized_href)
                
                return page_images, page_links, quality_score
            
            except Exception as e:
                print(f"❌ Error: {e}")
                return [], [], 0
        
        # Priority-based traversal with early stopping
        early_stop = False
        
        while urls_to_visit and len(visited_urls) < max_pages and not early_stop:
            urls_to_visit.sort(key=lambda x: x[1], reverse=True)
            
            current_url, priority = urls_to_visit.pop(0)
            
            page_images, page_links, quality_score = scrape_with_selenium(current_url, priority)
            
            for img in page_images:
                images_found.add(img)
            
            if priority >= 0.8 and quality_score >= min_images_per_page:
                early_stop = True
                print(f"\n🎯 STOPPING: Found excellent page!")
                break
            
            if not early_stop:
                for link, relevance in page_links:
                    normalized_link = normalize_url(link)
                    if not any(normalize_url(u[0]) == normalized_link for u in urls_to_visit):
                        if normalized_link not in visited_urls:
                            urls_to_visit.append((link, relevance))
        
        driver.quit()
        
        print(f"\n✅ FINAL: {len(visited_urls)} pages | {len(images_found)} images | {len(skipped_urls)} skipped")
        
        return {
            "status": "success",
            "website": website,
            "context": context,
            "method": "selenium",
            "pages_visited": len(visited_urls),
            "pages_skipped": len(skipped_urls),
            "total_images": len(images_found),
            "images": list(images_found),
            "best_page": best_page,
            "early_stopped": early_stop
        }
    
    except Exception as e:
        try:
            driver.quit()
        except:
            pass
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/filter-images")
def filter_images_by_ai(
    website: str = Query(..., description="Website URL"),
    context: str = Query(..., description="What are you looking for?"),
    max_pages: int = Query(50, description="Maximum pages to scrape"),
    max_images: int = Query(200, description="Maximum images to collect"),
    use_js: bool = Query(False, description="Use JavaScript rendering"),
    min_images_per_page: int = Query(5, description="Stop if page has enough good images")  # ← ADD THIS
):
    """
    Scrapes ALL images from ALL pages and rates them with GPT
    """
    if use_js:
        scrape_result = scrape_website_images_with_js(
            website=website,
            max_pages=max_pages,
            max_images=max_images,
            wait_time=3,
            context=context,
            min_images_per_page=min_images_per_page  # ← ADD THIS
        )
    else:
        scrape_result = scrape_website_images(
            website=website,
            max_pages=max_pages,
            max_images=max_images,
            context=context,
            min_images_per_page=min_images_per_page  # ← ADD THIS
        )
    
    if scrape_result.get("status") != "success":
        return scrape_result
    
    all_images = scrape_result.get("images", [])
    
    if not all_images:
        return {
            "status": "error",
            "message": "No images found on the website",
            "debug_info": {
                "pages_visited": scrape_result.get("pages_visited", 0),
                "visited_urls": scrape_result.get("visited_urls", [])
            }
        }
    
    print(f"📦 Total images scraped: {len(all_images)}")
    print(f"🔗 Sample images: {all_images[:3]}")
    
    # Filter out small images and logos
    valid_images = []
    for img_url in all_images:
        img_lower = img_url.lower()
        
        skip_patterns = [
            'logo', 'icon', 'sprite', 'favicon', 'banner', 'badge',
            'thumb', 'thumbnail', 'avatar', 'profile', 'social',
            'button', 'arrow', 'star', 'rating', 'flag'
        ]
        
        if any(pattern in img_lower for pattern in skip_patterns):
            continue
        
        good_patterns = [
            'gallery', 'photo', 'image', 'img', 'content', 'food',
            'dish', 'menu', 'interior', 'restaurant', 'product'
        ]
        
        has_good_pattern = any(pattern in img_lower for pattern in good_patterns)
        has_size_indicator = any(size in img_lower for size in ['large', 'full', 'original', 'medium'])
        
        if has_good_pattern or has_size_indicator:
            valid_images.append(img_url)
            continue
        
        if not any(pattern in img_lower for pattern in skip_patterns):
            valid_images.append(img_url)
    
    print(f"✅ Valid images after filtering: {len(valid_images)}")
    
    if not valid_images:
        valid_images = all_images[:10]
    
    # LIMIT images sent to GPT to avoid token limits
    images_to_rate = valid_images[:50]  # ← Only send 50 images max
    print(f"📤 Sending {len(images_to_rate)} images to GPT for rating")
    
    # Create list for GPT
    image_list = []
    for i, img_url in enumerate(images_to_rate):
        filename = img_url.split('/')[-1].split('?')[0]
        url_parts = img_url.split('/')
        path_hint = '/'.join(url_parts[-3:]) if len(url_parts) >= 3 else filename
        image_list.append(f"{i}: {filename} | Path: .../{path_hint}")
    
    images_text = "\n".join(image_list)
    
    # Ask GPT to rate images
    try:
        rating_response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are an expert at analyzing image URLs to determine their relevance for: "{context}"

Rate each image from 0.0 to 1.0 based on URL analysis.

**IMPORTANT PATTERNS TO RECOGNIZE:**

For "interior" context:
- High scores (0.8-1.0): gallery/, interior/, inside/, room/, decor/, furniture/
- Medium scores (0.5-0.7): photos/, images/, content/
- Low scores (0.0-0.3): logo, icon, exterior, outside, building, facade

For "food" context:
- High scores (0.8-1.0): food-, dish-, menu-, meal-, plate-, cuisine/
- Medium scores (0.5-0.7): gallery/, photos/, restaurant-
- Low scores (0.0-0.3): logo, icon, building, exterior

**File naming patterns:**
- Place names (e.g., "cavango-cajovna-kosice") → Check for context clues
- Generic names (e.g., "IMG_1234", "photo-5") → Medium score (0.5)
- Descriptive names (e.g., "wooden-table", "interior-view") → High score (0.9)
- Technical names (e.g., "d1", "thumb", "banner") → Low score (0.2)

**URL path indicators:**
- /gallery/ → +0.3 bonus
- /interior/ or /inside/ → +0.4 bonus for interior context
- /food/ or /menu/ → +0.4 bonus for food context
- /thumbnail/ or /thumb/ → -0.3 penalty
- /logo/ or /icon/ → score = 0.0

Return ONLY valid JSON:
{{"0": 0.9, "1": 0.7, "2": 0.95}}

Rate ALL {len(images_to_rate)} images."""
                },
                {
                    "role": "user",
                    "content": f"""Context: {context}

Analyze these image URLs and rate their relevance:

{images_text}

Examples for "{context}" context:
- "restaurant-interior-view.jpg" → 1.0 (perfect match)
- "cajovna-kosice-photo.jpg" → 0.7 (location photo, likely interior)
- "logo-brand.png" → 0.0 (not relevant)
- "IMG_5432.jpg" → 0.5 (unknown, could be anything)

Return ONLY JSON with scores for ALL {len(images_to_rate)} images."""
                }
            ],
            temperature=0.2,
            max_tokens=2000
        )
        
        response_text = rating_response.choices[0].message.content.strip()
        print(f"🤖 GPT response (first 300 chars):")
        print(response_text[:300])
        
        # Clean response - remove markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # Remove any trailing commas (invalid JSON)
        response_text = response_text.replace(",}", "}").replace(",]", "]")
        
        # Try to parse JSON
        try:
            ratings = json.loads(response_text)
        except json.JSONDecodeError as json_error:
            print(f"❌ JSON parse error: {json_error}")
            print(f"📝 Raw response:\n{response_text}")
            
            # Fallback: try to extract numbers manually
            import re
            ratings = {}
            matches = re.findall(r'"(\d+)":\s*([\d.]+)', response_text)
            for idx, score in matches:
                try:
                    ratings[idx] = float(score)
                except:
                    pass
            
            if not ratings:
                raise Exception(f"Could not parse GPT response as JSON: {json_error}")
        
        print(f"🎯 GPT rated {len(ratings)} images")
        
        # Create filtered list with ALL valid images
        filtered_images = []
        
        # Add rated images with their scores
        for idx in range(len(images_to_rate)):
            score = ratings.get(str(idx), 0.5)
            
            filtered_images.append({
                "url": images_to_rate[idx],
                "filename": images_to_rate[idx].split('/')[-1].split('?')[0],
                "index": idx,
                "ai_score": float(score),
                "confidence": float(score),
                "description": f"AI relevance: {score:.2f}/1.0"
            })
        
        # Add remaining images (not sent to GPT) with default score
        for idx in range(len(images_to_rate), len(valid_images)):
            filtered_images.append({
                "url": valid_images[idx],
                "filename": valid_images[idx].split('/')[-1].split('?')[0],
                "index": idx,
                "ai_score": 0.3,  # Default low score
                "confidence": 0.3,
                "description": "Not rated (too many images)"
            })
        
        # Sort by AI score (highest first)
        filtered_images.sort(key=lambda x: x["ai_score"], reverse=True)
        
        print(f"📸 Total images in result: {len(filtered_images)}")
        
        top_scores = [f"{img.get('ai_score', 0):.2f}" for img in filtered_images[:3]]
        print(f"🏆 Top 3 scores: {top_scores}")
        
        return {
            "status": "success",
            "website": website,
            "context": context,
            "selection_method": "AI-rated",
            "total_images_found": len(all_images),
            "valid_images_after_filter": len(valid_images),
            "images_rated_by_ai": len(ratings),
            "matched_images": len(filtered_images),
            "filtered_images": filtered_images,
            "top_score": filtered_images[0]["ai_score"] if filtered_images else 0,
            "average_score": sum(img["ai_score"] for img in filtered_images) / len(filtered_images) if filtered_images else 0
        }
        
    except Exception as e:
        print(f"❌ Error with AI rating: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback: return ALL valid images with default scores
        fallback_images = []
        for i in range(len(valid_images)):
            # Give slightly higher scores to images with good patterns
            img_lower = valid_images[i].lower()
            default_score = 0.6 if any(pattern in img_lower for pattern in ['gallery', 'food', 'dish', 'photo', 'image']) else 0.4
            
            fallback_images.append({
                "url": valid_images[i],
                "filename": valid_images[i].split('/')[-1].split('?')[0],
                "index": i,
                "ai_score": default_score,
                "confidence": default_score,
                "description": f"Fallback score: {default_score:.2f} (AI failed)"
            })
        
        # Sort by score
        fallback_images.sort(key=lambda x: x["ai_score"], reverse=True)
        
        return {
            "status": "success",
            "website": website,
            "context": context,
            "selection_method": "fallback (AI failed)",
            "error": str(e),
            "total_images_found": len(all_images),
            "valid_images_after_filter": len(valid_images),
            "matched_images": len(fallback_images),
            "filtered_images": fallback_images
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
        temperature=0.3,
        max_tokens=500
    )
    
    # Get response from GPT
    gpt_response = response.choices[0].message.content
    
    try:  # ← FIX: Use colon instead of {
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
        
    except json.JSONDecodeError as e:  # ← FIX: Use colon
        # If GPT didn't return valid JSON
        return {
            "status": "error",
            "message": "Failed to parse GPT response",
            "raw_response": gpt_response,
            "error": str(e)
        }
    except Exception as e:  # ← FIX: Use colon
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

@app.get("/search-places-with-images")
def search_places_with_images(
    request: str = Query(..., description="User's natural language request"),
    lat: float = Query(48.7164, description="Latitude"),
    lon: float = Query(21.2611, description="Longitude"),
    radius: int = Query(500, description="Search radius in meters"),
    limit: int = Query(5, description="Max number of places"),
    images_per_place: int = Query(3, description="Max images per place")
):
    """
    🎯 MAIN ENDPOINT: Parse request → Find places → Get images for each place
    
    Process:
    1. Parse user request with GPT (extract activity type, place types, preferences)
    2. Search for places using places_api
    3. For each place, scrape images from their website
    4. Return places with descriptions and images
    """
    try:
        print(f"\n{'='*60}")
        print(f"🔍 SMART SEARCH REQUEST")
        print(f"{'='*60}")
        print(f"Request: {request}")
        print(f"Location: ({lat}, {lon})")
        print(f"Radius: {radius}m")
        
        # STEP 1: Parse request with GPT
        print(f"\n📝 STEP 1: Parsing request with GPT...")
        
        parse_response = openai.chat.completions.create(
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
    "wheelchair_accessible": boolean or null,
    "outdoor_seating": boolean or null,
    "dog_friendly": boolean or null
  },
  "search_context": "short description for image search (e.g., 'restaurant interior', 'museum exhibits', 'park landscape')"
}

Only return valid JSON, nothing else."""
                },
                {"role": "user", "content": request}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        gpt_response = parse_response.choices[0].message.content
        parsed_data = json.loads(gpt_response)
        
        print(f"✅ Parsed data:")
        print(f"   Activity: {parsed_data.get('activity_type')}")
        print(f"   Place types: {parsed_data.get('place_types')}")
        print(f"   Search context: {parsed_data.get('search_context')}")
        
        # STEP 2: Search for places
        print(f"\n📍 STEP 2: Searching for places...")
        
        place_types = parsed_data.get("place_types", ["restaurant"])
        all_places = []
        
        for place_type in place_types[:3]:  # Max 3 types to avoid long searches
            print(f"   Searching for: {place_type}")
            places = search_places(
                lat=lat,
                lon=lon,
                radius=radius,
                place_type=place_type,
                limit=limit,
                use_google=False  # Use only free APIs
            )
            all_places.extend(places)
        
        # Remove duplicates
        unique_places = []
        seen_names = set()
        
        for place in all_places:
            if place["name"] not in seen_names:
                seen_names.add(place["name"])
                unique_places.append(place)
        
        # Sort by rating
        def get_rating(place):
            rating = place.get("rating", "N/A")
            try:
                return float(rating)
            except:
                return 0
        
        unique_places.sort(key=get_rating, reverse=True)
        unique_places = unique_places[:limit]
        
        print(f"✅ Found {len(unique_places)} unique places")
        
        # STEP 3: Get images for each place
        print(f"\n🖼️ STEP 3: Getting images for each place...")
        
        search_context = parsed_data.get("search_context", "interior photos")
        results = []
        
        for i, place in enumerate(unique_places):
            print(f"\n   [{i+1}/{len(unique_places)}] Processing: {place['name']}")
            
            place_result = {
                "place_info": place,
                "images": [],
                "image_search_method": "unknown"
            }
            
            # Strategy 1: Try to scrape from website if available
            if place.get("website") and place["website"] != "N/A":
                print(f"      🌐 Found website: {place['website']}")
                
                try:
                    # Use existing scrape function
                    scrape_result = scrape_website_images(
                        website=place["website"],
                        max_pages=5,  # Quick search
                        max_images=20,
                        context=search_context,
                        min_images_per_page=3,
                        use_ai_scoring=False  # Faster without AI
                    )
                    
                    if scrape_result.get("status") == "success":
                        scraped_images = scrape_result.get("images", [])
                        
                        if scraped_images:
                            print(f"      ✅ Scraped {len(scraped_images)} images from website")
                            
                            # Filter and rate images with GPT
                            if len(scraped_images) > 0:
                                # Take top images
                                top_images = scraped_images[:images_per_place * 2]
                                
                                # Rate with GPT
                                try:
                                    rating_prompt = f"""Rate these images (0.0-1.0) for context: "{search_context}" at place "{place['name']}"

Images (by index):
{chr(10).join([f"{idx}: {img}" for idx, img in enumerate(top_images)])}

Return JSON: {{"image_index": score, ...}}
Only return relevant images (score > 0.5)."""

                                    rating_response = openai.chat.completions.create(
                                        model="gpt-3.5-turbo",
                                        messages=[
                                            {"role": "system", "content": "You rate image relevance. Return only JSON."},
                                            {"role": "user", "content": rating_prompt}
                                        ],
                                        temperature=0.2,
                                        max_tokens=500
                                    )
                                    
                                    ratings = json.loads(rating_response.choices[0].message.content)
                                    
                                    # Select top rated images
                                    rated_images = []
                                    for idx_str, score in ratings.items():
                                        idx = int(idx_str)
                                        if idx < len(top_images) and score > 0.5:
                                            rated_images.append({
                                                "url": top_images[idx],
                                                "confidence": score,
                                                "source": "website"
                                            })
                                    
                                    rated_images.sort(key=lambda x: x["confidence"], reverse=True)
                                    place_result["images"] = rated_images[:images_per_place]
                                    place_result["image_search_method"] = "website_scraping"
                                    
                                    print(f"      ⭐ Selected {len(place_result['images'])} top rated images")
                                
                                except Exception as e:
                                    print(f"      ⚠️ Rating failed: {e}")
                                    # Fallback: just take first N images
                                    place_result["images"] = [
                                        {"url": img, "confidence": 0.7, "source": "website"}
                                        for img in scraped_images[:images_per_place]
                                    ]
                                    place_result["image_search_method"] = "website_scraping_unrated"
                        
                except Exception as e:
                    print(f"      ❌ Website scraping failed: {e}")
            
            # Strategy 2: If no website or scraping failed, try Google Image Search
            if not place_result["images"]:
                print(f"      🔍 Trying Google Image Search...")
                
                try:
                    search_query = f"{place['name']} {search_context}"
                    
                    google_result = get_place_images_from_google(
                        place_name=place["name"],
                        location=f"{lat},{lon}",
                        use_mock=False
                    )
                    
                    if google_result.get("status") == "success":
                        google_images = google_result.get("images", [])
                        
                        if google_images:
                            place_result["images"] = [
                                {
                                    "url": img["url"],
                                    "confidence": 0.6,
                                    "source": "google_images",
                                    "title": img.get("title", "")
                                }
                                for img in google_images[:images_per_place]
                            ]
                            place_result["image_search_method"] = "google_images"
                            print(f"      ✅ Found {len(place_result['images'])} images from Google")
                
                except Exception as e:
                    print(f"      ❌ Google search failed: {e}")
            
            # Strategy 3: Fallback - generate placeholder
            if not place_result["images"]:
                print(f"      ⚠️ No images found, using placeholder")
                place_result["images"] = [{
                    "url": f"https://via.placeholder.com/400x300?text={place['name'].replace(' ', '+')}",
                    "confidence": 0.1,
                    "source": "placeholder"
                }]
                place_result["image_search_method"] = "placeholder"
            
            results.append(place_result)
        
        print(f"\n{'='*60}")
        print(f"✅ SEARCH COMPLETE")
        print(f"{'='*60}")
        print(f"Found {len(results)} places with images")
        
        return {
            "status": "success",
            "request": request,
            "parsed_context": parsed_data,
            "location": {"lat": lat, "lon": lon, "radius": radius},
            "total_places": len(results),
            "places": results,
            "optimization_notes": [
                "Used free APIs (OpenStreetMap)",
                "Scraped images from place websites when available",
                "Fallback to Google Image Search if needed",
                "AI-rated images for relevance"
            ]
        }
    
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "message": "Failed to parse GPT response",
            "error": str(e)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }

