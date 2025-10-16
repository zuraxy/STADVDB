from dash import html, dcc, Input, Output, State
from dash import dash_table
import dash
import pandas as pd
import plotly.express as px
from common import COLORS, make_api_request

px.defaults.template = "plotly_white"

def layout():
    return dcc.Tab(
        label="Flexible Summary Report",
        children=[
            html.Div(
                [
                    html.H2("🧮 Sales Summary Report", style={"marginBottom": "20px"}),

                    html.Div(
                        [
                            html.Div([
                                html.Label("Year:"),
                                dcc.Input(id="q8-year", type="number", placeholder="e.g. 2025"),
                            ], style={"flex": "1"}),

                            html.Div([
                                html.Label("Country:"),
                                dcc.Input(id="q8-country", type="text", placeholder="Leave blank for all"),
                            ], style={"flex": "1"}),

                            html.Div([
                                html.Label("City:"),
                                dcc.Input(id="q8-city", type="text", placeholder="Leave blank for all"),
                            ], style={"flex": "1"}),

                            html.Div([
                                html.Label("Category:"),
                                dcc.Input(id="q8-category", type="text", placeholder="Leave blank for all"),
                            ], style={"flex": "1"}),

                            html.Button(
                                "Update",
                                id="q8-update",
                                n_clicks=0,
                                style={
                                    "backgroundColor": COLORS["primary"],
                                    "color": "white",
                                    "border": "none",
                                    "padding": "10px 20px",
                                    "borderRadius": "8px",
                                    "cursor": "pointer",
                                },
                            ),
                        ],
                        style={"display": "flex", "gap": "15px", "marginBottom": "20px"},
                    ),

                    html.Div(
                        id="q8-summary-cards",
                        style={"display": "flex", "gap": "20px", "marginBottom": "20px"},
                    ),

                    html.Div(
                        [
                            dcc.Loading(
                                id="q8-loading",
                                type="circle",
                                color=COLORS["primary"],
                                children=[
                                    dash_table.DataTable(
                                        id="q8-table",
                                        style_table={"height": "500px", "overflowY": "auto"},
                                        page_action="none",
                                        virtualization=True,
                                        fixed_rows={"headers": True},
                                        style_header={
                                            "backgroundColor": COLORS["primary"],
                                            "color": "white",
                                            "fontWeight": "bold",
                                        },
                                        style_cell={
                                            "backgroundColor": COLORS["card"],
                                            "color": COLORS["text"],
                                            "fontSize": "14px",
                                            "padding": "8px",
                                            "textAlign": "center",
                                        },
                                    )
                                ],
                            ),
                        ],
                        style={"marginBottom": "30px"},
                    ),

                    html.Div(id="q8-graph-section"),
                ],
                style={"padding": "20px", "backgroundColor": COLORS["background"], "borderRadius": "12px"},
            )
        ],
    )


def register_callbacks(app):
    @app.callback(
        [
            Output("q8-summary-cards", "children"),
            Output("q8-table", "data"),
            Output("q8-table", "columns"),
            Output("q8-graph-section", "children"),
        ],
        Input("q8-update", "n_clicks"),
        State("q8-year", "value"),
        State("q8-country", "value"),
        State("q8-city", "value"),
        State("q8-category", "value"),
    )
    def update_summary(n_clicks, year, country, city, category):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        params = {"year": year, "country": country, "city": city, "category": category}
        rows, _duration = make_api_request("query8", params)
        df = pd.DataFrame(rows)

        if df.empty:
            return html.Div("No data available."), [], [], html.Div("")

        # Ensure numeric conversions
        for col in ("total_revenue", "unique_riders"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Summary cards
        total_rev = float(df.get("total_revenue", pd.Series([0])).sum())
        total_riders = int(df.get("unique_riders", pd.Series([0])).sum())
        avg_rev = total_rev / len(df) if len(df) > 0 else 0

        summary_cards = [
            html.Div(
                [html.H4("💰 Total Revenue"), html.H3(f"${total_rev:,.2f}")],
                style={
                    "backgroundColor": COLORS["card"],
                    "padding": "15px",
                    "borderRadius": "10px",
                    "flex": "1",
                    "textAlign": "center",
                    "boxShadow": "0 2px 5px rgba(0,0,0,0.1)",
                },
            ),
            html.Div(
                [html.H4("🚴 Unique Riders"), html.H3(f"{total_riders:,}")],
                style={
                    "backgroundColor": COLORS["card"],
                    "padding": "15px",
                    "borderRadius": "10px",
                    "flex": "1",
                    "textAlign": "center",
                    "boxShadow": "0 2px 5px rgba(0,0,0,0.1)",
                },
            ),
            html.Div(
                [html.H4("📊 Avg Revenue per Entry"), html.H3(f"${avg_rev:,.2f}")],
                style={
                    "backgroundColor": COLORS["card"],
                    "padding": "15px",
                    "borderRadius": "10px",
                    "flex": "1",
                    "textAlign": "center",
                    "boxShadow": "0 2px 5px rgba(0,0,0,0.1)",
                },
            ),
        ]

        # Table
        columns = [{"name": i, "id": i} for i in df.columns]
        data = df.to_dict("records")

        # Graph
        if "country" in df.columns and "total_revenue" in df.columns:
            grouped = df.groupby("country", as_index=False)["total_revenue"].sum()
            fig = px.bar(
                grouped,
                x="country",
                y="total_revenue",
                title="Total Revenue by Country",
                color_discrete_sequence=[COLORS["primary"]],
            )
            fig.update_layout(
                paper_bgcolor=COLORS["card"],
                plot_bgcolor=COLORS["card"],
                font_color=COLORS["text"],
                xaxis_title="Country",
                yaxis_title="Revenue",
                height=500,
            )
            graph_section = dcc.Graph(figure=fig)
        else:
            graph_section = html.Div("No graphable data.")

        return summary_cards, data, columns, graph_section