import streamlit as st
import math
import requests
import re
import json
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import subprocess
from datetime import datetime
import uuid
import traceback
import google.generativeai as genai
from feedback import show_feedback_form
from input_validator import validate_antenati_url

# --- CONFIGURATION ---
APP_NAME = "Antenati Downloader & AI Translator"
APP_ICON = "🏛️"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://antenati.cultura.gov.it/"
}

# --- GOOGLE ANALYTICS VIA SECRETS ---
# These pull from .streamlit/secrets.toml or Streamlit Cloud Secrets
GA_MEASUREMENT_ID = st.secrets.get("GA_MEASUREMENT_ID")
GA_API_SECRET = st.secrets.get("GA_API_SECRET")

# Cache control
CACHE_TTL = 900

# --- AI PROMPT CONFIGURATION ---
DEFAULT_AI_MODEL = 'gemini-3.1-flash-lite-preview'

def load_prompt():
    """Reads the prompt from prompt.txt and handles fallback."""
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: AI prompt.txt file not found"

DEFAULT_PROMPT = load_prompt()

def load_models():
    """Reads the list of models from models.txt."""
    try:
        with open("models.txt", "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return [DEFAULT_AI_MODEL]

AVAILABLE_MODELS = load_models()

# --- GIT METADATA HELPER ---
def get_git_info():
    try:
        # Get short hash
        sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
        # Get commit date
        commit_date = subprocess.check_output(['git', 'log', '-1', '--format=%cd', '--date=format:%Y-%m-%d %H:%M']).decode('ascii').strip()
        return f"Build: {sha} | {commit_date}"
    except:
        # Fallback if git is not available
        return f"Last Refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

# --- GOOGLE ANALYTICS TRACKING ---
def track_ga_event(event_name, extra_params=None):
    """Sends a server-side event to GA4 using Streamlit Secrets."""
    try:
        if not GA_API_SECRET or not GA_MEASUREMENT_ID:
            return

        # Get real user IP from Streamlit Cloud proxy headers for location
        user_ip = st.context.headers.get("X-Forwarded-For", "0.0.0.0").split(",")[0]
        user_agent = st.context.headers.get("User-Agent", "Unknown")
        
        if "ga_client_id" not in st.session_state:
            st.session_state.ga_client_id = str(uuid.uuid4())

        url = f"https://www.google-analytics.com/mp/collect?measurement_id={GA_MEASUREMENT_ID}&api_secret={GA_API_SECRET}"
        
        payload = {
            "client_id": st.session_state.ga_client_id,
            "events": [{
                "name": event_name,
                "params": {
                    "ip_override": user_ip,
                    "user_agent": user_agent,
                    "engagement_time_msec": "1",
                    **(extra_params or {})
                }
            }]
        }
        requests.post(url, data=json.dumps(payload), timeout=2)
    except:
        pass

# --- REFACTORED LOGGING FUNCTION ---
def log_to_gsheets(sheet_name, row_data):
    """Targeted logging for usage, error, and ai tabs."""
    script_url = st.secrets.get("GSHEET_WEBAPP_URL")
    if not script_url:
        return

    client_id = st.session_state.get("ga_client_id", "unknown_session")
    
    payload = {
        "sheetName": sheet_name,
        "rowData": [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), client_id] + row_data
    }
    
    try:
        requests.post(script_url, json=payload, timeout=5)
    except:
        pass

def get_canvas_id_url(url):
    """Parses the Antenati HTML to extract the hidden canvasId URL."""
    try:
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://antenati.cultura.gov.it/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        resp = requests.get(url, headers=HEADERS, timeout=5)

        if resp.status_code == 200:
            match = re.search(r"canvasId:\s*'([^']+)'", resp.text)
            if match:
                return match.group(1)
        elif resp.status_code == 403:
             st.write(f"DEBUG: 403 Forbidden received for {url}")

    except:
        pass
    return None

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide")

# --- INITIAL PAGE LOAD TRACKING ---
if "page_loaded" not in st.session_state:
    track_ga_event("page_load")
    st.session_state.page_loaded = True

if "history" not in st.session_state:
    st.session_state.history = []

if "last_tracked_path" not in st.session_state:
    st.session_state.last_tracked_path = None

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
def get_stitched_image(cache_key, image_id, source_input, ark_unit=""):
    base_url = f"https://iiif-antenati.cultura.gov.it/iiif/2/{image_id}"
    try:
        info_resp = requests.get(f"{base_url}/info.json", headers=HEADERS)
        info_resp.raise_for_status()
        info = info_resp.json()
    except Exception as e:
        track_ga_event("antenati_error", {"error_type": "info_json", "image_id": image_id})
        log_to_gsheets("error_logs", [APP_NAME, ark_unit, source_input, "Stitching Error (Info JSON)", str(e), traceback.format_exc()])
        raise e
    
    w, h = info["width"], info["height"]
    
    # Border/Footer settings
    footer_height = 50
    
    # Corrected extraction logic for tile dimensions
    first_tile = info["tiles"][0]
    tw = first_tile["width"]
    th = first_tile.get("height", tw)
    
    # Create canvas with extra room at the bottom for visual metadata
    final_img = Image.new("RGB", (w, h + footer_height), (255, 255, 255))
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
            try:
                res = requests.get(tile_url, headers=HEADERS)
                res.raise_for_status()
                tile_data = Image.open(BytesIO(res.content))
                final_img.paste(tile_data, (x, y))
            except Exception as e:
                track_ga_event("antenati_error", {"error_type": "tile_download", "image_id": image_id})
                log_to_gsheets("error_logs", [APP_NAME, ark_unit, source_input, "Stitching Error (Tile)", str(e), traceback.format_exc()])
                raise e
    
    progress_placeholder.empty()

    # --- ADD TEXT OVERLAY ---
    draw = ImageDraw.Draw(final_img)
    try:
        # standard linux/cloud font path
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 35)
    except:
        font = ImageFont.load_default()

    label_text = f"Source: {source_input}"
    # Draw the text in the new white space (the footer)
    text_x = 20
    text_y = h + 10
    draw.text((text_x, text_y), label_text, fill=(0, 0, 0), font=font)

    # Embed metadata into EXIF (Tag 270 is ImageDescription)
    exif = final_img.getexif()
    # Tag 270: ImageDescription (Standard)
    exif[270] = f"Source: {source_input}"
    # Tag 37510: UserComment (Often more reliable for Windows 'Comments' field)
    exif[37510] = f"Source: {source_input}"

    buf = BytesIO()
    final_img.save(buf, format="JPEG", quality=95, subsampling=0, exif=exif)
    return buf.getvalue()

# --- AI ANALYSIS ---
@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_ai_analysis(img_bytes, metadata_context, _model_instance, model_name):
    # Using the prompt variable formatted with context
    prompt = DEFAULT_PROMPT.format(metadata_context=metadata_context)

    response = _model_instance.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_bytes}])
    return response.text

# --- CSV & TABLE HELPERS ---
def format_csv_row(data, image_id, source_input):
    if not data: return None
    source_url = source_input if "http" in source_input else f"https://antenati.cultura.gov.it/ark:/12657/an_ua/{image_id}"
    
    if data.get("format") == "list":
        rows = []
        for r in data.get("rows", []):
            row_data = [image_id, data.get("type"), source_url] + r
            rows.append(",".join([f'"{str(x)}"' for x in row_data]))
        return "\n".join(rows)
    else:
        row = [
            image_id,                                # 1
            data.get("type",""),                     # 2
            data.get("subject",""),                  # 3
            data.get("date",""),                     # 4
            data.get("father",""),                   # 5
            data.get("mother",""),                   # 6
            data.get("town",""),                     # 7
            data.get("occupation",""),               # 8
            data.get("address",""),                  # 9
            data.get("notes","").replace("\n", " "), # 10
            source_url                               # 11
        ]
        return ",".join([f'"{str(x)}"' for x in row])

def extract_raw_data(ai_text):
    try:
        match = re.search(r'RAW_DATA:\s*(\{.*?\})', ai_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except:
        return None
    return None

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ App Management")
    
    # Optional API Key Input
    user_api_key = st.text_input(
        "🔑 Personal Gemini API Key (Optional)", 
        type="password", 
        placeholder="Paste your key here...",
        help="If the app's shared quota is reached, you can use your own key. [Create a free API key here](https://aistudio.google.com/api-keys)."
    )
    if user_api_key and "api_key_tracked" not in st.session_state:
        track_ga_event("personal_key_entered")
        st.session_state.api_key_tracked = True
    
    st.write(f"**Cache TTL:** {CACHE_TTL//60}m")
    if st.button("🗑️ Clear Cache & History"):
        st.cache_data.clear()
        st.session_state.history = []
        st.session_state.last_tracked_path = None
        st.rerun()

    if st.session_state.history:
        st.markdown("---")
        st.header("🕒 Recent History")
        for h_input in reversed(st.session_state.history[-5:]):
            h_id = h_input.strip().split('/')[-1] if "/" in h_input else h_input.strip()
            if st.button(f"📄 {h_id}", key=f"hist_{h_id}", use_container_width=True):
                st.query_params["image_id"] = "" 
                st.query_params["url"] = h_input
                st.rerun()

    st.markdown("---")
    with st.expander("📊 CSV Log Guide"):
        st.markdown("""
        **Individual Records:**
        1. **ID:** Antenati Image ID.
        2. **Type:** Birth, Marriage, Death, *Processetti/Allegati*, or Parish Record.
        3. **Subject:** The primary person(s) of the record.
        4. **Date:** Event date (Baptism vs. birth clarified by AI).
        5. **Father:** Father's full name.
        6. **Mother:** Mother's full name (including maiden name).
        7. **Town:** Archive location, registration town, or *Parish name*.
        8. **Occupation:** Profession of subject, parents, or witnesses.
        9. **Address:** Street name, house number, or hamlet (frazione).
        10. **Notes:** Marginalia, ages, Latin-to-English clarifications, or supplemental document details.
        11. **Source URL:** Direct link to the original record.
        
        **Census/Index Lists:** Multi-row format.
        1. **ID:** Antenati Image ID.
        2. **Type:** Type of list.
        3. **Source URL:** Direct link.
        4. **Data Columns:** Vary based on the document (Name, Age, Year, etc).
        """)

    with st.expander("🤖 Current AI Prompt"):
        st.info("This is the instruction set currently being used by the AI:")
        st.code(DEFAULT_PROMPT, language="text")

    st.markdown("---")
    st.markdown("📖 [Learn more about this app](https://community.familysearch.org/en/discussion/179735/antenati-full-sized-image)")
    st.caption(get_git_info())

# --- MAIN UI ---
st.title(f"{APP_ICON} {APP_NAME}")

with st.expander("ℹ️ Instructions"):
    st.markdown("""
    This tool is designed for use with the official [Antenati portal](https://antenati.cultura.gov.it/), 
    not the copies found on FamilySearch.

    **How to use:**
    1. Find the record image you want to download on the Antenati website.
    2. Look for the link labeled "Copia link del bookmark" on that page and click it to copy the address.
    3. Paste that link into the box below.

    **Example URLs:**
    * https://antenati.cultura.gov.it/ark:/12657/an_ua264421/LzPr8VJ - 1871 Civile Nati
    * https://antenati.cultura.gov.it/ark:/12657/an_ua264421/LzPr8x9 - 1871 Civile Nati index page
    * https://antenati.cultura.gov.it/ark:/12657/an_ua36205266/Le8qveo - 1816 Matrimoni index page
    * https://antenati.cultura.gov.it/ark:/12657/an_ua36203217/Lz7XnvP - 1841 Censimento page

    **Example ID:** LzPr8VJ

    **📥 Best Way to Save**
    For the best results, always use the **"Download" button** rather than right-clicking the image. The button automatically names your file using the **Image ID** and will embed the **original Antenati URL** in the file's internal metadata.


    🔗 **Quick Link:** Pass parameters in the browser bar using `?url=FULL_URL` or `?image_id=ID`.


    💡 **AI Use:** By default, this page uses a shared Google Gemini AI account with a daily rate limit for the AI translations. If you plan to perform many translations (e.g. over 100), please [create your own free Gemini API key](https://aistudio.google.com/api-keys) and specify it in the left sidebar. There is no rate limit for the image downloading.
    """)

# Determine which API key to use (Personal > Secret)
final_api_key = user_api_key if user_api_key else st.secrets.get("GEMINI_API_KEY")

if final_api_key:
    genai.configure(api_key=final_api_key)
    
    params = st.query_params
    url_param = params.get("url", "")
    id_param = params.get("image_id", "")
    initial_value = url_param if url_param else id_param
    
    raw_input = st.text_input("Paste Antenati URL (preferred) or Image ID:", value=initial_value)

    # --- URL VALIDATION & ID EXTRACTION ---
    input_id, ark_part1, original_input, processing_url = validate_antenati_url(
        raw_input, id_param, get_canvas_id_url, APP_NAME
    )

    # Update raw_input for the rest of the logic to use the resolved URL
    raw_input = processing_url
    
    if input_id:

        st.info(f"Processing ID: {image_id}...")

        if original_input not in st.session_state.history:
            st.session_state.history.append(original_input)

        try:
            record_meta = get_antenati_metadata(raw_input if "http" in raw_input else input_id)
            
            # --- Robust Ark Part 1 Fallback ---
            if not ark_part1:
                meta_match = re.search(r'an_ua\d+', record_meta)
                if meta_match:
                    ark_part1 = meta_match.group(0)

            # Cache using full raw_input (URL or ID)
            img_data = get_stitched_image(raw_input, input_id, raw_input, ark_unit=ark_part1)
            
            # --- TRACK IMAGE STITCHING/VIEW (only once per ID) ---
            if "last_stitched_id" not in st.session_state or st.session_state.last_stitched_id != input_id:
                track_ga_event("image_stitched", {"image_id": input_id})

                # --- TRIGGER 1: Tab 1 (usage_logs) ---
                # Tab 1: [Timestamp, Session_ID, App_Name, ARK_Unit, ARK_URL, Original_URL (Optional)]
                usage_row = [APP_NAME, ark_part1, raw_input]
                if raw_input != original_input:
                    usage_row.append(original_input)
                
                log_to_gsheets("usage_logs", usage_row)
                st.session_state.last_stitched_id = input_id
            
            # Determine descriptive filename
            save_name = f"{ark_part1}_{input_id}.jpg" if ark_part1 else f"{input_id}.jpg"

            # --- AI MODEL SELECTOR & STATUS (NOW ABOVE IMAGE) ---
            st.markdown("---")
            model_col, btn_col, spacer = st.columns([4, 2, 4], vertical_alignment="bottom")

            key_suffix = "(using personal Gemini key)" if user_api_key else "(using default Gemini key)"
            with model_col:
                selected_model_name = st.selectbox(
                    f"AI Model {key_suffix}:",
                    options=AVAILABLE_MODELS,
                    index=0
                )

            with btn_col:
                translate_clicked = st.button("Translate with AI", type="primary", use_container_width=True)

            # Move status area here so it appears above the image
            status_area = st.empty()

            # Action Row (Download Button)
            col1, spacer_dl = st.columns([2, 8])
            with col1:
                dl_btn = st.download_button("📥 Download JPG", img_data, save_name, "image/jpeg", use_container_width=True)
                if dl_btn:
                    track_ga_event("download_button_pushed", {"image_id": input_id})

            st.image(img_data, use_container_width=True)
            st.info(f"📍 **Archival Context:** {record_meta}")

            if translate_clicked:
                track_ga_event("ai_translation_started", {"model": selected_model_name})
                if user_api_key:
                    track_ga_event("personal_key_used_for_translation")
                
                current_model = genai.GenerativeModel(selected_model_name)
                status_area.info(
                    f"⏳ AI is analyzing record: {input_id}. Results will appear **below** once completed...\n\n"
                    f"By default, this page uses a shared account with a daily rate limit. "
                    f"If you plan to perform many translations, please use your own key in the sidebar."
                )
                
                try:
                    analysis_text = get_ai_analysis(img_data, record_meta, current_model, selected_model_name)
                    
                    # --- TRIGGER 3: Tab 3 (ai_logs) ---
                    # Tab 3: [Timestamp, Session_ID, App_Name, ARK_Unit, ARK_URL, Model_Used, Key_Type]
                    key_type = "Personal" if user_api_key else "Shared"
                    log_to_gsheets("ai_logs", [APP_NAME, ark_part1, raw_input, selected_model_name, key_type])

                    display_text = analysis_text.split("RAW_DATA:")[0].strip()
                    raw_data = extract_raw_data(analysis_text)
                    
                    st.markdown('<div id="findings"></div>', unsafe_allow_html=True)
                    st.markdown("---")
                    st.subheader("📝 AI Findings")
                    st.write(display_text)
                    
                    if raw_data:
                        st.markdown("---")
                        st.subheader("📊 Research Log Data")
                        final_source_url = raw_input if "http" in raw_input else f"https://antenati.cultura.gov.it/ark:/12657/an_ua/{input_id}"
                        
                        if raw_data.get("format") == "list":
                            # Census/Index Multi-row table
                            cols = raw_data.get("columns", [])
                            rows = raw_data.get("rows", [])

                            # Convert list of lists to list of dicts so Streamlit shows headers
                            formatted_data = [dict(zip(cols, row)) for row in rows]
                            st.dataframe(data=formatted_data, use_container_width=True)
                            
                        else:
                            # Standard Individual Record table
                            st.table({
                                "Field": [
                                "1. ID",
                                "2. Record Type",
                                "3. Subject",
                                "4. Date", 
                                "5. Father",
                                "6. Mother",
                                "7. Town", 
                                "8. Occupation",
                                "9. Address",
                                "10. Notes",
                                "11. Source URL"
                            ],
                            "Value": [
                                input_id,
                                raw_data.get("type"),
                                raw_data.get("subject"), 
                                raw_data.get("date"),
                                raw_data.get("father"),
                                raw_data.get("mother"), 
                                raw_data.get("town"),
                                raw_data.get("occupation"),
                                raw_data.get("address"), 
                                raw_data.get("notes"),
                                final_source_url
                            ]
                          })
                            
                        # --- CSV CODE BLOCK ---
                        csv_row = format_csv_row(raw_data, input_id, raw_input)
                        st.markdown("**CSV Copy-Paste Row(s):**")
                        st.code(csv_row, language="csv")
                        st.caption("☝️ Use the copy button in the top right to paste into your log.")
                    
                    status_area.success(
                        f"✅ Analysis complete. [View Findings](#findings)"
                    )

                except Exception as e:
                    # --- TRIGGER 2: Tab 2 (error_logs) ---
                    status_area.empty()
                    err_msg = str(e)
                    tb_str = traceback.format_exc()
                    
                    # Tab 2: [Timestamp, Session_ID, App_Name, ARK_Unit, ARK_URL, Error_Type, Error_Msg, Traceback]
                    log_to_gsheets("error_logs", [APP_NAME, ark_part1, raw_input, type(e).__name__, err_msg, tb_str])
                    
                    if "429" in err_msg or "quota" in err_msg.lower():
                        st.warning("⚠️ **Rate Limit Reached:** API quota hit. Wait a moment or use your own key.")
                    else:
                        st.error("❌ **An unexpected error occurred during AI analysis.**")

                    with st.expander("Show Technical Error Details"):
                        st.exception(e)

        except Exception as e:
            st.error(f"Error fetching record: {e}")
            # --- TRIGGER 2: Tab 2 (error_logs) for Fetch/Metadata Errors ---
            log_to_gsheets("error_logs", [APP_NAME, ark_part1, raw_input, "Fetch/Metadata Error", str(e), traceback.format_exc()])
else:
    st.error("🔑 API Key missing. Provide a key in the sidebar or check Secrets.")

# --- FINAL UI ELEMENTS ---
show_feedback_form(APP_NAME, HEADERS)
