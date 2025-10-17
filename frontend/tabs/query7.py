from dash import html, dcc, Input, Output, State
import dash
from dash import dash_table
import pandas as pd
from common import COLORS, make_api_request

# Query #7 -> Top percentile riders by sales with regional analysis and quarter-over-quarter growth
# Backend /query7 expects query params mapping to the SQL placeholders:
# $1::text -> country (optional, pass NULL for all countries, e.g., 'Philippines')
# $2::text -> city (optional, pass NULL for all cities, e.g., 'Canton')
# $3::text -> category (optional, pass NULL for all categories, e.g., 'Electronics')
# $4::int  -> percentile_threshold (sent as `percentile`, e.g., 90 for top 10%, 80 for top 20%)
# $5::int  -> year (e.g., 2024)
# $6::int  -> quarter (e.g., 4 for Q4)


def layout():
    return dcc.Tab(label="Top Riders (Q7)", children=[
        html.Div([
            html.H2("Top Riders Analytical Report", style={"marginBottom": "16px"}),

            # Filters (Slice & Dice) - mirror backend parameters exactly
            html.Div([
                html.Div([
                    html.Label("Country:"),
                    dcc.Dropdown(
                        id="q7-country",
                        options=[],
                        value=None,
                        placeholder="All countries",
                        clearable=True,
                        style={"minWidth": "240px"}
                    ),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "260px"}),

                html.Div([
                    html.Label("City:"),
                    dcc.Dropdown(
                        id="q7-city",
                        options=[],
                        value=None,
                        placeholder="All cities",
                        clearable=True,
                        style={"minWidth": "240px"}
                    ),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "260px"}),

                html.Div([
                    html.Label("Category:"),
                    dcc.Dropdown(
                        id="q7-category",
                        options=[],
                        value=None,
                        placeholder="Select a category (optional)",
                        clearable=True,
                        style={"minWidth": "220px"}
                    ),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "240px"}),

                html.Div([
                    html.Label("Percentile Threshold (e.g., 90 = Top 10%):"),
                    dcc.Input(id="q7-percentile", type="number", min=0, max=100, step=1, value=90),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "280px"}),

                html.Div([
                    html.Label("Year:"),
                    dcc.Input(id="q7-year", type="number", placeholder="e.g. 2024", value=2024),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "160px"}),

                html.Div([
                    html.Label("Quarter (1-4):"),
                    dcc.Input(id="q7-quarter", type="number", min=1, max=4, step=1, value=4),
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
                        "marginRight": "8px",
                    },
                ),
                html.Button(
                    "Back",
                    id="q7-back",
                    n_clicks=0,
                    style={
                        "backgroundColor": COLORS["secondary"],
                        "color": "white",
                        "border": "none",
                        "padding": "10px 16px",
                        "borderRadius": "6px",
                        "cursor": "pointer",
                        "marginTop": "22px",
                    },
                ),
            ], style={"marginBottom": "20px"}),

            # Top riders by metric (now above KPI cards)
            html.Div([
                html.H4("Top Riders by Metric"),
                html.Div(id="q7-top-metrics", style={"display": "grid", "gridTemplateColumns": "repeat(2, 1fr)", "gap": "12px"}),
            ], style={"marginBottom": "16px"}),

            # KPI Cards (trimmed)
            html.Div(id="q7-kpis", style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),

            # Rider details table (full width)
            html.Div([
                html.H4("Rider Details"),
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
    # Populate categories dropdown from backend using query8 (returns a category column)
    @app.callback(
        Output("q7-category", "options"),
        Input("q7-year", "value"),
        prevent_initial_call=False
    )
    def load_categories(year):
        # Fetch available categories for the selected year
        params = {"year": year} if year is not None else {"year": 2025}
        rows, _ = make_api_request("query8", params)
        df = pd.DataFrame(rows)
        if "category" in df.columns:
            cats = [c for c in df["category"].dropna().unique().tolist() if str(c).strip() and str(c).lower() != "all categories"]
            cats.sort()
            return [{"label": c, "value": c} for c in cats]
        return []

    # Populate Country/City options using Query 8 (no extra aggregation)
    @app.callback(
        [Output("q7-country", "options"), Output("q7-city", "options")],
        [Input("q7-year", "value"), Input("q7-country", "value")],
        prevent_initial_call=False,
    )
    def load_countries_cities(year, country):
        rows, _ = make_api_request("query8", {"year": year, "country": country or None, "city": None, "category": None})
        df = pd.DataFrame(rows)
        country_opts = []
        city_opts = []
        if not df.empty:
            # Countries: rollup rows (All Cities, All Categories), excluding Grand Total
            df_num = df.copy()
            if "total_revenue" in df_num.columns:
                df_num["total_revenue"] = pd.to_numeric(df_num["total_revenue"], errors="coerce")
            countries = df[(df["city"] == "All Cities") & (df["category"] == "All Categories") & (df["country"] != "Grand Total")]["country"].dropna().unique().tolist()
            country_opts = [{"label": c, "value": c} for c in sorted(countries)]
            # Cities: rollup city totals at All Categories for selected country
            if country:
                cities = df[(df["country"] == country) & (df["city"] != "All Cities") & (df["category"] == "All Categories")]["city"].dropna().unique().tolist()
                city_opts = [{"label": c, "value": c} for c in sorted(cities)]
        return country_opts, city_opts

    # Back button: clear city, then country
    @app.callback(
        [Output("q7-city", "value"), Output("q7-country", "value")],
        Input("q7-back", "n_clicks"),
        State("q7-city", "value"),
        State("q7-country", "value"),
        prevent_initial_call=True,
    )
    def back_drill(n, city, country):
        if not n:
            raise dash.exceptions.PreventUpdate
        if city:
            return None, country
        if country:
            return None, None
        raise dash.exceptions.PreventUpdate

    @app.callback(
        [
            Output("q7-kpis", "children"),
            Output("q7-top-metrics", "children"),
            Output("q7-table", "data"),
            Output("q7-table", "columns"),
        ],
        Input("q7-submit", "n_clicks"),
        State("q7-country", "value"),
        State("q7-city", "value"),
        State("q7-category", "value"),
        State("q7-percentile", "value"),
        State("q7-year", "value"),
        State("q7-quarter", "value"),
    )
    def update_q7(n_clicks, country, city, category, percentile, year, quarter):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        params = {
            "country": country if country else None,
            "city": city if city else None,
            "category": category if category else None,
            "percentile": percentile if percentile is not None else 90,
            "year": year,
            "quarter": quarter,
        }
        # Drop None-valued keys to avoid sending literal "None" strings to backend
        params = {k: v for k, v in params.items() if v is not None}

        rows, _ = make_api_request("query7", params)
        df = pd.DataFrame(rows)

        # Ensure fields are present and numeric where needed; no extra aggregations beyond formatting
        for col in [
            "total_sales", "avg_order_value", "customers_served", "sales_percentile", "sales_growth_pct"
        ]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # KPI Scorecards (formatting only based on returned rows)
        total_sales_sum = float(df["total_sales"].sum()) if "total_sales" in df.columns else 0.0
        # Top performing rider from returned rows (no extra aggregation)
        top_rider_name = "—"
        top_rider_sales = 0.0
        if not df.empty and "courier_name" in df.columns and "total_sales" in df.columns:
            s = pd.to_numeric(df["total_sales"], errors="coerce")
            if s.notna().any():
                top_idx = s.idxmax()
                top_rider_name = str(df.at[top_idx, "courier_name"]) if top_idx in df.index else "—"
                try:
                    top_rider_sales = float(s.at[top_idx])
                except Exception:
                    top_rider_sales = 0.0
        avg_customers_served = float(df["customers_served"].mean()) if "customers_served" in df.columns and len(df) else 0.0
        elite_count = int(df["rider_id"].nunique()) if "rider_id" in df.columns else 0

        # Derive deliveries count per rider row using SUM/AVG relationship: count ≈ total_sales / avg_order_value
        # This avoids extra aggregation and uses only fields returned by backend QUERY7
        top_deliveries_name = "—"
        top_deliveries_count = 0
        if "total_sales" in df.columns and "avg_order_value" in df.columns and not df.empty:
            ts = pd.to_numeric(df["total_sales"], errors="coerce")
            aov = pd.to_numeric(df["avg_order_value"], errors="coerce")
            deliveries_calc = (ts / aov).where((aov > 0) & ts.notna() & aov.notna())
            if deliveries_calc.notna().any():
                # Round to nearest whole delivery
                deliveries_calc = deliveries_calc.round()
                max_idx = deliveries_calc.idxmax()
                if max_idx in df.index:
                    top_deliveries_count = int(deliveries_calc.at[max_idx]) if pd.notna(deliveries_calc.at[max_idx]) else 0
                    if "courier_name" in df.columns:
                        top_deliveries_name = str(df.at[max_idx, "courier_name"]) or "—"

        kpis = [
            html.Div([
                html.P("Avg. Customers Served of Riders", style={"margin": 0, "fontWeight": "bold"}),
                html.H3(f"{avg_customers_served:,.0f}", style={"margin": 0})
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "flex": 1, "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"}),
        ]

        # Build Top Metrics cards
        def metric_card(title, name, value_fmt):
            return html.Div([
                html.P(title, style={"margin": 0, "fontWeight": "bold"}),
                html.H3(name or "—", style={"margin": 0}),
                html.P(value_fmt, style={"margin": 0, "color": "#555"}),
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"})

        def top_by(col):
            if col in df.columns and not df.empty:
                s = pd.to_numeric(df[col], errors="coerce")
                if s.notna().any():
                    idx = s.idxmax()
                    rider_name = str(df.at[idx, "courier_name"]) if "courier_name" in df.columns and idx in df.index else "—"
                    rider_id = str(df.at[idx, "rider_id"]) if "rider_id" in df.columns and idx in df.index else "—"
                    rider = f"{rider_name} (ID: {rider_id})" if rider_name != "—" and rider_id != "—" else rider_name
                    val = s.at[idx] if pd.notna(s.at[idx]) else None
                    return rider, val
            return "—", None

        ts_name, ts_val = top_by("total_sales")
        aov_name, aov_val = top_by("avg_order_value")
        cs_name, cs_val = top_by("customers_served")
        growth_name, growth_val = top_by("sales_growth_pct")

        top_metrics = [
            metric_card("Highest Total Sales Rider", ts_name, (f"${ts_val:,.2f}" if ts_val is not None else "—")),
            metric_card("Highest Average Order Value Rider", aov_name, (f"${aov_val:,.2f}" if aov_val is not None else "—")),
            metric_card("Most Customers Served Rider", cs_name, (f"{int(cs_val):,}" if cs_val is not None else "—")),
            metric_card("Fastest Growing Rider (QoQ)", growth_name, (f"{growth_val:.2f}%" if growth_val is not None else "—")),
        ]

        # Rider Details table: show all returned rows (paginated by DataTable)
        table_df = df.copy()
        table_columns = [{"name": c, "id": c} for c in table_df.columns]
        table_data = table_df.to_dict("records")

        return kpis, top_metrics, table_data, table_columns
