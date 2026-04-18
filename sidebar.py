import streamlit as st
from git_utils import get_git_info
from api_helpers import track_ga_event
from update_history import update_history

def show_sidebar(CACHE_TTL, AVAILABLE_MODELS, DEFAULT_PROMPT):
    """
    Renders the sidebar and returns the user's personal API key if provided.
    """
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
            # Use enumerate to ensure unique keys even if IDs are similar
            for i, h_input in enumerate(reversed(st.session_state.history)):
                h_id = h_input.strip().split('/')[-1] if "/" in h_input else h_input.strip()
                if st.button(f"📄 {h_id}", key=f"hist_{h_id}_{i}", use_container_width=True):
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
        
        return user_api_key
