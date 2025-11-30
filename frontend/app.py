import streamlit as st
import requests
from PIL import Image
from io import BytesIO
from datetime import datetime
import base64

# Backend URL
BACKEND_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Place Image Finder",
    page_icon="🏛️",
    layout="wide"
)

st.title("🏛️ Place Image Finder")
st.markdown("Find images of places from websites or Google search")

# Sidebar for options
st.sidebar.header("Search Options")

search_mode = st.sidebar.radio(
    "Search Mode:",
    ["By Website", "By Place Name", "Smart Request", "💬 AI Chat Assistant"]
)

# Initialize session state for chat
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if 'last_parsed_context' not in st.session_state:
    st.session_state.last_parsed_context = None


def load_image_with_referer(img_url, website_url):
    """
    Load image with proper headers to bypass hotlink protection
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": website_url,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    try:
        response = requests.get(img_url, headers=headers, timeout=15, allow_redirects=True)
        
        # Check content type
        content_type = response.headers.get('content-type', '').lower()
        
        if 'image' not in content_type:
            return None, f"Not an image: {content_type}"
        
        # Try to open image
        img = Image.open(BytesIO(response.content))
        
        # Skip very small images
        if img.size[0] < 100 or img.size[1] < 100:
            return None, f"Too small: {img.size[0]}x{img.size[1]}px"
        
        return img, None
    
    except requests.exceptions.Timeout:
        return None, "Timeout"
    except requests.exceptions.RequestException as e:
        return None, f"Network error: {str(e)}"
    except Exception as e:
        return None, f"Error: {str(e)}"


# Main content
if search_mode == "By Website":
    st.header("🌐 Search by Website")
    
    col1, col2 = st.columns(2)
    
    with col1:
        website = st.text_input("Website URL", placeholder="https://example.com")
        context = st.text_input("Context", value="main photo", placeholder="e.g., bar atmosphere, food")
    
    with col2:
        max_pages = st.slider("Max pages to scrape", 1, 100, 50)
        max_images = st.slider("Max images", 10, 500, 200)
    
    use_js = st.checkbox("Use JavaScript rendering (for dynamic content)", value=False)
    
    if st.button("🔍 Search Images", type="primary"):
        if website:
            with st.spinner("Searching images..."):
                try:
                    response = requests.get(
                        f"{BACKEND_URL}/filter-images",
                        params={
                            "website": website,
                            "context": context,
                            "max_pages": max_pages,
                            "max_images": max_images,
                            "use_js": use_js
                        },
                        timeout=120
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get("status") == "success":
                            matched = data.get("matched_images", 0)
                            st.success(f"✅ Found {matched} relevant images")
                            
                            # Debug info
                            with st.expander("🔍 Debug Info"):
                                st.write(f"Total scraped: {data.get('total_images_found', 0)}")
                                st.write(f"Valid after filter: {data.get('valid_images_after_filter', 0)}")
                                st.write(f"Final matched: {matched}")
                                st.write(f"Selection method: {data.get('selection_method', 'unknown')}")
                            
                            # Display images
                            filtered_images = data.get("filtered_images", [])
                            
                            if filtered_images:
                                st.markdown(f"### 🖼️ Top {len(filtered_images)} Images")
                                
                                # Display in grid
                                cols = st.columns(3)
                                
                                images_displayed = 0
                                errors_summary = {}
                                
                                for idx, img_data in enumerate(filtered_images):
                                    img_url = img_data.get("url")
                                    
                                    if not img_url:
                                        continue
                                    
                                    # Skip obvious tracking pixels
                                    if any(skip in img_url.lower() for skip in [
                                        'facebook.com/tr', 'google-analytics', 'pixel', 
                                        'tracking', 'tr?id', 'noscript', '1x1.gif'
                                    ]):
                                        continue
                                    
                                    # Try to load image with proper headers
                                    img, error = load_image_with_referer(img_url, website)
                                    
                                    if img:
                                        # Display in column
                                        with cols[images_displayed % 3]:
                                            st.image(img, use_container_width=True)
                                            
                                            # Show metadata
                                            st.caption(f"**{img_data.get('filename', 'Unknown')}**")
                                            st.caption(f"Confidence: {img_data.get('confidence', 0):.2f} | {img_data.get('description', '')}")
                                            st.caption(f"Size: {img.size[0]}x{img.size[1]}px")
                                            
                                            # Show URL in expander
                                            with st.expander("🔗 Image URL"):
                                                st.code(img_url, language=None)
                                        
                                        images_displayed += 1
                                    else:
                                        # Track errors
                                        error_type = error.split(':')[0] if error else "Unknown"
                                        errors_summary[error_type] = errors_summary.get(error_type, 0) + 1
                                
                                # Show results summary
                                st.markdown("---")
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    if images_displayed > 0:
                                        st.success(f"✅ Successfully displayed **{images_displayed}** images")
                                    else:
                                        st.error("❌ Could not display any images")
                                
                                with col2:
                                    if errors_summary:
                                        with st.expander("⚠️ Errors encountered"):
                                            for error_type, count in errors_summary.items():
                                                st.write(f"- {error_type}: {count}")
                                
                                if images_displayed == 0:
                                    st.info("💡 **Suggestions:**\n"
                                           "- Try enabling 'Use JavaScript rendering'\n"
                                           "- The website may have hotlink protection\n"
                                           "- Try a different website")
                            else:
                                st.warning("No images were filtered from the results")
                        
                        else:
                            error_msg = data.get('message', 'Unknown error')
                            st.error(f"❌ Error: {error_msg}")
                            
                            # Show debug info if available
                            if data.get('debug_info'):
                                with st.expander("🔍 Debug Info"):
                                    st.json(data['debug_info'])
                    else:
                        st.error(f"❌ Backend error: HTTP {response.status_code}")
                
                except requests.exceptions.Timeout:
                    st.error("⏱️ Request timeout. The website may be slow or blocking requests.")
                except requests.exceptions.ConnectionError:
                    st.error("🌐 Connection error. Make sure the backend is running on http://127.0.0.1:8000")
                except Exception as e:
                    st.error(f"❌ Unexpected error: {str(e)}")
        else:
            st.warning("⚠️ Please enter a website URL")

elif search_mode == "By Place Name":
    st.header("📍 Search by Place Name")
    
    col1, col2 = st.columns(2)
    
    with col1:
        place_name = st.text_input("Place Name", placeholder="e.g., Singing Fountain")
        location = st.text_input("Location (optional)", placeholder="e.g., Košice")
    
    with col2:
        max_results = st.slider("Max results", 3, 10, 5)
        use_mock = st.checkbox("Use mock data (for testing)", value=False)
    
    if st.button("🔍 Search Images", type="primary"):
        if place_name:
            with st.spinner("Searching images..."):
                response = requests.get(
                    f"{BACKEND_URL}/get-place-images",
                    params={
                        "place_name": place_name,
                        "location": location,
                        "use_mock": use_mock
                    },
                    timeout=60
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "success":
                        source = data.get("source", "unknown")
                        st.success(f"✅ Found images from: **{source}**")
                        
                        images = data.get("images", [])
                        
                        if images:
                            cols = st.columns(3)
                            for idx, img_data in enumerate(images):
                                with cols[idx % 3]:
                                    try:
                                        if source == "mock_data":
                                            st.image(img_data["url"], caption=img_data["title"], use_container_width=True)
                                        else:
                                            img_url = img_data.get("url")
                                            
                                            if any(skip in img_url.lower() for skip in [
                                                'facebook.com', 'google-analytics', 'pixel', 
                                                'tracking', 'tr?', 'noscript'
                                            ]):
                                                continue
                                            
                                            img_response = requests.get(img_url, timeout=10, headers={
                                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                            })
                                            
                                            content_type = img_response.headers.get('content-type', '')
                                            if 'image' not in content_type:
                                                continue
                                            
                                            img = Image.open(BytesIO(img_response.content))
                                            
                                            if img.size[0] < 50 or img.size[1] < 50:
                                                continue
                                            
                                            st.image(img, caption=img_data.get("title", "Image"), use_container_width=True)
                                    except:
                                        pass
                        else:
                            st.warning("No images found")
                    else:
                        st.error(f"Error: {data.get('message')}")
                        if data.get("fallback"):
                            st.info(data.get("fallback"))
                else:
                    st.error(f"Backend error: {response.status_code}")
        else:
            st.warning("Please enter a place name")

elif search_mode == "Smart Request":
    st.header("🤖 Smart Request")
    
    request_text = st.text_area(
        "Describe what you're looking for:",
        placeholder="e.g., Find a cozy bar in Košice with good atmosphere",
        height=100
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        lat = st.number_input("Latitude", value=48.7164, format="%.4f")
        lon = st.number_input("Longitude", value=21.2611, format="%.4f")
    
    with col2:
        radius = st.slider("Search radius (meters)", 100, 2000, 500)
    
    if st.button("🔍 Smart Search", type="primary"):
        if request_text:
            with st.spinner("Processing your request..."):
                parse_response = requests.get(
                    f"{BACKEND_URL}/request",
                    params={"request": request_text},
                    timeout=30
                )
                
                if parse_response.status_code == 200:
                    parse_data = parse_response.json()
                    
                    if parse_data.get("status") == "success":
                        st.success("✅ Request parsed successfully")
                        
                        parsed = parse_data.get("parsed_data", {})
                        
                        with st.expander("📋 Parsed Information", expanded=True):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("**Activity Type:**", parsed.get("activity_type", "N/A"))
                                st.write("**Place Types:**", ", ".join(parsed.get("place_types", [])))
                            with col2:
                                st.write("**Cuisine:**", parsed.get("cuisine", "N/A"))
                                st.write("**Budget:**", parsed.get("preferences", {}).get("budget", "N/A"))
                        
                        st.info("🚧 Full smart search with places coming soon!")
                    else:
                        st.error(f"Error parsing request: {parse_data.get('message')}")
                else:
                    st.error(f"Backend error: {parse_response.status_code}")
        else:
            st.warning("Please enter a request")

else:  # AI Chat Assistant
    st.header("💬 AI Chat Assistant")
    st.markdown("Tell me what you're looking for, and I'll help you understand your request!")
    
    # Quick suggestions
    st.markdown("### 💡 Try these:")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🍕 Find Italian restaurant", use_container_width=True):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "I want to find a good Italian restaurant in Košice"
            })
            st.rerun()
    
    with col2:
        if st.button("🍵 Tea house with photos", use_container_width=True):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "Show me photos of tea houses with good interior"
            })
            st.rerun()
    
    with col3:
        if st.button("🏛️ Museum visit", use_container_width=True):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "I want to visit a museum with wheelchair access"
            })
            st.rerun()
    
    st.markdown("---")
    
    # Chat messages display
    chat_container = st.container()
    
    with chat_container:
        for idx, message in enumerate(st.session_state.chat_history):
            if message["role"] == "user":
                with st.chat_message("user", avatar="👤"):
                    st.markdown(message["content"])
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(message["content"])
                    
                    # Show parsed context if available
                    if "parsed_context" in message:
                        with st.expander("📊 Understood Context", expanded=True):
                            parsed = message["parsed_context"]
                            
                            # Activity Type
                            if parsed.get("activity_type"):
                                st.info(f"**🎯 Activity:** {parsed['activity_type']}")
                            
                            # Place Types
                            if parsed.get("place_types"):
                                st.success(f"**📍 Looking for:** {', '.join(parsed['place_types'])}")
                            
                            # Cuisine
                            if parsed.get("cuisine"):
                                st.warning(f"**🍽️ Cuisine:** {parsed['cuisine']}")
                            
                            # Location
                            location = parsed.get("location", {})
                            if location.get("city"):
                                st.info(f"**📌 Location:** {location['city']}")
                            
                            # Preferences
                            prefs = parsed.get("preferences", {})
                            if any(prefs.values()):
                                st.markdown("**⚙️ Preferences:**")
                                pref_cols = st.columns(3)
                                col_idx = 0
                                
                                if prefs.get("budget"):
                                    with pref_cols[col_idx % 3]:
                                        st.caption(f"💰 Budget: {prefs['budget']}")
                                    col_idx += 1
                                
                                if prefs.get("rating_min"):
                                    with pref_cols[col_idx % 3]:
                                        st.caption(f"⭐ Min rating: {prefs['rating_min']}")
                                    col_idx += 1
                                
                                if prefs.get("wheelchair_accessible"):
                                    with pref_cols[col_idx % 3]:
                                        st.caption("♿ Wheelchair accessible")
                                    col_idx += 1
                                
                                if prefs.get("outdoor_seating"):
                                    with pref_cols[col_idx % 3]:
                                        st.caption("🌳 Outdoor seating")
                                    col_idx += 1
                                
                                if prefs.get("dog_friendly"):
                                    with pref_cols[col_idx % 3]:
                                        st.caption("🐕 Dog friendly")
                                    col_idx += 1
                            

                            # Additional notes
                            if parsed.get("additional_notes"):
                                st.markdown(f"**📝 Notes:** {parsed['additional_notes']}")
                            

                            # Action button
                            st.markdown("---")
                            if st.button(f"🔍 Search for these places", key=f"search_{idx}"):
                                st.info("🚧 Search functionality coming soon! For now, use the parsed context above.")
    
    # Chat input
    st.markdown("---")
    user_message = st.chat_input("💬 Tell me what you're looking for...")
    
    if user_message:
        # Add user message to history
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Send to backend for parsing
        with st.spinner("🤔 Understanding your request..."):
            try:
                response = requests.get(
                    f"{BACKEND_URL}/request",
                    params={"request": user_message},
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "success":
                        parsed = data.get("parsed_data", {})
                        
                        # Create friendly response
                        response_parts = ["Great! I understand you're looking for:\n"]
                        
                        if parsed.get("activity_type"):
                            response_parts.append(f"- **Activity type:** {parsed['activity_type']}")
                        
                        if parsed.get("place_types"):
                            places = ", ".join(parsed['place_types'])
                            response_parts.append(f"- **Places:** {places}")
                        
                        if parsed.get("cuisine"):
                            response_parts.append(f"- **Cuisine:** {parsed['cuisine']}")
                        
                        location = parsed.get("location", {})
                        if location.get("city"):
                            response_parts.append(f"- **Location:** {location['city']}")
                        
                        prefs = parsed.get("preferences", {})
                        pref_list = []
                        if prefs.get("budget"):
                            pref_list.append(f"{prefs['budget']} budget")
                        if prefs.get("wheelchair_accessible"):
                            pref_list.append("wheelchair accessible")
                        if prefs.get("outdoor_seating"):
                            pref_list.append("outdoor seating")
                        if prefs.get("dog_friendly"):
                            pref_list.append("dog friendly")
                        
                        if pref_list:
                            response_parts.append(f"- **Preferences:** {', '.join(pref_list)}")
                        
                        if parsed.get("additional_notes"):
                            response_parts.append(f"- **Additional notes:** {parsed['additional_notes']}")
                        
                        response_parts.append("\n\n✅ I've extracted this information from your request. You can use the 'Search for these places' button above to find matching locations!")
                        
                        friendly_response = "\n".join(response_parts)
                        
                        # Add assistant response with parsed context
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": friendly_response,
                            "parsed_context": parsed
                        })
                        
                        # Save last context
                        st.session_state.last_parsed_context = parsed
                        
                    else:
                        # Fallback to general answer endpoint
                        answer_response = requests.get(
                            f"{BACKEND_URL}/answer",
                            params={"question": user_message},
                            timeout=30
                        )
                        
                        if answer_response.status_code == 200:
                            answer_data = answer_response.json()
                            answer_text = answer_data.get("answer", "I'm not sure how to help with that.")
                            
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": answer_text
                            })
                        else:
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": "I'm having trouble processing your request. Could you rephrase it?"
                            })
                else:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"❌ Backend error: HTTP {response.status_code}"
                    })
            
            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"❌ Error: {str(e)}\n\nPlease try again or rephrase your request."
                })
        
        st.rerun()
    
    # Clear chat button
    if st.session_state.chat_history:
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🗑️ Clear chat", type="secondary", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.last_parsed_context = None
                st.rerun()
    
    # Sidebar with last context
    if st.session_state.last_parsed_context:
        with st.sidebar:
            st.markdown("---")
            st.markdown("### 🎯 Last Parsed Context")
            
            parsed = st.session_state.last_parsed_context
            
            if parsed.get("activity_type"):
                st.caption(f"**Activity:** {parsed['activity_type']}")
            
            if parsed.get("place_types"):
                st.caption(f"**Places:** {', '.join(parsed['place_types'])}")
            
            if parsed.get("cuisine"):
                st.caption(f"**Cuisine:** {parsed['cuisine']}")
            
            if st.button("📋 Copy context JSON", use_container_width=True):
                import json
                st.code(json.dumps(parsed, indent=2), language="json")

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Backend Status")
try:
    health_check = requests.get(f"{BACKEND_URL}/", timeout=5)
    if health_check.status_code == 200:
        st.sidebar.success("✅ Backend online")
    else:
        st.sidebar.error("❌ Backend error")
except:
    st.sidebar.error("❌ Backend offline")

st.sidebar.markdown("---")
st.sidebar.info("💡 **Tip:** Use the chat to describe what you're looking for naturally!")