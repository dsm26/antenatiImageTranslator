import streamlit as st
import math
import requests
import re
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# --- CONFIGURATION ---
CHOSEN_MODEL = 'gemini-2.5-flash' 
CACHE_TTL = 900  # 15 minutes in seconds

st.set_page_config(page_title="Antenati AI", page_icon="🧬", layout="wide")

# Setup Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(CHOSEN_MODEL)
else:
    st.error("🔑 API Key missing! Add GEMINI_API_KEY to your Streamlit Secrets.")

# --- CACHED DOWNLOAD LOGIC ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_stitched_image(image_id):
    HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://antenati.cultura.gov.it/"}
    base_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}"
    
    info_resp = requests.get(f"{base_url}/info.json", headers=HEADERS)
    info_resp.raise_for_status()
    info = info_resp.json()
    
    w, h = info["width"], info["height"]
    tw = info["tiles"][0]["width"]
    th = info["tiles"][0].get("height", tw)
    
    final_img = Image.new("RGB", (w, h))
    cols, rows = math.ceil(w / tw), math.ceil(h / th)
    
    my_bar = st.progress(0, text=f"Downloading tiles for {image_id}...")
    
    for r in range(rows):
        for c in range(cols):
            x, y = c * tw, r * th
            tile_w, tile_h = min(tw, w - x), min(th, h - y)
            tile_url = f"{base_url}/{x},{y},{tile_w},{tile_h}/full/0/default.jpg"
            res = requests.get(tile_url, headers=HEADERS)
            tile_data = Image.open(BytesIO(res.content))
            final_img.paste(tile_data, (x, y))
        my_bar.progress((r + 1) / rows, text=f"Stitching row {r+1} of {rows}...")
    
    my_bar.empty()
    
    buf = BytesIO()
    final_img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

# --- CACHED AI LOGIC ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_ai_analysis(img_bytes, _model_instance):
    prompt = """
    Analyze this 1800s Italian civil record. 
    1. Identify the record type, primary names, and dates.
    2. Provide a full transcription of handwritten details.
    3. Translate the summary into clear English.
    """
    response = _model_instance.generate_content([
        prompt, 
        {"mime_type": "image/jpeg", "data": img_bytes}
    ])
    return response.text

# --- UI START ---
st.title("🏛️ Antenati AI Downloader & Translator")

# --- SIDEBAR: CACHE MANAGEMENT ---
with st.sidebar:
    st.header("⚙️ App Management")
    st.write(f"**Model:** {CHOSEN_MODEL}")
    st.write(f"**Cache TTL:** 15 Minutes")
    
    # Simple count of unique Image IDs in the download cache
    try:
        # We access the internal length of the function's cache
        cache_count = len(get_stitched_image.get_stats())
        st.metric("Images in Cache", cache_count)
    except:
        # Fallback if stats are being recalibrated
        st.write("**Cache Status:** Active")

    if st.button("🗑️ Clear App Cache"):
        st.cache_data.clear()
        st.success("Cache cleared!")
        st.rerun()

st.markdown(f"""
💡 **How to use:** Paste a full Antenati URL or Image ID below. The app will automatically download, stitch, and analyze the record.
*(Shortcut: You can also pass parameters in the browser URL using `?image_id=...` or `?url=...`)*
""")

# --- URL PARAMETER LOGIC ---
params = st.query_params
default_value = ""

if "url" in params:
    default_value = params["url"]
elif "image_id" in params:
    default_value = params["image_id"]

raw_input = st.text_input("Paste Antenati URL or Image ID here:", value=default_value)
input_clean = raw_input.strip().rstrip('/')

def get_image_id(user_input):
    if "antenati.cultura.gov.it" in user_input:
        match = re.search(r'([^/]+)$', user_input)
        return match.group(1) if match else user_input
    return user_input

image_id = get_image_id(input_clean)

if image_id:
    try:
        # 1. Automatic Download & Stitch
        img_data = get_stitched_image(image_id)

        # 2. UI Action Bar
        st.download_button("📥 Download JPG", img_data, f"{image_id}.jpg", "image/jpeg")
        
        # 3. AI Status Message
        status_area = st.empty()
        status_area.info(f"⏳ AI is transcribing and translating with {CHOSEN_MODEL}. Results will appear below the image...")

        # 4. Display Image
        st.image(img_data, use_container_width=True)

        # 5. Automatic AI Analysis
        analysis_text = get_ai_analysis(img_data, model)
        
        # 6. Final Results
        st.markdown('<div id="findings"></div>', unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("📝 AI Findings")
        st.write(analysis_text)
        st.markdown("---")
        
        status_area.success(f"✅ Analysis complete using {CHOSEN_MODEL}. [Click here to see AI Findings](#findings)")

    except Exception as e:
        st.error(f"Error processing {image_id}: {e}")
