from streamlit.testing.v1 import AppTest
import pytest
from unittest.mock import patch
import io

# 1. We create a "Mock" image so the app has something to display
def get_mock_image_bytes(*args, **kwargs):
    return b"fake-image-data-for-testing"

# 2. We mock the AI response so we don't spend API credits during tests
MOCK_AI_RESPONSE = """
This is a birth record for Mario Rossi.
RAW_DATA: {"type": "Nascita", "subject": "Mario Rossi", "date": "1880", "father": "Giuseppe", "mother": "Maria Biondi", "town": "Salerno", "job": "Contadino", "notes": "Twin"}
"""

def test_app_initialization():
    at = AppTest.from_file("streamlit_app.py").run()
    assert any("Antenati Downloader" in m.value for m in at.title)

@patch("streamlit_app.get_stitched_image")
@patch("streamlit_app.get_ai_analysis")
@patch("streamlit_app.get_antenati_metadata")
def test_full_flow_with_mocks(mock_meta, mock_ai, mock_stitch):
    """Test the app flow without hitting real servers."""
    # Setup our "Lies" (Mocks)
    mock_stitch.return_value = get_mock_image_bytes()
    mock_ai.return_value = MOCK_AI_RESPONSE
    mock_meta.return_value = "Provincia di Salerno, 1880"
    
    at = AppTest.from_file("streamlit_app.py")
    at.query_params["image_id"] = "LzPr8VJ"
    
    # This run is now INSTANT because it doesn't go to the web
    at.run(timeout=5)
    
    # Assertions
    assert at.text_input[0].value == "LzPr8VJ"
    # Check if the table rendered the mock data
    assert any("Mario Rossi" in str(t.value) for t in at.table)

def test_csv_format_logic():
    """Verify the 10-column CSV structure."""
    from streamlit_app import format_csv_row
    
    sample_data = {
        "type": "Nascita",
        "subject": "Mario Rossi",
        "date": "1880",
        "father": "Giuseppe",
        "mother": "Maria Biondi",
        "town": "Salerno",
        "job": "Contadino",
        "notes": "None"
    }
    
    row = format_csv_row(sample_data, "12345", "https://antenati.it/test")
    # Verify exactly 9 commas (for 10 columns)
    assert row.count(",") == 9
    assert '"Contadino"' in row
