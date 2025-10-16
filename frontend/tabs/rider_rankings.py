from dash import html, dcc, Input, Output, State
import plotly.express as px
import pandas as pd
from common import COLORS, make_api_request


def layout():
    return dcc.Tab(label="Rider Rankings", children=[
        html.Div([
            html.H2("Rider Rankings by Deliveries"),
            html.Div([
                html.Div([
                    html.Label("Country:"),
                    dcc.Input(id="q5-country", type="text", placeholder="Leave empty for all countries"),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Button("Update", id="q5-submit-btn", n_clicks=0,
                           style={'backgroundColor': COLORS['primary'], 'color': 'white',
                                  'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
            ], style={"marginBottom": "20px"}),

            html.Div([
                dcc.Loading(
                    dcc.Graph(id="rider-ranking-graph"),
                    type="circle"
                ),
            ], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),

            html.Div(id="q5-query-time", style={'marginTop': '10px', 'fontStyle': 'italic'})
        ], style={"padding": "20px"})
    ])


def register_callbacks(app):
    @app.callback(
        [Output("rider-ranking-graph", "figure"), Output("q5-query-time", "children")],
        Input("q5-submit-btn", "n_clicks"),
        State("q5-country", "value"),
    )
    def update_rider_ranking(n_clicks, country):
        params = {
            "country": country if country else None,
        }

        data, duration = make_api_request("query5", params)

        df = pd.DataFrame(data) if data else pd.DataFrame({
            "country": [], "rider_id": [], "courier_name": [], 
            "total_deliveries": [], "delivery_rank": []
        })

        if df.empty:
            fig = px.scatter(title="No data available")
            fig.add_annotation(text="No data available", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
            return fig, ""

        for col in ["total_deliveries", "delivery_rank"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])

        df = df.sort_values("delivery_rank").head(20)

        if "country" in df.columns and len(df["country"].unique()) > 1:
            fig = px.bar(
                df,
                y="courier_name",
                x="total_deliveries",
                color="country",
                orientation='h',
                text="delivery_rank",
                title=f"Top Riders by Delivery Count" + (f" in {country}" if country else ""),
                hover_data=["delivery_rank"],
                labels={"delivery_rank": "Rank"}
            )
        else:
            fig = px.bar(
                df,
                y="courier_name",
                x="total_deliveries",
                orientation='h',
                text="delivery_rank",
                title=f"Top Riders by Delivery Count" + (f" in {country}" if country else ""),
                hover_data=["delivery_rank"],
                labels={"delivery_rank": "Rank"},
                color_discrete_sequence=[COLORS['primary']]
            )

        fig.update_traces(texttemplate="Rank: %{text}", textposition="inside")
        fig.update_layout(
            yaxis_title="Courier",
            xaxis_title="Total Deliveries",
            height=max(500, len(df)*30),
            yaxis={'categoryorder': 'total ascending'}
        )

        return fig, f"Query executed in {duration} ms"
