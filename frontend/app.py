# ...existing code...
import os
import dash
from dash import html, dcc
import pandas as pd
import requests
import plotly.express as px

app = dash.Dash(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:3000")
params = {
    "start": "2024-01-01",
    "end": "2024-12-31",
    "category": None,
    "granularity": "month",
}

try:
    resp = requests.get(f"{BACKEND_URL}/query1")
    resp.raise_for_status()
    data = resp.json()
except Exception as e:
    print("Backend request failed:", e)
    data = []

df = pd.DataFrame(data)
if df.empty:
    df = pd.DataFrame({"period": [], "revenue": []})

fig = px.line(df, x="period", y="revenue", title="Revenue Over Time")

app.layout = html.Div([
    html.H1("Data Warehouse Dashboard"),
    dcc.Graph(figure=fig)
])

if __name__ == "__main__":
    app.run(debug=True)
# ...existing code...