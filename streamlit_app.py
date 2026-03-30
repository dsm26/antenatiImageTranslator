import streamlit as st
import math
import requests
import re
import json
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import subprocess
from datetime import datetime


# --- CONFIGURATION ---
CHOSEN_MODEL = 'gemini-3.1-flash-lite-preview' 
CACHE_TTL = 900 
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://antenati.cultura.gov.it/",
}

st.set_page_config(page_title="Antenati Downloader & AI Translator", page_icon="🧬", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []

# --- ROBUST METADATA EXTRACTION ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_antenati_metadata(input_str):
    image_id = input_str.strip().split('/')[-1] if "/" in input_str else input_str.strip()
    
    # Strategy 1: IIIF Manifest
    try:
        manifest_url = f"https://antenati.cultura.gov.it/iiif/2/{image_id}/manifest"
        resp = requests.get(manifest_url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            label = resp.json().get("label", "")
            if label: return f"{label}"
    except:
        pass

    # Strategy 2: Page Scraping (Requires Full URL)
    if "antenati.cultura.gov.it" in input_str:
        try:
            resp = requests.get(input_str, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                title_match = re.search(r'<title>(.*?)</title>', resp.text)
                if title_match:
                    clean_title = title_match.group(1).replace(" - Antenati", "").strip()
                    if clean_title and "Antenati" not in clean_title:
                        return f"{clean_title}"
        except:
            pass

    # Strategy 3: ID Breakdown
    folder_match = re.search(r'an_ua\d+', input_str)
    if folder_match:
        return f"Italian Record (Unit: {folder_match.group(0)}, ID: {image_id})"

    return f"Italian Civil Record (ID: {image_id})"

# --- DOWNLOAD & STITCHING ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_stitched_image(image_id):
    base_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}"
    info_resp = requests.get(f"{base_url}/info.json", headers=HEADERS)
    info_resp.raise_for_status()
    info = info_resp.json()
    
    w, h = info["width"], info["height"]
    
    # Corrected extraction logic for tile dimensions
    first_tile = info["tiles"][0]
    tw = first_tile["width"]
    th = first_tile.get("height", tw)
    
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

# --- AI ANALYSIS ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_ai_analysis(img_bytes, metadata_context, _model_instance):
    prompt = f"""
    ARCHIVAL CONTEXT: {metadata_context}
    
    TASK: Analyze this 19th-century Italian civil record.
    1. Identify Record Type, Primary Subject Name, Date of Event, Father's Name, Mother's Name (with maiden name), and Town.
    2. Provide a full transcription of names and any marginalia.
    3. Provide an English Summary of the key findings.
    
    IMPORTANT: After your summary, provide a single line starting with "RAW_DATA: " followed by a JSON block exactly like this:
    RAW_DATA: {{"type": "...", "subject": "...", "date": "...", "father": "...", "mother": "...", "town": "...", "notes": "..."}}
    """
    response = _model_instance.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_bytes}])
    return response.text

# --- CSV & TABLE HELPERS ---
def extract_raw_data(ai_text):
    try:
        match = re.search(r'RAW_DATA:\s*(\{.*?\})', ai_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except:
        return None
    return None

def format_csv_row(data, image_id, source_input):
    if not data: return None
    source_url = source_input if "http" in source_input else f"https://antenati.cultura.gov.it/ark:/12657/an_ua/{image_id}"
    row = [
        image_id, 
        data.get("type",""), 
        data.get("subject",""), 
        data.get("date",""), 
        data.get("father",""), 
        data.get("mother",""), 
        data.get("town",""), 
        data.get("notes","").replace("\n", " "),
        source_url
    ]
    return ",".join([f'"{str(x)}"' for x in row])

# --- GIT METADATA HELPER ---
def get_git_info():
    try:
        # Get short hash
        sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
        # Get commit date
        commit_date = subprocess.check_output(['git', 'log', '-1', '--format=%cd', '--date=format:%Y-%m-%d %H:%M']).decode('ascii').strip()
        return f"Build: {sha} | {commit_date}"
    except:
        # Fallback if git is not initialized or available (e.g., in some cloud environments)
        return f"Last Refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ App Management")
    st.write(f"**Default model:** {CHOSEN_MODEL}")
    st.write(f"**Cache TTL:** {CACHE_TTL//60}m")
    if st.button("🗑️ Clear Cache & History"):
        st.cache_data.clear()
        st.session_state.history = []
        st.rerun()

    if st.session_state.history:
        st.markdown("---")
        st.header("🕒 Recent History")
        for h_id in reversed(st.session_state.history[-5:]):
            if st.button(f"📄 {h_id}", key=f"hist_{h_id}", use_container_width=True):
                st.query_params["url"] = "" 
                st.query_params["image_id"] = h_id
                st.rerun()

    st.markdown("---")
    with st.expander("📊 CSV Log Guide"):
        st.markdown("""
        **Column Meanings:**
        1. **ID:** Antenati Image ID.
        2. **Type:** Birth, Marriage, Death, etc.
        3. **Subject:** The primary person of the record.
        4. **Date:** Event date as written.
        5. **Father:** Father's full name.
        6. **Mother:** Mother's full name (including maiden name).
        7. **Town:** Archive/Registration location.
        8. **Notes:** Marginalia, ages, or additional family details.
        9. **Source URL:** Direct link to the original record.
        """)

    st.markdown("---")
    st.caption(get_git_info())

# --- MAIN UI ---
st.title("🏛️ Antenati Downloader & AI Translator")

st.markdown(f"""
💡 **How to use:** Paste a **Full URL** (recommended) or an **Image ID**. <br>
🔗 **Quick Link:** Pass parameters in the browser bar using `?url=FULL_URL` or `?image_id=ID`. <br>
**Example URL:** https://antenati.cultura.gov.it/ark:/12657/an_ua264421/LzPr8VJ <br>
**Example ID:** LzPr8VJ
""", unsafe_allow_html=True)

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    params = st.query_params
    url_param = params.get("url", "")
    id_param = params.get("image_id", "")
    initial_value = url_param if url_param else id_param
    
    raw_input = st.text_input("Paste Antenati URL or Image ID:", value=initial_value)
    input_id = raw_input.strip().split('/')[-1] if "/" in raw_input else raw_input.strip()

    if input_id:
        if input_id not in st.session_state.history:
            st.session_state.history.append(input_id)

        try:
            record_meta = get_antenati_metadata(raw_input if "http" in raw_input else input_id)
            img_data = get_stitched_image(input_id)
            
            # Action Row
            col1, col2 = st.columns([1, 4])
            with col1:
                st.download_button("📥 Download JPG", img_data, f"{input_id}.jpg", "image/jpeg")
            with col2:
                if "http" in raw_input:
                    permalink = f"{st.get_option('server.baseUrlPath') or ''}?url={raw_input}"
                    st.code(permalink, language="text")
                    st.caption("🔗 Shareable Permalink for this URL")

            status_area = st.empty()
            st.image(img_data, use_container_width=True)
            st.info(f"📍 **Archival Context:** {record_meta}")

            # --- MANUAL TRANSLATION BUTTON & MODEL SELECTOR ---
            st.markdown("---")
            
            # Using vertical_alignment="bottom" ensures the button aligns
            # with the input field, not the label
            model_col, btn_col, spacer = st.columns([2, 2, 4], vertical_alignment="bottom")

            with model_col:
                # Prepending 'gemini-' to fix the 404 errors you encountered
                selected_model_name = st.selectbox(
                    "AI Model:",
                    options=[
                        "gemini-3.1-flash-lite-preview", 
                        "gemini-2.5-flash", 
                        "gemini-2.5-flash-lite", 
                        "gemini-3.1-flash-lite"
                    ],
                    index=0
                )

            with btn_col:
                # This button will now stay on the same line as the selector
                translate_clicked = st.button("Translate with AI", type="primary", use_container_width=True)

            if translate_clicked:
                current_model = genai.GenerativeModel(selected_model_name)
                status_area.info(f"⏳ AI is analyzing record: {input_id}. Results will appear **below the image** once completed...")
                
                try:
                    analysis_text = get_ai_analysis(img_data, record_meta, current_model)
                    display_text = analysis_text.split("RAW_DATA:")[0].strip()
                    raw_data = extract_raw_data(analysis_text)
                    
                    st.markdown('<div id="findings"></div>', unsafe_allow_html=True)
                    st.markdown("---")
                    st.subheader("📝 AI Findings")
                    st.write(display_text)
                    
                    if raw_data:
                        st.markdown("---")
                        st.subheader("📊 Research Log Data")
                
                # --- NEW HUMAN READABLE TABLE ---
                        st.table({
                            "Field": ["ID", "Record Type", "Subject", "Date", "Father", "Mother", "Town", "Notes"],
                            "Value": [input_id, raw_data.get("type"), raw_data.get("subject"), raw_data.get("date"), 
                                      raw_data.get("father"), raw_data.get("mother"), raw_data.get("town"), raw_data.get("notes")]
                        })
                        
                # --- CSV CODE BLOCK ---
                        csv_row = format_csv_row(raw_data, input_id, raw_input)
                        st.markdown("**CSV Copy-Paste Row:**")
                        st.code(csv_row, language="csv")
                        st.caption("☝️ Use the copy button in the top right to paste this row into your master log.")
                    
                    status_area.success(f"✅ Analysis complete. [View Findings](#findings)")

                except Exception as e:
                    status_area.empty()
                    if "429" in str(e) or "quota" in str(e).lower():
                        st.warning("⚠️ **Rate Limit Reached:** You've hit your daily or per-minute quota for the Gemini API. Please wait about 60 seconds and try again.")
                    else:
                        st.error("❌ **An unexpected error occurred during AI analysis.**")
                    
                    with st.expander("Show Technical Error Details"):
                        st.exception(e)

        except Exception as e:
            st.error(f"Error fetching record: {e}")
else:
    st.error("🔑 API Key missing in Secrets.")
