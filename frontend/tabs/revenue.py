from dash import html, dcc, Input, Output, State
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
from common import COLORS, make_api_request


def layout():
    return dcc.Tab(label="Revenue Trends", children=[
        html.Div([
            html.H2("Revenue Over Time"),
            html.Div([
                html.Div([
                    html.Label("Start Date:"),
                    dcc.DatePickerSingle(
                        id="q1-start-date",
                        date=datetime(2024, 1, 1),
                        display_format='YYYY-MM-DD',
                    ),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Div([
                    html.Label("End Date:"),
                    dcc.DatePickerSingle(
                        id="q1-end-date",
                        date=datetime(2024, 12, 31),
                        display_format='YYYY-MM-DD',
                    ),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Div([
                    html.Label("Category:"),
                    dcc.Input(id="q1-category", type="text", placeholder="Leave empty for all"),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Div([
                    html.Label("Granularity:"),
                    dcc.Dropdown(
                        id="q1-granularity",
                        options=[
                            {"label": "Year", "value": "year"},
                            {"label": "Month", "value": "month"},
                            {"label": "Day", "value": "day"},
                        ],
                        value="month",
                        clearable=False,
                        style={"width": "120px"}
                    ),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Button("Update", id="q1-submit-btn", n_clicks=0,
                            style={'backgroundColor': COLORS['primary'], 'color': 'white',
                                   'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
            ], style={"marginBottom": "20px"}),

            html.Div([
                dcc.Loading(
                    dcc.Graph(id="revenue-graph"),
                    type="circle"
                ),
            ], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),

            html.Div(id="q1-query-time", style={'marginTop': '10px', 'fontStyle': 'italic'})
        ], style={"padding": "20px"})
    ])


def register_callbacks(app):
    @app.callback(
        [Output("revenue-graph", "figure"), Output("q1-query-time", "children")],
        Input("q1-submit-btn", "n_clicks"),
        State("q1-start-date", "date"),
        State("q1-end-date", "date"),
        State("q1-category", "value"),
        State("q1-granularity", "value"),
    )
    def update_revenue_graph(n_clicks, start, end, category, granularity):
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

        data, duration = make_api_request("query1", params)

        df = pd.DataFrame(data) if data else pd.DataFrame({"period": [], "revenue": [], "units_sold": []})

        if df.empty:
            fig = go.Figure().add_annotation(
                text="No data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig, ""

        # Convert revenue to numeric
        df["revenue"] = pd.to_numeric(df["revenue"])
        df["units_sold"] = pd.to_numeric(df["units_sold"])

        # Create combo chart: line for revenue, bar for units
        fig = go.Figure()

        # Add revenue line
        fig.add_trace(go.Scatter(
            x=df["period"],
            y=df["revenue"],
            name="Revenue",
            line=dict(color=COLORS['primary'], width=3),
            mode="lines+markers"
        ))

        # Add units sold as bars on secondary y-axis
        fig.add_trace(go.Bar(
            x=df["period"],
            y=df["units_sold"],
            name="Units Sold",
            opacity=0.6,
            marker_color=COLORS['secondary'],
            yaxis="y2"
        ))

        # Update layout with dual y-axes
        fig.update_layout(
            title=f"Revenue Over Time ({granularity.capitalize()})",
            xaxis_title="Period",
            yaxis_title="Revenue",
            yaxis2=dict(
                title="Units Sold",
                overlaying="y",
                side="right",
                showgrid=False
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5
            ),
            hovermode="x unified",
        )

        return fig, f"Query executed in {duration} ms"
