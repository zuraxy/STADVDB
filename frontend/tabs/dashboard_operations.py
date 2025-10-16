from dash import html, dcc
from common import COLORS

from . import rider_rankings, vehicle_deliveries, query7 as top_riders


def layout():
    sections = []
    sections.append(html.H2("Rider & Logistics Operations", style={"marginBottom": "16px"}))

    # Rider Rankings (Query 5)
    sections.append(html.Div(
        rider_rankings.layout().children,
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
            "marginBottom": "16px",
        },
    ))

    # Vehicle Deliveries (Query 6)
    sections.append(html.Div(
        vehicle_deliveries.layout().children,
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
            "marginBottom": "16px",
        },
    ))

    # Top Riders Analytical Report (Query 7)
    sections.append(html.Div(
        top_riders.layout().children,
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
        },
    ))

    return dcc.Tab(label="Rider & Logistics", children=[
        html.Div(sections, style={"padding": "20px"})
    ])


def register_callbacks(app):
    rider_rankings.register_callbacks(app)
    vehicle_deliveries.register_callbacks(app)
    top_riders.register_callbacks(app)
