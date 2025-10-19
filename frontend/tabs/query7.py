from dash import html, dcc, Input, Output, State
import dash
from dash import dash_table
import plotly.express as px
import pandas as pd
from common import COLORS, make_api_request

# New Query #7 backend contract (/query7):
# Params: country (text, optional), percentile (int, e.g., 10 for Top 10%), year (int), quarter (1-4)
# Returns rows for the selected period only with columns:
# country, period (e.g., '2025-Q1'), rider_id, total_sales, prev_quarter_sales,
# sales_growth_pct, customers_served, sales_percentile


def layout():
    return dcc.Tab(label="Top Riders (Q7)", children=[
        html.Div([
            html.H2("Top Percentile Riders", style={"marginBottom": "16px"}),

            # Filters mapped 1:1 to backend params
            html.Div([
                html.Div([
                    html.Label("Country:"),
                    dcc.Dropdown(
                        id="q7-country",
                        options=[{"label": "Philippines", "value": "Philippines"}],
                        value="Philippines",
                        placeholder="Select country",
                        clearable=False,
                        style={"minWidth": "240px"}
                    ),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "260px"}),

                html.Div([
                    html.Label("Percentile threshold (Top X%):"),
                    dcc.Input(id="q7-percentile", type="number", min=0, max=100, step=1, value=10),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "260px"}),

                html.Div([
                    html.Label("Year:"),
                    dcc.Input(id="q7-year", type="number", placeholder="e.g. 2025", value=2025),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "160px"}),

                html.Div([
                    html.Label("Quarter (1-4):"),
                    dcc.Input(id="q7-quarter", type="number", min=1, max=4, step=1, value=1),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "160px"}),

                html.Button(
                    "Update",
                    id="q7-submit",
                    n_clicks=1,
                    style={
                        "backgroundColor": COLORS["primary"],
                        "color": "white",
                        "border": "none",
                        "padding": "10px 16px",
                        "borderRadius": "6px",
                        "cursor": "pointer",
                        "marginTop": "22px",
                    },
                ),
            ], style={"marginBottom": "16px"}),

            # KPI highlights (no aggregation beyond simple selection)
            html.Div([
                html.Div(id="q7-kpi-cards", style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "12px"}),
            ], style={"marginBottom": "16px"}),

            # Charts
            html.Div([
                dcc.Loading(dcc.Graph(id="q7-bar-total-sales"), type="circle"),
            ], style={"backgroundColor": COLORS['card'], "padding": "12px", "borderRadius": "10px", "marginBottom": "14px"}),

            html.Div([
                dcc.Loading(dcc.Graph(id="q7-scatter-growth"), type="circle"),
            ], style={"backgroundColor": COLORS['card'], "padding": "12px", "borderRadius": "10px", "marginBottom": "14px"}),

            # Raw rows table
            html.Div([
                html.H4("Rider rows (backend output)"),
                dash_table.DataTable(
                    id="q7-table",
                    page_action="native",
                    page_size=20,
                    style_table={"maxHeight": "520px", "overflowY": "auto"},
                    style_header={"backgroundColor": COLORS["primary"], "color": "white", "fontWeight": "bold"},
                    style_cell={"backgroundColor": COLORS["card"], "color": COLORS["text"], "textAlign": "center", "padding": "8px"},
                )
            ])
        ], style={"padding": "20px", "backgroundColor": COLORS["background"], "borderRadius": "10px"})
    ])


def register_callbacks(app):
    # Populate Country dropdown from Query 8 we just get the list of countries any query where country retursn works
    @app.callback(
        Output("q7-country", "options"),
        Input("q7-year", "value"),
        prevent_initial_call=False,
    )
    def load_countries(year):
        rows, _ = make_api_request("query8", {"year": year or 2025})
        df = pd.DataFrame(rows)
        options = [{"label": "Philippines", "value": "Philippines"}]
        if not df.empty and "country" in df.columns:
            mask = (df.get("city").fillna("") == "All Cities") & (df.get("category").fillna("") == "All Categories") & (df.get("country").fillna("") != "Grand Total")
            country_vals = df.loc[mask, "country"].dropna().unique().tolist()

            if "Philippines" not in country_vals:
                country_vals.append("Philippines")
            country_vals = sorted(set(country_vals))
            options = [{"label": c, "value": c} for c in country_vals]
        return options

    @app.callback(
        [
            Output("q7-kpi-cards", "children"),
            Output("q7-bar-total-sales", "figure"),
            Output("q7-scatter-growth", "figure"),
            Output("q7-table", "data"),
            Output("q7-table", "columns"),
        ],
        Input("q7-submit", "n_clicks"),
        State("q7-country", "value"),
        State("q7-percentile", "value"),
        State("q7-year", "value"),
        State("q7-quarter", "value"),
    )
    def update_q7(n_clicks, country, percentile, year, quarter):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        country = country or "Philippines"
        percentile = 10 if (percentile is None or percentile == "") else int(percentile)
        year = 2025 if (year is None or year == "") else int(year)
        quarter = 1 if (quarter is None or quarter == "") else int(quarter)

        params = {
            "country": country,
            "percentile": percentile,
            "year": year,
            "quarter": quarter,
        }

        rows, _ = make_api_request("query7", params)
        df = pd.DataFrame(rows)

        for col in ["total_sales", "prev_quarter_sales", "sales_growth_pct", "customers_served", "sales_percentile"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        def kpi_card(title, value):
            return html.Div([
                html.P(title, style={"margin": 0, "fontWeight": "bold"}),
                html.H3(value if value is not None else "—", style={"margin": 0}),
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"})

        cards = [
            kpi_card("Period", df["period"].iloc[0] if not df.empty and "period" in df.columns else f"{year}-Q{quarter}"),
            kpi_card("Country", country),
            kpi_card("Top Percentile", f"Top {percentile}%"),
        ]

        if not df.empty and "total_sales" in df.columns:
            idx = df["total_sales"].idxmax()
            if idx is not None:
                rid = df.at[idx, "rider_id"] if "rider_id" in df.columns else None
                val = df.at[idx, "total_sales"]
                cards.append(kpi_card("Top Rider by Sales","Rider: " f"{rid} | ${val:,.2f}" if pd.notna(val) else str(rid)))
        if not df.empty and "sales_growth_pct" in df.columns:
            idx = df["sales_growth_pct"].idxmax()
            if idx is not None:
                rid = df.at[idx, "rider_id"] if "rider_id" in df.columns else None
                val = df.at[idx, "sales_growth_pct"]
                cards.append(kpi_card("Best QoQ Growth", "Rider:" f"{rid} | {val:.2f}%" if pd.notna(val) else str(rid)))

        if df.empty:
            bar_fig = px.scatter(title="No data for selection")
            bar_fig.add_annotation(text="No data available", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
            scatter_fig = bar_fig
            table_data, table_cols = [], []
        else:
            plot_df = df.copy()

            if "total_sales" in plot_df.columns:
                plot_df = plot_df.sort_values("total_sales", ascending=False)

            bar_fig = px.bar(
                plot_df,
                x="rider_id",
                y="total_sales",
                color="sales_growth_pct" if "sales_growth_pct" in plot_df.columns else None,
                title="Total Sales by Rider",
                labels={"rider_id": "Rider", "total_sales": "Total Sales", "sales_growth_pct": "QoQ %"},
                text="sales_percentile" if "sales_percentile" in plot_df.columns else None,
            )
            bar_fig.update_traces(texttemplate="%{text:.1f}%" if "sales_percentile" in plot_df.columns else None)
            bar_fig.update_layout(xaxis_title="Rider", yaxis_title="Total Sales")


            scatter_fig = px.scatter(
                plot_df,
                x="prev_quarter_sales" if "prev_quarter_sales" in plot_df.columns else None,
                y="total_sales" if "total_sales" in plot_df.columns else None,
                size="customers_served" if "customers_served" in plot_df.columns else None,
                color="sales_growth_pct" if "sales_growth_pct" in plot_df.columns else None,
                hover_data=[c for c in ["rider_id", "sales_percentile", "period", "country"] if c in plot_df.columns],
                title="Quarter-over-Quarter Performance",
                labels={"prev_quarter_sales": "Prev Quarter", "total_sales": "Current Quarter"},
            )
            scatter_fig.update_layout(xaxis_title="Prev Quarter Sales", yaxis_title="Current Quarter Sales")

            # Table
            table_cols = [{"name": c, "id": c} for c in df.columns]
            table_data = df.to_dict("records")

        return cards, bar_fig, scatter_fig, table_data, table_cols
