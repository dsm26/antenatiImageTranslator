import streamlit as st
from google import genai
from PIL import Image
import io
import subprocess
from datetime import datetime
import requests  # Ensure this is in your requirements.txt

# --- 1. BUILD INFO LOGIC ---
def get_git_info():
    """Pulls the current commit hash and date from GitHub."""
    try:
        # Gets the short 7-character hash
        hash = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
        # Gets the date of the last commit
        date_str = subprocess.check_output(['git', 'log', '-1', '--format=%cd', '--date=format:%Y-%m-%d %H:%M']).decode('ascii').strip()
        return f"Build: {hash} ({date_str})"
    except Exception:
        # Fallback if git is not initialized in the host environment
        return f"Build: Manual Deploy ({datetime.now().strftime('%Y-%m-%d %H:%M')})"

# --- 2. SIDEBAR UI ---
st.sidebar.title("Settings & Info")

# API Key Input
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Enter your Google AI Studio API Key")

# Model Selector (New 2026 Models to help with daily limits)
model_options = {
    "Gemini 2.5 Flash (Best Accuracy)": "gemini-2.5-flash",
    "Gemini 3.1 Flash-Lite (Highest Limits)": "gemini-3.1-flash-lite-preview",
    "Gemini 2.5 Flash-Lite (Very Fast)": "gemini-2.5-flash-lite",
    "Gemini 2.0 Flash (Stable)": "gemini-2.0-flash"
}

selected_display_name = st.sidebar.selectbox(
    "Select Gemini Model", 
    options=list(model_options.keys()), 
    index=0
)
selected_model_id = model_options[selected_display_name]

# CSV Guide (10 Columns)
st.sidebar.markdown("---")
st.sidebar.markdown("""
**CSV Log Guide (10 Fields):**
1. Image ID | 2. Record Type | 3. Subject Name | 4. Date | 5. Father | 6. Mother | 7. Town | 8. Job | 9. Notes | 10. Source URL
""")

# Versioning Footer
st.sidebar.markdown("---")
st.sidebar.caption(get_git_info())

# --- 3. MAIN UI ---
st.title("Antenati Downloader & AI Translator")
st.markdown("Enter an **Image ID** (e.g., `LzPr8VJ`) or a full **Antenati URL** to begin.")

input_val = st.text_input("Antenati URL or Image ID", placeholder="https://antenati.cultura.gov.it/detail-view/?id=...")

# --- 4. LOGIC FUNCTIONS ---

def format_csv_row(data, image_id, url):
    """Guarantees exactly 10 numbered fields (9 commas) for your spreadsheet."""
    fields = [
        str(image_id),           # 1
        data.get("type", "N/A"), # 2
        data.get("subject", "N/A"), # 3
        data.get("date", "N/A"), # 4
        data.get("father", "N/A"), # 5
        data.get("mother", "N/A"), # 6
        data.get("town", "N/A"), # 7
        data.get("job", "N/A"),  # 8
        data.get("notes", "N/A"), # 9
        str(url)                 # 10
    ]
    # Encapsulate in quotes to prevent internal commas from breaking the CSV
    return ",".join([f'"{f}"' for f in fields])

def get_ai_analysis(image_bytes):
    """Uses the modern google-genai SDK with the selected model."""
    if not api_key:
        return "⚠️ Please enter an API Key in the sidebar."
    
    try:
        client = genai.Client(api_key=api_key)
        img = Image.open(io.BytesIO(image_bytes))
        
        prompt = (
            "Analyze this Italian genealogical record. Provide a summary and then a "
            "JSON block labeled RAW_DATA: with keys: type, subject, date, father, "
            "mother, town, job, notes."
        )
        
        response = client.models.generate_content(
            model=selected_model_id,
            contents=[prompt, img]
        )
        
        if not response.text:
            return "AI returned an empty response. You may have hit a temporary quota limit."
            
        return response.text
    except Exception as e:
        if "429" in str(e) or "Resource Exhausted" in str(e):
            return f"⚠️ Limit Reached for {selected_display_name}. Switch to a 'Lite' model in the sidebar."
        return f"AI Error: {str(e)}"

# --- [INSERT YOUR ORIGINAL get_stitched_image() FUNCTION HERE] ---

# --- [INSERT YOUR ORIGINAL get_antenati_metadata() FUNCTION HERE] ---

# --- 5. EXECUTION BLOCK ---
if input_val:
    # Extract ID from URL if necessary
    input_id = input_val.split("id=")[-1] if "id=" in input_val else input_val
    
    if input_id:
        with st.status("Processing Record...", expanded=True) as status:
            st.write("Step 1: Downloading tiles & stitching image...")
            # --- CALL YOUR STITCHING FUNCTION HERE ---
            # image_data = get_stitched_image(input_id) 
            
            st.write(f"Step 2: Sending to {selected_display_name}...")
            # --- CALL THE AI ANALYSIS ---
            # analysis_text = get_ai_analysis(image_data)
            
            status.update(label="Analysis Complete!", state="complete", expanded=False)

        # --- [DISPLAY YOUR RESULTS / TABLE / CSV CODE HERE] ---
        # st.image(image_data)
        # st.write(analysis_text)

st.divider()
st.caption("Note: AI translations are probabilistic. Always verify with the original image.")
