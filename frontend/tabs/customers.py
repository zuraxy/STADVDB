from dash import html, dcc, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import pycountry
from common import COLORS, make_api_request


def layout():
    return dcc.Tab(label="Customer Distribution", children=[
        html.Div([
            html.H2("Customer Distribution"),
            dcc.Store(id="selected-country-store", data=None),

            html.Div([
                html.Button("Refresh Data", id="q2-submit-btn", n_clicks=0,
                        style={'backgroundColor': COLORS['primary'], 'color': 'white',
                                'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
            ], style={"marginBottom": "20px"}),

            html.Div([
                html.Label("View Type:"),
                dcc.RadioItems(
                    id='q2-view-type',
                    options=[
                        {'label': 'Bar Chart', 'value': 'bar'},
                        {'label': 'World Map', 'value': 'map'}
                    ],
                    value='map',
                    labelStyle={'display': 'inline-block', 'marginRight': '15px'}
                ),
            ], style={"marginBottom": "15px"}),

            html.Div([
                dcc.Loading(
                    dcc.Graph(id="customer-dist-graph"),
                    type="circle"
                ),
            ], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),

            html.Div([
                html.H3(id="city-detail-title", children=""),
                dcc.Loading(
                    dcc.Graph(id="city-detail-graph"),
                    type="circle"
                ),
            ], id="city-detail-container", style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 
                                                'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)', 'marginTop': '20px', 'display': 'none'}),

            html.Div(id="q2-query-time", style={'marginTop': '10px', 'fontStyle': 'italic'})
        ], style={"padding": "20px"})
    ])


def register_callbacks(app):
    @app.callback(
        [Output("customer-dist-graph", "figure"), Output("q2-query-time", "children")],
        [Input("q2-submit-btn", "n_clicks"),
         Input("q2-view-type", "value")]
    )
    def update_customer_dist(n_clicks, view_type):
        data, duration = make_api_request("query2")

        df = pd.DataFrame(data) if data else pd.DataFrame({"country": [], "city": [], "total_customers": []})

        if df.empty:
            fig = go.Figure().add_annotation(
                text="No data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig, ""

        df["total_customers"] = pd.to_numeric(df["total_customers"])

        country_df = df[df['city'].isna()].copy()
        country_df = country_df.dropna(subset=['country'])

        if view_type == 'bar':
            df = df[~(df['country'].isna() & df['city'].isna())]
            df['city'] = df['city'].fillna('Total')
            df = df.sort_values(['country', 'total_customers'], ascending=[True, False])

            fig = px.bar(
                df,
                x="country",
                y="total_customers",
                color="city",
                title="Customer Distribution by Country and City",
                barmode="group",
                hover_data=["total_customers"]
            )

            fig.update_layout(
                xaxis_title="Country",
                yaxis_title="Number of Customers",
                legend_title="City",
                height=600,
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=0.99,
                    xanchor="right",
                    x=0.99
                )
            )
        else:
            def get_country_code(country_name):
                try:
                    return pycountry.countries.search_fuzzy(country_name)[0].alpha_3
                except:
                    return None

            country_df['iso_alpha'] = country_df['country'].apply(get_country_code)

            fig = px.choropleth(
                country_df,
                locations="iso_alpha",
                color="total_customers",
                hover_name="country",
                color_continuous_scale=px.colors.sequential.Plasma,
                title="Global Customer Distribution (Click on a country to see city details)",
                labels={'total_customers': 'Customers'}
            )

            fig.update_layout(
                geo=dict(
                    showframe=False,
                    showcoastlines=True,
                    projection_type='natural earth'
                ),
                height=600
            )

        return fig, f"Query executed in {duration} ms"

    @app.callback(
        [Output("city-detail-container", "style"),
         Output("city-detail-title", "children"),
         Output("city-detail-graph", "figure"),
         Output("selected-country-store", "data")],
        [Input("customer-dist-graph", "clickData"),
         Input("q2-view-type", "value")],
        [State("selected-country-store", "data")]
    )
    def show_city_details(click_data, view_type, selected_country):
        data, _ = make_api_request("query2")
        df = pd.DataFrame(data) if data else pd.DataFrame({"country": [], "city": [], "total_customers": []})

        container_style = {'display': 'none'}
        title = ""
        fig = go.Figure()

        if view_type == 'map' and click_data and 'points' in click_data and len(click_data['points']) > 0:
            try:
                country_name = click_data['points'][0]['hovertext']

                city_df = df[(df['country'] == country_name) & (~df['city'].isna())].copy()

                if not city_df.empty:
                    city_df["total_customers"] = pd.to_numeric(city_df["total_customers"])
                    city_df = city_df.sort_values('total_customers', ascending=False)

                    fig = px.bar(
                        city_df,
                        x="city",
                        y="total_customers",
                        title=f"Customer Distribution in {country_name} Cities",
                        color_discrete_sequence=[COLORS['primary']],
                        labels={"total_customers": "Customers", "city": "City"}
                    )

                    fig.update_layout(
                        xaxis_title="City",
                        yaxis_title="Number of Customers"
                    )

                    container_style = {'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 
                                      'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)', 'marginTop': '20px'}
                    title = f"Cities in {country_name}"

                    return container_style, title, fig, country_name
            except Exception as e:
                print(f"Error processing city details: {e}")

        if view_type == 'bar':
            return container_style, title, fig, None

        return container_style, title, fig, selected_country
