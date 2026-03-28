import streamlit as st
import math
import requests
import re
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# --- CONFIGURATION ---
CHOSEN_MODEL = 'gemini-2.5-flash' 

st.set_page_config(page_title="Antenati AI", page_icon="🧬", layout="wide")

# Setup Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(CHOSEN_MODEL)
else:
    st.error("🔑 API Key missing! Add GEMINI_API_KEY to your Streamlit Secrets.")

st.title("🏛️ Antenati AI Downloader & Translator")

# Updated help message with parameter instructions
st.markdown(f"""
💡 **How to use:** Paste a full Antenati URL or Image ID below. Then, use the AI button (powered by **{CHOSEN_MODEL}**) to transcribe and translate the record.
*(Shortcut: You can also pass parameters in the browser URL using `?image_id=...` or `?url=...`)*
""")
st.markdown(f"Example URL - https://antenati.cultura.gov.it/ark:/12657/an_ua264421/LzPr8VJ")
st.markdown(f"Example Image ID - LzPr8VJ)

# --- URL PARAMETER LOGIC ---
params = st.query_params
default_value = ""

# Prioritize 'url' parameter, then 'image_id'
if "url" in params:
    default_value = params["url"]
elif "image_id" in params:
    default_value = params["image_id"]

# Input field (pre-filled if params exist)
raw_input = st.text_input("Paste Antenati URL or Image ID here:", value=default_value)

# Clean input: trim whitespace and remove trailing slashes
input_clean = raw_input.strip().rstrip('/')

def get_image_id(user_input):
    if "antenati.cultura.gov.it" in user_input:
        # Regex looks for the text after the last remaining slash
        match = re.search(r'([^/]+)$', user_input)
        return match.group(1) if match else user_input
    return user_input

image_id = get_image_id(input_clean)

if image_id:
    st.info(f"Stitching image: {image_id}...")
    HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://antenati.cultura.gov.it/"}
    base_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}"
    
    try:
        # --- DOWNLOAD LOGIC ---
        info_resp = requests.get(f"{base_url}/info.json", headers=HEADERS)
        info_resp.raise_for_status()
        info = info_resp.json()
        
        w, h = info["width"], info["height"]
        tw = info["tiles"][0]["width"]
        th = info["tiles"][0].get("height", tw)
        
        final_img = Image.new("RGB", (w, h))
        cols, rows = math.ceil(w / tw), math.ceil(h / th)
        
        my_bar = st.progress(0, text="Downloading tiles...")
        
        for r in range(rows):
            for c in range(cols):
                x, y = c * tw, r * th
                tile_w, tile_h = min(tw, w - x), min(th, h - y)
                tile_url = f"{base_url}/{x},{y},{tile_w},{tile_h}/full/0/default.jpg"
                res = requests.get(tile_url, headers=HEADERS)
                tile_data = Image.open(BytesIO(res.content))
                final_img.paste(tile_data, (x, y))
            my_bar.progress((r + 1) / rows, text=f"Stitching row {r+1} of {rows}...")

        buf = BytesIO()
        final_img.save(buf, format="JPEG", quality=95)
        img_data = buf.getvalue()

        # --- UI LAYOUT ---
        btn_col1, btn_col2 = st.columns([1, 4])
        with btn_col1:
            st.download_button("📥 Download JPG", img_data, f"{image_id}.jpg", "image/jpeg")
        
        if st.button(f"🤖 Analyze & Translate with {CHOSEN_MODEL}"):
            with st.spinner(f"Reading cursive with {CHOSEN_MODEL}..."):
                prompt = """
                Analyze this 1800s Italian civil record. 
                1. Identify the record type, primary names, and dates.
                2. Provide a full transcription of handwritten details.
                3. Translate the summary into clear English.
                """
                response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_data}])
                
                st.markdown("---")
                st.subheader("📝 Findings")
                st.write(response.text)
                st.markdown("---")

        st.image(img_data, use_container_width=True)

    except Exception as e:
        st.error(f"Error processing {image_id}: {e}")
