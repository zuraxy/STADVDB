from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
import pandas as pd
from common import COLORS, make_api_request


def layout():
    return dcc.Tab(label="Moving Average", children=[
        html.Div([
            html.H2("3-Month Moving Average"),
            html.Div([
                html.Div([
                    html.Label("Country:"),
                    dcc.Input(id="q4-country", type="text", placeholder="Leave empty for all countries"),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Button("Update", id="q4-submit-btn", n_clicks=0,
                           style={'backgroundColor': COLORS['primary'], 'color': 'white',
                                  'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
            ], style={"marginBottom": "20px"}),

            html.Div([
                dcc.Loading(
                    dcc.Graph(id="moving-avg-graph"),
                    type="circle"
                ),
            ], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),

            html.Div(id="q4-query-time", style={'marginTop': '10px', 'fontStyle': 'italic'})
        ], style={"padding": "20px"})
    ])


def register_callbacks(app):
    @app.callback(
        [Output("moving-avg-graph", "figure"), Output("q4-query-time", "children")],
        Input("q4-submit-btn", "n_clicks"),
        State("q4-country", "value"),
    )
    def update_moving_avg(n_clicks, country):
        params = {
            "country": country if country else None,
        }

        data, duration = make_api_request("query4", params)

        df = pd.DataFrame(data) if data else pd.DataFrame({
            "year": [], "month": [], "country": [], 
            "total_sales": [], "moving_avg_3_month": []
        })

        if df.empty:
            fig = go.Figure().add_annotation(
                text="No data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig, ""

        numeric_cols = ["total_sales", "moving_avg_3_month"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])

        df["date"] = pd.to_datetime(df["year"].astype(str) + "-" + df["month"].astype(str) + "-01")

        fig = go.Figure()

        if country:
            fig.add_trace(go.Scatter(
                x=df["date"],
                y=df["total_sales"],
                name="Monthly Sales",
                mode="lines+markers",
                line=dict(color=COLORS['secondary'])
            ))
            fig.add_trace(go.Scatter(
                x=df["date"],
                y=df["moving_avg_3_month"],
                name="3-Month Moving Avg",
                mode="lines",
                line=dict(color=COLORS['primary'], width=3)
            ))
            title = f"Sales and 3-Month Moving Average for {country}"
        else:
            for c in df["country"].unique():
                country_df = df[df["country"] == c]
                fig.add_trace(go.Scatter(
                    x=country_df["date"],
                    y=country_df["total_sales"],
                    name=f"{c} Sales",
                    mode="lines+markers",
                    opacity=0.7,
                    line=dict(width=1.5)
                ))
                fig.add_trace(go.Scatter(
                    x=country_df["date"],
                    y=country_df["moving_avg_3_month"],
                    name=f"{c} 3-Month Avg",
                    mode="lines",
                    line=dict(width=3, dash="dot")
                ))
            title = "Sales and 3-Month Moving Average by Country"

        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Sales",
            hovermode="x unified",
        )

        return fig, f"Query executed in {duration} ms"
