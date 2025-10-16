import dash
from dash import html, dcc
from common import COLORS
from tabs import dashboard_sales, dashboard_product_customer, dashboard_operations

app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Layout
app.layout = html.Div([
    html.H1("Data Warehouse Dashboard", style={'textAlign': 'center', 'marginBottom': '30px'}),
    dcc.Tabs([
        dashboard_sales.layout(),
        dashboard_product_customer.layout(),
        dashboard_operations.layout(),
    ])
], style={'padding': '30px', 'backgroundColor': COLORS['background'], 'minHeight': '100vh'})

for mod in [dashboard_sales, dashboard_product_customer, dashboard_operations]:
    mod.register_callbacks(app)

if __name__ == "__main__":
    app.run(debug=True)