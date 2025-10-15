import dash
from dash import html, dcc
from common import COLORS
from tabs import revenue, customers, top_products, moving_avg, rider_rankings, vehicle_deliveries
from tabs import query8

app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Layout
app.layout = html.Div([
    html.H1("Data Warehouse Dashboard", style={'textAlign': 'center', 'marginBottom': '30px'}),
    dcc.Tabs([
        revenue.layout(),
        customers.layout(),
        top_products.layout(),
        moving_avg.layout(),
        rider_rankings.layout(),
        vehicle_deliveries.layout(),
        query8.layout(),
    ])
], style={'padding': '30px', 'backgroundColor': COLORS['background'], 'minHeight': '100vh'})

for mod in [revenue, customers, top_products, moving_avg, rider_rankings, vehicle_deliveries, query8]:
    mod.register_callbacks(app)

if __name__ == "__main__":
    app.run(debug=True)