import os
import dash
from dash import html, dcc, Input, Output, State, dash_table
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np

app = dash.Dash(__name__, suppress_callback_exceptions=True)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:3000")

# Styling
COLORS = {
    'background': '#F8F9FA',
    'text': '#212529',
    'primary': '#007BFF',
    'secondary': '#6C757D',
    'success': '#28A745',
    'card': '#FFFFFF',
}

# Common function to make API requests
def make_api_request(endpoint, params=None):
    try:
        resp = requests.get(f"{BACKEND_URL}/{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get('rows', []), data.get('durationMs', 0)
    except Exception as e:
        print(f"Backend request failed ({endpoint}):", e)
        return [], 0

# Layout
app.layout = html.Div([
    html.H1("Data Warehouse Dashboard", style={'textAlign': 'center', 'marginBottom': '30px'}),
    
    # Tabs for different queries
    dcc.Tabs([
        # Query 1 - Revenue Over Time
        dcc.Tab(label="Revenue Trends", children=[
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
        ]),
        
        # Query 2 - Customer Distribution
# In the Query 2 tab, modify the content:

        dcc.Tab(label="Customer Distribution", children=[
            html.Div([
                html.H2("Customer Distribution"),
                # Add a Store component to remember clicked country
                dcc.Store(id="selected-country-store", data=None),
                
                html.Div([
                    html.Button("Refresh Data", id="q2-submit-btn", n_clicks=0,
                            style={'backgroundColor': COLORS['primary'], 'color': 'white',
                                    'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
                ], style={"marginBottom": "20px"}),
                
                # Add visualization type selector
                html.Div([
                    html.Label("View Type:"),
                    dcc.RadioItems(
                        id='q2-view-type',
                        options=[
                            {'label': 'Bar Chart', 'value': 'bar'},
                            {'label': 'World Map', 'value': 'map'}
                        ],
                        value='map',  # Changed default to map
                        labelStyle={'display': 'inline-block', 'marginRight': '15px'}
                    ),
                ], style={"marginBottom": "15px"}),
                
                html.Div([
                    dcc.Loading(
                        dcc.Graph(id="customer-dist-graph"),
                        type="circle"
                    ),
                ], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),
                
                # Add a container for city details that appears when a country is clicked
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
        ]),
        
        # Query 3 - Top Products
        dcc.Tab(label="Top Products", children=[
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
        ]),
        
        # Query 4 - 3-Month Moving Average
        dcc.Tab(label="Moving Average", children=[
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
        ]),
        
        # Query 5 - Rider Rankings
        dcc.Tab(label="Rider Rankings", children=[
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
        ]),
        
               dcc.Tab(label="Vehicle Deliveries", children=[
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
    ])
], style={'padding': '30px', 'backgroundColor': COLORS['background'], 'minHeight': '100vh'})

# Callback for Query 1 - Revenue Over Time
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

# Update the Query 2 callback

# First, add import for ISO country code mapping (at the top of the file)
import pycountry

# Update the Query 2 callback to add clickData handling

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
    
    # Convert to numeric
    df["total_customers"] = pd.to_numeric(df["total_customers"])
    
    # Create country-level dataframe for the map
    # Filter to rows where city is null (these are country totals from ROLLUP)
    country_df = df[df['city'].isna()].copy()
    country_df = country_df.dropna(subset=['country'])  # Ensure no null countries
    
    # For bar chart view
    if view_type == 'bar':
        # Same as before
        # Filter out the grand total row (where both country and city are null)
        df = df[~(df['country'].isna() & df['city'].isna())]
        
        # Replace NaN in city with "Total" for country totals
        df['city'] = df['city'].fillna('Total')
        
        # Sort by country and total customers (descending)
        df = df.sort_values(['country', 'total_customers'], ascending=[True, False])
        
        # Create grouped bar chart
        fig = px.bar(
            df,
            x="country",
            y="total_customers",
            color="city",
            title="Customer Distribution by Country and City",
            barmode="group",  # Use "stack" for stacked bars
            hover_data=["total_customers"]
        )
        
        fig.update_layout(
            xaxis_title="Country",
            yaxis_title="Number of Customers",
            legend_title="City",
            height=600,  # Taller to fit legend
            legend=dict(
                orientation="v",
                yanchor="top",
                y=0.99,
                xanchor="right",
                x=0.99
            )
        )
    
    # For map view
    else:
        # Map country names to ISO codes
        def get_country_code(country_name):
            try:
                return pycountry.countries.search_fuzzy(country_name)[0].alpha_3
            except:
                return None
        
        # Add ISO codes to dataframe
        country_df['iso_alpha'] = country_df['country'].apply(get_country_code)
        
        # Create choropleth map
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

# Add a new callback for handling map clicks and showing city details
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
    # Get full data to filter
    data, _ = make_api_request("query2")
    df = pd.DataFrame(data) if data else pd.DataFrame({"country": [], "city": [], "total_customers": []})
    
    # Default values for no selection
    container_style = {'display': 'none'}
    title = ""
    fig = go.Figure()
    
    # Only process if we're in map view and have click data
    if view_type == 'map' and click_data and 'points' in click_data and len(click_data['points']) > 0:
        # Extract country name from clickData
        try:
            country_name = click_data['points'][0]['hovertext']
            
            # Filter data to only show cities in the selected country
            # Get cities where country matches and city is not null
            city_df = df[(df['country'] == country_name) & (~df['city'].isna())].copy()
            
            if not city_df.empty:
                # Convert to numeric
                city_df["total_customers"] = pd.to_numeric(city_df["total_customers"])
                
                # Sort by customer count descending
                city_df = city_df.sort_values('total_customers', ascending=False)
                
                # Create bar chart for cities
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
                
                # Make the container visible
                container_style = {'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 
                                  'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)', 'marginTop': '20px'}
                title = f"Cities in {country_name}"
                
                return container_style, title, fig, country_name
        except Exception as e:
            print(f"Error processing city details: {e}")
    
    # If we switched to bar chart, hide the city details
    if view_type == 'bar':
        return container_style, title, fig, None
    
    # Return existing selection if no new click
    return container_style, title, fig, selected_country

# Callback for Query 3 - Top Products
@app.callback(
    [Output("top-products-graph", "figure"), Output("q3-query-time", "children")],
    Input("q3-submit-btn", "n_clicks"),
    State("q3-top-n", "value"),
    State("q3-country", "value"),
    State("q3-city", "value"),
    State("q3-category", "value"),
)
def update_top_products(n_clicks, top_n, country, city, category):
    # Default values
    top_n = top_n or 10
    params = {
        "no": top_n,  # Changed from "n" to "no" to match backend
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
    
    # Convert to numeric
    df["total_sales"] = pd.to_numeric(df["total_sales"])
    if "total_quantity_sold" in df.columns:
        df["total_quantity_sold"] = pd.to_numeric(df["total_quantity_sold"])
    
    # Sort by total sales (descending)
    df = df.sort_values("total_sales", ascending=True)  # Ascending for horizontal bars
    
    # Limit to top N
    if len(df) > top_n:
        df = df.tail(top_n)
    
    # Create horizontal bar chart
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
    )
    
    # Improve layout
    fig.update_layout(
        yaxis_title="Product",
        xaxis_title="Total Revenue",
        height=max(400, len(df)*30),  # Dynamic height based on number of products
    )
    
    return fig, f"Query executed in {duration} ms"

# Callback for Query 4 - 3-Month Moving Average
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
    
    # Convert numeric columns
    numeric_cols = ["total_sales", "moving_avg_3_month"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col])
    
    # Create date column for better x-axis
    df["date"] = pd.to_datetime(df["year"].astype(str) + "-" + df["month"].astype(str) + "-01")
    
    # Create line chart with moving average
    fig = go.Figure()
    
    # If filtering by country, show single country
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
        # If showing all countries, create a line for each country
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

# Callback for Query 5 - Rider Rankings
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
        fig = go.Figure().add_annotation(
            text="No data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig, ""
    
    # Convert numeric columns
    for col in ["total_deliveries", "delivery_rank"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col])
    
    # Filter to top 20 riders for readability
    df = df.sort_values("delivery_rank").head(20)
    
    # Create horizontal bar chart
    if "country" in df.columns and len(df["country"].unique()) > 1:
        # Color by country if multiple countries
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
        # Single color if one country
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
    
    # Improve layout
    fig.update_traces(texttemplate="Rank: %{text}", textposition="inside")
    fig.update_layout(
        yaxis_title="Courier",
        xaxis_title="Total Deliveries",
        height=max(500, len(df)*30),  # Dynamic height based on number of riders
        yaxis={'categoryorder': 'total ascending'}  # Sort by total deliveries
    )
    
    return fig, f"Query executed in {duration} ms"

# Callback for Query 6 - Deliveries by Vehicle Type

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

    # Ensure numeric
    df["total_deliveries"] = pd.to_numeric(df["total_deliveries"], errors="coerce").fillna(0)

    df["year"] = pd.to_numeric(df["year"], errors="coerce")  # may come as float (e.g., 2024.0)
    if "month" in df.columns:
        df["month"] = pd.to_numeric(df["month"], errors="coerce")
    else:
        df["month"] = pd.NA

    # Drop rows without year
    df = df[~df["year"].isna()]
    df["year"] = df["year"].astype(int)
    # Build period
    df["period"] = df.apply(
        lambda r: f"{r['year']}-{int(r['month']):02d}" if pd.notna(r["month"]) and r["month"] > 0 else f"{r['year']}",
        axis=1
    )

    # Detail rows only
    df_plot = df[~df["vehicle_type"].isna()].copy()

    if df_plot.empty:
        fig = go.Figure().add_annotation(
            text="No vehicle-level rows",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig, "", f"Query executed in {duration} ms"

    # Sorting
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

    # Summary
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

if __name__ == "__main__":
    app.run(debug=True)