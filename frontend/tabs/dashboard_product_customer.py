from dash import html, dcc
from common import COLORS

from . import top_products, customers


def layout():
    sections = []
    sections.append(html.H2("Product & Customer Insights", style={"marginBottom": "16px"}))

    # Customer Distribution (Query 2)
    sections.append(html.Div(
        customers.layout().children,
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
            "marginBottom": "16px",
        },
    ))

    # Top Products (Query 3)
    sections.append(html.Div(
        top_products.layout().children,
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
        },
    ))

    return dcc.Tab(label="Products & Customers", children=[
        html.Div(sections, style={"padding": "20px"})
    ])


def register_callbacks(app):
    customers.register_callbacks(app)
    top_products.register_callbacks(app)
