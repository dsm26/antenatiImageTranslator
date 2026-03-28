import streamlit as st
import math
import requests
import re
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# --- CONFIGURATION ---
CHOSEN_MODEL = 'gemini-2.5-flash' 
CACHE_TTL = 900 
# Broadened headers to appear more like a standard browser session
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://antenati.cultura.gov.it/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

st.set_page_config(page_title="Antenati Downloader & AI Translator", page_icon="🧬", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []

# --- IMPROVED METADATA FETCHING ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_antenati_metadata(image_id):
    """Tries multiple endpoints to get the archival context."""
    # Attempt 1: The IIIF Manifest (Most detailed)
    try:
        manifest_url = f"https://antenati.cultura.gov.it/iiif/2/{image_id}/manifest"
        resp = requests.get(manifest_url, headers=HEADERS, timeout=7)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("label", "Italian Civil Record")
    except:
        pass

    # Attempt 2: Fallback to the Info.json (Least restrictive)
    try:
        info_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}/info.json"
        resp = requests.get(info_url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            # Info.json doesn't have names, but we can verify it exists
            return "Italian Civil Record (Image Verified)"
    except:
        pass
        
    return "Italian Civil Record (Context unavailable)"

# --- CACHED DOWNLOAD LOGIC ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_stitched_image(image_id):
    base_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}"
    info_resp = requests.get(f"{base_url}/info.json", headers=HEADERS)
    info_resp.raise_for_status()
    info = info_resp.json()
    
    w, h = info["width"], info["height"]
    tw = info["tiles"][0]["width"]
    th = info["tiles"][0].get("height", tw)
    
    final_img = Image.new("RGB", (w, h))
    cols, rows = math.ceil(w / tw), math.ceil(h / th)
    total_tiles = rows * cols
    
    progress_placeholder = st.empty()
    tile_count = 0
    for r in range(rows):
        for c in range(cols):
            tile_count += 1
            x, y = c * tw, r * th
            tile_w, tile_h = min(tw, w - x), min(th, h - y)
            tile_url = f"{base_url}/{x},{y},{tile_w},{tile_h}/full/0/default.jpg"
            progress_placeholder.progress(tile_count / total_tiles, text=f"📥 Downloading tile {tile_count} of {total_tiles}...")
            res = requests.get(tile_url, headers=HEADERS)
            tile_data = Image.open(BytesIO(res.content))
            final_img.paste(tile_data, (x, y))
    
    progress_placeholder.empty()
    buf = BytesIO()
    final_img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

# --- CACHED AI LOGIC ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_ai_analysis(img_bytes, metadata_context, _model_instance):
    prompt = f"""
    CONTEXT FROM ARCHIVE: {metadata_context}
    TASK: Analyze this handwritten 19th-century Italian civil record. 
    1. Identify the record type, primary names (subject, parents), and specific dates.
    2. Provide a full transcription of the handwritten names.
    3. Translate the summary into clear English.
    """
    response = _model_instance.generate_content([
        prompt, 
        {"mime_type": "image/jpeg", "data": img_bytes}
    ])
    return response.text

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ App Management")
    st.write(f"**Model:** {CHOSEN_MODEL}")
    st.write(f"**Cache TTL:** {CACHE_TTL // 60} Minutes")
    
    if st.button("🗑️ Clear Cache & History"):
        st.cache_data.clear()
        st.session_state.history = []
        st.rerun()

    if st.session_state.history:
        st.markdown("---")
        st.header("🕒 Recent History")
        for h_id in reversed(st.session_state.history[-5:]):
            if st.button(f"📄 {h_id}", key=f"hist_{h_id}", use_container_width=True):
                st.query_params["image_id"] = h_id
                st.rerun()

# --- MAIN UI ---
st.title("🏛️ Antenati Downloader & AI Translator")

st.markdown(f"""
💡 **How to use:** Paste a full Antenati URL or Image ID below. <br>
**Example ID:** LzPr8VJ
""", unsafe_allow_html=True)

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(CHOSEN_MODEL)
    
    params = st.query_params
    default_id = params.get("image_id", "")
    raw_input = st.text_input("Paste Antenati URL or Image ID:", value=default_id)
    input_id = raw_input.strip().split('/')[-1] if "/" in raw_input else raw_input.strip()

    if input_id:
        if input_id not in st.session_state.history:
            st.session_state.history.append(input_id)

        try:
            record_meta = get_antenati_metadata(input_id)
            img_data = get_stitched_image(input_id)
            
            st.download_button("📥 Download JPG", img_data, f"{input_id}.jpg", "image/jpeg")
            
            status_area = st.empty()
            status_area.info(f"⏳ AI is analyzing with {CHOSEN_MODEL}. Results will appear below...")

            st.image(img_data, use_container_width=True)
            
            # Metadata Display Box
            st.info(f"**Archival Context:** {record_meta}")

            analysis_text = get_ai_analysis(img_data, record_meta, model)
            
            st.markdown('<div id="findings"></div>', unsafe_allow_html=True)
            st.markdown("---")
            st.subheader("📝 AI Findings")
            st.write(analysis_text)
            st.markdown("---")
            
            status_area.success(f"✅ Analysis complete. [Click here to jump to AI Findings](#findings)")

        except Exception as e:
            st.error(f"Error processing record: {e}")
else:
    st.error("🔑 API Key missing! Add GEMINI_API_KEY to your Streamlit Secrets.")
