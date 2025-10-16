from dash import html, dcc, Input, Output, State
import dash
from dash import dash_table
import pandas as pd
import plotly.express as px
from common import COLORS, make_api_request

# Use a safe template
px.defaults.template = "plotly_white"


def layout():
    return dcc.Tab(label="Top Riders (Q7)", children=[
        html.Div([
            html.H2("Top Riders Analytical Report", style={"marginBottom": "16px"}),

            # Filters (Slice & Dice) - mirror backend parameters exactly
            html.Div([
                html.Div([
                    html.Label("Country:"),
                    dcc.Input(id="q7-country", type="text", placeholder="Leave empty for all"),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "220px"}),

                html.Div([
                    html.Label("City:"),
                    dcc.Input(id="q7-city", type="text", placeholder="Leave empty for all"),
                ], style={"display": "inline-block", "marginRight": "16px", "minWidth": "220px"}),

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
                    n_clicks=0,
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
            ], style={"marginBottom": "20px"}),

            # KPI Cards
            html.Div(id="q7-kpis", style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),

            # Leaderboard + details
            html.Div([
                html.Div([
                    dcc.Graph(id="q7-leaderboard")
                ], style={"width": "52%", "display": "inline-block", "verticalAlign": "top"}),

                html.Div([
                    html.H4("Rider Details"),
                    dash_table.DataTable(
                        id="q7-table",
                        page_action="none",
                        virtualization=True,
                        style_table={"height": "520px", "overflowY": "auto"},
                        style_header={"backgroundColor": COLORS["primary"], "color": "white", "fontWeight": "bold"},
                        style_cell={"backgroundColor": COLORS["card"], "color": COLORS["text"], "textAlign": "center", "padding": "8px"},
                    )
                ], style={"width": "46%", "display": "inline-block", "marginLeft": "2%", "verticalAlign": "top"}),
            ])
        ], style={"padding": "20px", "backgroundColor": COLORS["background"], "borderRadius": "10px"})
    ])


def register_callbacks(app):
    # Populate categories dropdown from backend (reuse query9 which includes category column)
    @app.callback(
        Output("q7-category", "options"),
        Input("q7-category", "id"),  # dummy input to trigger once
        prevent_initial_call=False
    )
    def load_categories(_):
        # Attempt to fetch categories using a lightweight call
        rows, _ = make_api_request("query9", {"year": None, "country": None, "city": None, "category": None})
        df = pd.DataFrame(rows)
        if "category" in df.columns:
            cats = [c for c in df["category"].dropna().unique().tolist() if str(c).strip() and str(c).lower() != "all categories"]
            cats.sort()
            return [{"label": c, "value": c} for c in cats]
        return []

    @app.callback(
        [
            Output("q7-kpis", "children"),
            Output("q7-leaderboard", "figure"),
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
                html.P("Total Sales from Top Riders", style={"margin": 0, "fontWeight": "bold"}),
                html.H3(f"${total_sales_sum:,.2f}", style={"margin": 0})
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "flex": 1, "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"}),
            html.Div([
                html.P("Top Performing Rider", style={"margin": 0, "fontWeight": "bold"}),
                html.H3(f"{top_rider_name}", style={"margin": 0}),
                html.P(f"${top_rider_sales:,.2f}", style={"margin": 0, "color": "#555"}),
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "flex": 1, "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"}),
            html.Div([
                html.P("Avg. Customers Served of Riders", style={"margin": 0, "fontWeight": "bold"}),
                html.H3(f"{avg_customers_served:,.0f}", style={"margin": 0})
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "flex": 1, "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"}),
            html.Div([
                html.P("Count of Elite Riders", style={"margin": 0, "fontWeight": "bold"}),
                html.H3(f"{elite_count:,}", style={"margin": 0})
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "flex": 1, "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"}),
            html.Div([
                html.P("Top Rider by Deliveries", style={"margin": 0, "fontWeight": "bold"}),
                html.H3(f"{top_deliveries_name}", style={"margin": 0}),
                html.P(f"{top_deliveries_count:,} deliveries", style={"margin": 0, "color": "#555"}),
            ], style={"backgroundColor": COLORS["card"], "padding": "14px", "borderRadius": "8px", "flex": 1, "textAlign": "center", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)"}),
        ]

        # Leaderboard - simple y=courier_name, limit hover to name + total sales
        if not df.empty and "courier_name" in df.columns and "total_sales" in df.columns:
            df_disp = df.copy()
            # Order by total_sales descending so top appears first
            df_disp = df_disp.sort_values("total_sales", ascending=False)

            # Create ordinal rank labels based on total_sales (highest = 1st)
            def ordinal(n: int) -> str:
                return "%d%s" % (n, "th" if 11 <= (n % 100) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))

            sales_numeric = pd.to_numeric(df_disp["total_sales"], errors="coerce")
            ranks = sales_numeric.rank(method="dense", ascending=False).astype("Int64")
            df_disp["rank_label"] = ranks.apply(lambda x: ordinal(int(x)) if pd.notna(x) else "")

            fig = px.bar(
                df_disp,
                y="courier_name",
                x="total_sales",
                orientation="h",
                color="vehicle_type" if "vehicle_type" in df_disp.columns else None,
                text="rank_label",
                title="Top Rider Leaderboard (by Total Sales)",
                template="plotly_white",
            )
            fig.update_traces(textposition="outside")
            # Show only name and total sales in hover
            fig.update_traces(hovertemplate="Rider: %{y}<br>Total Sales: %{x:$,.2f}<extra></extra>")
            fig.update_layout(
                yaxis_title="Rider",
                xaxis_title="Total Sales",
            )
        else:
            fig = px.bar(title="No data available")

        # Rider Details table: limit to top 10 by total_sales
        if not df.empty and "total_sales" in df.columns:
            df_top10 = df.sort_values("total_sales", ascending=False).head(10)
        else:
            df_top10 = df.head(10)

        table_columns = [{"name": c, "id": c} for c in df_top10.columns]
        table_data = df_top10.to_dict("records")

        return kpis, fig, table_data, table_columns
