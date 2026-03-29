from streamlit.testing.v1 import AppTest
import pytest

def test_app_initialization():
    """Ensure the app starts and shows the title and help text."""
    at = AppTest.from_file("streamlit_app.py").run()
    assert at.title[0].value == "🏛️ Antenati Downloader & AI Translator"
    assert "How to use" in at.markdown[0].value

def test_query_params_handling():
    """Ensure passing an image_id in the URL populates the input field."""
    at = AppTest.from_file("streamlit_app.py")
    at.query_params["image_id"] = "LzPr8VJ"
    at.run()
    
    # Check if the text input was automatically filled
    assert at.text_input[0].value == "LzPr8VJ"

def test_csv_format_logic():
    """Test the logic of the CSV row builder directly."""
    from streamlit_app import format_csv_row
    
    sample_data = {
        "type": "Nascita",
        "subject": "Mario Rossi",
        "date": "1880",
        "father": "Giuseppe",
        "mother": "Maria Biondi",
        "town": "Salerno",
        "job": "Contadino",
        "notes": "Twin birth"
    }
    
    row = format_csv_row(sample_data, "12345", "https://antenati.it/test")
    
    # Verify the 10-column structure
    parts = row.split('","')
    assert len(parts) == 10
    assert "Contadino" in row
    assert "https://antenati.it/test" in row
