from dash import html, dcc, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from common import COLORS, make_api_request

# Ensure a stable built-in template to avoid issues with custom/default templates
px.defaults.template = "plotly_white"


def layout():
    return dcc.Tab(label="Top Products", children=[
        html.Div([
            html.H2("Top Products by Revenue"),
            html.Div([
                html.Div([
                    html.Label("Top N products:"),
                    dcc.Input(id="q3-top-n", type="number", value=10, min=1, max=100),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Div([
                    html.Label("Country:"),
                    dcc.Input(id="q3-country", type="text", placeholder="Leave empty for all"),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Div([
                    html.Label("City:"),
                    dcc.Input(id="q3-city", type="text", placeholder="Leave empty for all"),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Div([
                    html.Label("Category:"),
                    dcc.Input(id="q3-category", type="text", placeholder="Leave empty for all"),
                ], style={'display': 'inline-block', 'marginRight': '20px'}),

                html.Button("Update", id="q3-submit-btn", n_clicks=0,
                           style={'backgroundColor': COLORS['primary'], 'color': 'white',
                                  'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
            ], style={"marginBottom": "20px"}),

            html.Div([
                dcc.Loading(
                    dcc.Graph(id="top-products-graph"),
                    type="circle"
                ),
            ], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),

            html.Div(id="q3-query-time", style={'marginTop': '10px', 'fontStyle': 'italic'})
        ], style={"padding": "20px"})
    ])


def register_callbacks(app):
    @app.callback(
        [Output("top-products-graph", "figure"), Output("q3-query-time", "children")],
        Input("q3-submit-btn", "n_clicks"),
        State("q3-top-n", "value"),
        State("q3-country", "value"),
        State("q3-city", "value"),
        State("q3-category", "value"),
    )
    def update_top_products(n_clicks, top_n, country, city, category):
        top_n = top_n or 10
        params = {
            "no": top_n,
            "country": country if country else None,
            "city": city if city else None,
            "category": category if category else None,
        }

        data, duration = make_api_request("query3", params)

        df = pd.DataFrame(data) if data else pd.DataFrame({"product_name": [], "total_sales": []})

        if df.empty:
            fig = go.Figure().add_annotation(
                text="No data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig, ""

        df["total_sales"] = pd.to_numeric(df["total_sales"])
        if "total_quantity_sold" in df.columns:
            df["total_quantity_sold"] = pd.to_numeric(df["total_quantity_sold"])

        df = df.sort_values("total_sales", ascending=True)

        if len(df) > top_n:
            df = df.tail(top_n)

        fig = px.bar(
            df,
            y="product_name",
            x="total_sales",
            color="category" if "category" in df.columns else None,
            orientation='h',
            title=f"Top {top_n} Products by Revenue" + 
                  (f" in {country}" if country else "") +
                  (f", {city}" if city else "") +
                  (f" (Category: {category})" if category else ""),
            hover_data=["total_quantity_sold"] if "total_quantity_sold" in df.columns else None,
            color_discrete_sequence=px.colors.qualitative.Pastel,
            template="plotly_white",
        )

        fig.update_layout(
            yaxis_title="Product",
            xaxis_title="Total Revenue",
            height=max(400, len(df)*30),
        )

        return fig, f"Query executed in {duration} ms"
