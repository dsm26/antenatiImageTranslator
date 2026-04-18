import streamlit as st

def update_history(new_input):
    """
    Updates the session state history by moving the most recent input to the top
    and removing any duplicates.
    """
    if 'history' not in st.session_state:
        st.session_state.history = []
    
    # Clean input
    new_input = new_input.strip()
    if not new_input:
        return
    
    # Remove if already exists to keep list unique
    if new_input in st.session_state.history:
        st.session_state.history.remove(new_input)
    
    # Add to the end (since the UI uses reversed() to show newest at top)
    st.session_state.history.append(new_input)
    
    # Keep only the last 10 entries
    if len(st.session_state.history) > 10:
        st.session_state.history = st.session_state.history[-10:]

