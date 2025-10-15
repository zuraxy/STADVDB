import os
import requests

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:3000")

# Styling
COLORS = {
    'background': '#F8F9FA',
    'text': '#212529',
    'primary': '#007BFF',
    'secondary': '#6C757D',
    'success': '#28A745',
    'card': '#FFFFFF',
}

# Common function to make API requests

def make_api_request(endpoint, params=None):
    try:
        resp = requests.get(f"{BACKEND_URL}/{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get('rows', []), data.get('durationMs', 0)
    except Exception as e:
        print(f"Backend request failed ({endpoint}):", e)
        return [], 0
