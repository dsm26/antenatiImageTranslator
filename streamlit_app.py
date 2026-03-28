import streamlit as st
import math
import requests
import re
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# 1. Page Config (Set to Wide for better viewing)
st.set_page_config(page_title="Antenati AI", page_icon="🧬", layout="wide")

# 2. Setup Gemini (Using 1.5 Flash for reliable free quota)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    st.error("🔑 API Key missing! Add GEMINI_API_KEY to your Streamlit Secrets.")

st.title("🏛️ Antenati AI Downloader & Translator")
st.markdown("💡 **How to use:** Paste a full Antenati URL or just the Image ID (for example, *LzPr8VJ*) below to stitch and analyze the record.")

# 3. Input with logic to handle URLs or IDs
raw_input = st.text_input("Paste Antenati URL or Image ID here:")
input_clean = raw_input.strip()

# Function to extract ID from URL if necessary
def get_image_id(user_input):
    if "antenati.cultura.gov.it" in user_input:
        # Regex to find the last part of the URL after the last slash
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

        # --- PREPARE DATA ---
        buf = BytesIO()
        final_img.save(buf, format="JPEG", quality=95)
        img_data = buf.getvalue()

        # --- UI LAYOUT ---
        # Action Buttons
        btn_col1, btn_col2 = st.columns([1, 4])
        with btn_col1:
            st.download_button("📥 Download JPG", img_data, f"{image_id}.jpg", "image/jpeg")
        
        # AI Trigger (Full Width below buttons)
        if st.button("🤖 AI Analyze & Translate"):
            with st.spinner("Gemini is reading the cursive..."):
                prompt = """
                Analyze this 1800s Italian civil record. 
                1. Transcribe key names, dates, and locations.
                2. Translate the summary into English.
                3. Format the result in a clear, full-width table or list.
                """
                response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_data}])
                
                # THIS IS THE FIX: Displaying the AI output outside of any columns
                st.markdown("---")
                st.subheader("📝 AI Findings (Full Width)")
                st.write(response.text)
                st.markdown("---")

        # Full Width Image Preview
        st.image(img_data, use_container_width=True)

    except Exception as e:
        st.error(f"Error processing {image_id}: {e}")
