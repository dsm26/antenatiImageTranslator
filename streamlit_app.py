import streamlit as st
import math
import requests
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# 1. Setup Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    st.warning("⚠️ Gemini API Key not found in Secrets!")

st.set_page_config(page_title="Antenati AI", page_icon="🧬")
st.title("🏛️ Antenati AI Downloader & Translator")

# Grab ID from URL
query_params = st.query_params
url_id = query_params.get("image_id", "")
image_id = st.text_input("Enter IIIF Image ID", value=url_id)

if image_id:
    st.info(f"Stitching image: {image_id}...")
    HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://antenati.cultura.gov.it/"}
    base_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}"
    
    try:
        # --- DOWNLOAD LOGIC ---
        info = requests.get(f"{base_url}/info.json", headers=HEADERS).json()
        w, h = info["width"], info["height"]
        tw = info["tiles"][0]["width"]
        th = info["tiles"][0].get("height", tw)
        
        final_img = Image.new("RGB", (w, h))
        cols, rows = math.ceil(w / tw), math.ceil(h / th)
        
        for r in range(rows):
            for c in range(cols):
                x, y = c * tw, r * th
                tile_w, tile_h = min(tw, w - x), min(th, h - y)
                tile_url = f"{base_url}/{x},{y},{tile_w},{tile_h}/full/0/default.jpg"
                res = requests.get(tile_url, headers=HEADERS)
                tile_data = Image.open(BytesIO(res.content))
                final_img.paste(tile_data, (x, y))

        # --- ACTIONS ---
        buf = BytesIO()
        final_img.save(buf, format="JPEG", quality=95)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📥 Download JPG", buf.getvalue(), f"{image_id}.jpg", "image/jpeg")
        
        with col2:
            if st.button("🤖 AI Analyze & Translate"):
                with st.spinner("Gemini is reading the cursive..."):
                    prompt = "This is an 1800s Italian civil record. Please transcribe the names, dates, and locations, then translate the summary into English."
                    response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": buf.getvalue()}])
                    st.markdown("### 📝 AI Findings")
                    st.write(response.text)

        st.image(buf.getvalue(), use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
