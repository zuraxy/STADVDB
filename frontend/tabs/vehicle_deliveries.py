from dash import html, dcc, Input, Output, State, dash_table
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from common import COLORS, make_api_request


def layout():
    return dcc.Tab(label="Vehicle Deliveries", children=[
        html.Div([
            html.H2("Deliveries by Vehicle Type"),
            html.Div([
                html.Div([
                    html.Label("Year:"),
                    dcc.Input(
                        id="q6-year",
                        type="number",
                        placeholder="Leave empty for all years",
                        style={"width": "180px", "height": "36px", "paddingLeft": "10px"}
                    ),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),
                html.Div([
                    html.Label("Month:"),
                    dcc.Dropdown(
                        id="q6-month",
                        options=[
                            {"label": "All Months", "value": ""},
                            {"label": "January", "value": "1"},
                            {"label": "February", "value": "2"},
                            {"label": "March", "value": "3"},
                            {"label": "April", "value": "4"},
                            {"label": "May", "value": "5"},
                            {"label": "June", "value": "6"},
                            {"label": "July", "value": "7"},
                            {"label": "August", "value": "8"},
                            {"label": "September", "value": "9"},
                            {"label": "October", "value": "10"},
                            {"label": "November", "value": "11"},
                            {"label": "December", "value": "12"},
                        ],
                        value="",
                        clearable=False,
                        style={"width": "200px"}
                    ),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),
                html.Div([
                    html.Label("Chart Type:"),
                    dcc.RadioItems(
                        id="q6-chart-type",
                        options=[
                            {"label": "Stacked Bar", "value": "stacked_bar"},
                            {"label": "Grouped Bar", "value": "grouped_bar"},
                            {"label": "Stacked Area", "value": "stacked_area"},
                        ],
                        value="stacked_bar",
                        labelStyle={'display': 'inline-block', 'marginRight': '15px'}
                    )
                ], style={'display': 'inline-block', 'marginRight': '20px', 'verticalAlign': 'top'}),
                html.Button("Update", id="q6-submit-btn", n_clicks=0,
                            style={'backgroundColor': COLORS['primary'], 'color': 'white',
                                   'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
            ], style={"marginBottom": "20px"}),
            html.Div([
                dcc.Loading(
                    dcc.Graph(id="vehicle-deliveries-graph"),
                    type="circle"
                ),
            ], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px',
                      'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),
            html.Div(id="q6-summary", style={'marginTop': '20px'}),
            html.Div(id="q6-query-time", style={'marginTop': '10px', 'fontStyle': 'italic'})
        ], style={"padding": "20px"})
    ])


def register_callbacks(app):
    @app.callback(
        [Output("vehicle-deliveries-graph", "figure"),
         Output("q6-summary", "children"),
         Output("q6-query-time", "children")],
        Input("q6-submit-btn", "n_clicks"),
        State("q6-year", "value"),
        State("q6-month", "value"),
        State("q6-chart-type", "value"),
    )
    def update_vehicle_deliveries(n_clicks, year, month, chart_type):
        params = {
            "year": year if year else None,
            "month": month if month else None,
        }
        data, duration = make_api_request("query6", params)

        df = pd.DataFrame(data) if data else pd.DataFrame({
            "year": [], "month": [], "vehicle_type": [], "total_deliveries": []
        })

        if df.empty:
            fig = go.Figure().add_annotation(
                text="No data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig, "", f"Query executed in {duration} ms"

        df["total_deliveries"] = pd.to_numeric(df["total_deliveries"], errors="coerce").fillna(0)

        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        if "month" in df.columns:
            df["month"] = pd.to_numeric(df["month"], errors="coerce")
        else:
            df["month"] = pd.NA

        df = df[~df["year"].isna()]
        df["year"] = df["year"].astype(int)
        df["period"] = df.apply(
            lambda r: f"{r['year']}-{int(r['month']):02d}" if pd.notna(r["month"]) and r["month"] > 0 else f"{r['year']}",
            axis=1
        )

        df_plot = df[~df["vehicle_type"].isna()].copy()

        if df_plot.empty:
            fig = go.Figure().add_annotation(
                text="No vehicle-level rows",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig, "", f"Query executed in {duration} ms"

        df_plot["month_sort"] = df_plot["month"].fillna(0).astype(int)
        df_plot = df_plot.sort_values(["year", "month_sort", "vehicle_type"])

        title_suffix = ""
        if year:
            title_suffix += f" in {year}"
        if month:
            title_suffix += f", Month {month}"

        ordered_periods = df_plot["period"].unique().tolist()

        if chart_type == "stacked_area":
            fig = px.area(
                df_plot,
                x="period",
                y="total_deliveries",
                color="vehicle_type",
                title=f"Deliveries by Vehicle Type (Stacked Area){title_suffix}",
            )
        elif chart_type == "grouped_bar":
            fig = px.bar(
                df_plot,
                x="period",
                y="total_deliveries",
                color="vehicle_type",
                barmode="group",
                title=f"Deliveries by Vehicle Type (Grouped){title_suffix}",
            )
        else:
            fig = px.bar(
                df_plot,
                x="period",
                y="total_deliveries",
                color="vehicle_type",
                barmode="stack",
                title=f"Deliveries by Vehicle Type (Stacked){title_suffix}",
            )

        fig.update_layout(
            xaxis_title="Period",
            yaxis_title="Total Deliveries",
            legend_title="Vehicle Type",
            hovermode="x unified",
        )
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=ordered_periods)

        summary_df = (
            df_plot.groupby("vehicle_type", as_index=False)["total_deliveries"].sum()
            .sort_values("total_deliveries", ascending=False)
        )
        grand_total = summary_df["total_deliveries"].sum()
        summary_df["percent"] = (summary_df["total_deliveries"] / grand_total * 100).round(2)

        summary_table = dash_table.DataTable(
            columns=[
                {"name": "Vehicle Type", "id": "vehicle_type"},
                {"name": "Deliveries", "id": "total_deliveries", "type": "numeric"},
                {"name": "Percent (%)", "id": "percent", "type": "numeric"},
            ],
            data=summary_df.to_dict("records"),
            style_header={'backgroundColor': COLORS['primary'], 'color': 'white', 'fontWeight': 'bold'},
            style_cell={'padding': '6px', 'textAlign': 'center'},
            style_data={'backgroundColor': COLORS['card']},
            style_table={'maxWidth': '650px'},
        )

        summary_container = html.Div(
            [
                html.H4("Total Deliveries Share by Vehicle Type"),
                summary_table,
                html.Div(f"Grand Total: {int(grand_total):,} deliveries", style={'marginTop': '8px', 'fontStyle': 'italic'})
            ],
            style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px',
                   'boxShadow': '0px 0px 10px rgba(0,0,0,0.05)'}
        )

        return fig, summary_container, f"Query executed in {duration} ms"
