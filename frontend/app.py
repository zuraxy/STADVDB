import os
import dash
from dash import html, dcc, Input, Output, State
import pandas as pd
import requests
import plotly.express as px

app = dash.Dash(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:3000")

app.layout = html.Div([
    html.H1("Data Warehouse Dashboard"),
    html.Div([
        "Start Date: ",
        dcc.Input(id="start-date", type="text", value="2024-01-01"),
        " End Date: ",
        dcc.Input(id="end-date", type="text", value="2024-12-31"),
        " Category: ",
        dcc.Input(id="category", type="text", value=""),
        " Granularity: ",
        dcc.Dropdown(
            id="granularity",
            options=[
                {"label": "Year", "value": "year"},
                {"label": "Month", "value": "month"},
                {"label": "Day", "value": "day"},
            ],
            value="month",
            clearable=False,
            style={"width": "120px"}
        ),
        html.Button("Submit", id="submit-btn", n_clicks=0)
    ], style={"marginBottom": "20px"}),
    dcc.Loading(dcc.Graph(id="revenue-graph")),
    html.H2("Customer Distribution by Country and City"),
    dcc.Loading(dcc.Graph(id="customer-dist-graph")),
])


@app.callback(
    Output("revenue-graph", "figure"),
    Output("customer-dist-graph", "figure"),
    Input("submit-btn", "n_clicks"),
    State("start-date", "value"),
    State("end-date", "value"),
    State("category", "value"),
    State("granularity", "value"),
)
def update_graphs(n_clicks, start, end, category, granularity):
    # Always use defaults if n_clicks == 0 (initial load)
    start = start or "2024-01-01"
    end = end or "2024-12-31"
    category = category if category else None
    granularity = granularity or "month"

    # Revenue query
    params = {
        "start": start,
        "end": end,
        "category": category,
        "granularity": granularity,
    }
    try:
        resp = requests.get(f"{BACKEND_URL}/query1", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print("Backend request failed (revenue):", e)
        data = []
    df = pd.DataFrame(data)
    if df.empty:
        df = pd.DataFrame({"period": [], "revenue": []})
    fig1 = px.line(df, x="period", y="revenue", title="Revenue Over Time")

    # Customer distribution query
    try:
        resp2 = requests.get(f"{BACKEND_URL}/query2", timeout=15)
        print(f"[frontend] /query2 status: {resp2.status_code}")
        print(f"[frontend] /query2 response: {resp2.text[:500]}")  # print first 500 chars
        resp2.raise_for_status()
        data2 = resp2.json()
    except Exception as e:
        print("Backend request failed (customer dist):", e)
        data2 = []
    df2 = pd.DataFrame(data2)
    if df2.empty:
        df2 = pd.DataFrame({"country": [], "total_customers": []})
    else:
        # Aggregate by country
        df2 = df2.groupby("country", as_index=False)["total_customers"].sum()
    fig2 = px.bar(
        df2,
        x="country",
        y="total_customers",
        title="Customer Distribution by Country"
    )

    return fig1, fig2

if __name__ == "__main__":
    app.run(debug=True)