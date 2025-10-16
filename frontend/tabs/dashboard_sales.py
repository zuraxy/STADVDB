from dash import html, dcc
from common import COLORS

# Import existing modules to reuse their layouts and callbacks
from . import revenue, moving_avg
from . import query8 as sales_summary


def layout():
    # Compose a single Tab that embeds the contents of existing tabs
    sections = []

    sections.append(html.H2("Sales & Revenue Performance", style={"marginBottom": "16px"}))

    # Flexible Sales Summary (Query 8) - moved to top
    sections.append(html.Div(
        sales_summary.layout().children,
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
            "marginBottom": "16px",
        },
    ))

    # Revenue Trends (Query 1)
    sections.append(html.Div(
        revenue.layout().children,  # use the existing inner content
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
            "marginBottom": "16px",
        },
    ))

    # Moving Average (Query 4)
    sections.append(html.Div(
        moving_avg.layout().children,
        style={
            "backgroundColor": COLORS["card"],
            "padding": "10px",
            "borderRadius": "10px",
        },
    ))

    return dcc.Tab(label="Sales & Revenue", children=[
        html.Div(sections, style={"padding": "20px"})
    ])


def register_callbacks(app):
    # Delegate to existing modules to register their callbacks
    revenue.register_callbacks(app)
    moving_avg.register_callbacks(app)
    sales_summary.register_callbacks(app)
