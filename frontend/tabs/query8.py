from dash import html, dcc, Input, Output, State
from dash import dash_table
import dash
import plotly.graph_objects as go
import pandas as pd
from common import COLORS, make_api_request


def layout():
	return dcc.Tab(label="Revenue Drilldown (Query 8)", children=[
		html.Div([
			html.H2("Revenue Drilldown by Country → City → Category"),
			html.Div([
				html.Div([
					html.Label("Metric:"),
					dcc.RadioItems(
						id="q8-metric",
						options=[
							{"label": "Total Value", "value": "total"},
							{"label": "Avg Order Value", "value": "aov"},
						],
						value="total",
						labelStyle={"display": "inline-block", "marginRight": "12px"},
					)
				], style={'display': 'inline-block', 'marginRight': '20px'}),
				html.Div([
					html.Label("Year:"),
					dcc.Input(id="q8-year", type="number", value=2025, min=2000, step=1,
							  style={"width": "200px"}),
				], style={'display': 'inline-block', 'marginRight': '20px'}),

				html.Div([
					html.Label("Country:"),
					dcc.Dropdown(id="q8-country-dd", options=[], value=None, placeholder="Select country",
								 clearable=True, style={"minWidth": "1000px", "width": "1000px"})
				], style={'display': 'inline-block', 'marginRight': '20px', 'minWidth': '1020px'}),

				html.Div([
					html.Label("City:"),
					dcc.Dropdown(id="q8-city-dd", options=[], value=None, placeholder="Select city",
								 clearable=True, style={"minWidth": "700px", "width": "700px"})
				], style={'display': 'inline-block', 'marginRight': '20px', 'minWidth': '720px'}),

				html.Div([
					html.Label("Category:"),
					dcc.Dropdown(id="q8-category-dd", options=[], value=None, placeholder="Select category",
								 clearable=True, style={"minWidth": "700px", "width": "700px"})
				], style={'display': 'inline-block', 'marginRight': '20px', 'minWidth': '720px'}),

				html.Button("Update", id="q8-update", n_clicks=0,
						   style={'backgroundColor': COLORS['primary'], 'color': 'white',
								  'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px', 'marginRight': '10px'}),
				html.Button("Back", id="q8-back", n_clicks=0,
						   style={'backgroundColor': COLORS['secondary'], 'color': 'white',
								  'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px'})
			], style={"marginBottom": "12px"}),

			html.Div(id="q8-breadcrumb", style={'marginBottom': '8px', 'fontWeight': '600'}),

			html.Div(
				id="q8-top-bottom",
				style={
					'marginBottom': '12px',
					'backgroundColor': COLORS['card'],
					'padding': '10px 12px',
					'borderRadius': '8px',
					'boxShadow': '0 0 8px rgba(0,0,0,0.08)',
					'border': '1px solid #eee',
					'color': COLORS['text']
				}
			),

			dcc.Store(id="q8-state", data={"level": "country", "country": None, "city": None, "category": None}),
			dcc.Store(id="q8-master", data={"countries": [], "citiesByCountry": {}, "categoriesByCity": {}}),

			html.Div([
				dcc.Loading(
					dcc.Graph(id="q8-bar"),
					type="circle"
				),
			], style={'backgroundColor': COLORS['card'], 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0px 0px 10px rgba(0,0,0,0.1)'}),

			html.Div(id="q8-table", style={'marginTop': '16px'}),

			html.Div(id="q8-query-time", style={'marginTop': '10px', 'fontStyle': 'italic'})
		], style={"padding": "20px"})
	])


def register_callbacks(app):
	# Update drill state on bar click, Back, or Update
	@app.callback(
		[Output("q8-state", "data"), Output("q8-master", "data")],
		[
			Input("q8-update", "n_clicks"),
			Input("q8-back", "n_clicks"),
			Input("q8-bar", "clickData"),
			Input("q8-year", "value"),
			Input("q8-country-dd", "value"),
			Input("q8-city-dd", "value"),
			Input("q8-category-dd", "value"),
		],
		[State("q8-state", "data"), State("q8-master", "data")],
		prevent_initial_call=False,
	)
	def update_state(n_update, n_back, clickData, year_value, sel_country, sel_city, sel_category, state, master):
		state = state or {"level": "country", "country": None, "city": None, "category": None}
		master = master or {"countries": [], "citiesByCountry": {}, "categoriesByCity": {}}
		triggered_id = None
		if dash.callback_context.triggered:
			triggered_id = dash.callback_context.triggered[0]['prop_id'].split('.')[0]

		# Update should just re-query; keep current state/params intact
		if triggered_id == "q8-update":
			return state, master

		# Year change: reset drilldown to top, preserve selected category
		if triggered_id == "q8-year":
			return {"level": "country", "country": None, "city": None, "category": state.get("category")}, master

		# Navigate back
		if triggered_id == "q8-back":
			if state.get("level") == "category":
				return {"level": "city", "country": state.get("country"), "city": None, "category": None}, master
			elif state.get("level") == "city":
				return {"level": "country", "country": None, "city": None, "category": None}, master
			else:
				return state, master

		# Dropdown selection handling (progressive parameters)
		if triggered_id == "q8-country-dd":
			# Selecting or clearing country keeps category visible and updates level appropriately
			if sel_country:
				return {"level": "city", "country": sel_country, "city": None, "category": state.get("category")}, master
			else:
				# cleared
				return {"level": "country", "country": None, "city": None, "category": state.get("category")}, master
		if triggered_id == "q8-city-dd":
			# Do NOT auto-drill to category on city selection; keep current level (or move to city if coming from country)
			current_level = state.get("level") or "country"
			next_level = ("city" if current_level == "country" else current_level)
			if sel_city:
				# If city changed, clear category to avoid mismatched city/category
				category_val = state.get("category")
				if state.get("city") != sel_city:
					category_val = None
				return {"level": next_level, "country": state.get("country"), "city": sel_city, "category": category_val}, master
			else:
				# cleared city -> stay at city level for selected country
				return {"level": "city", "country": state.get("country"), "city": None, "category": state.get("category")}, master
		if triggered_id == "q8-category-dd":
			# Category selection should not change level; just store it
			return {"level": state.get("level"), "country": state.get("country"), "city": state.get("city"), "category": sel_category}, master

		# Drill down on bar click
		if triggered_id == "q8-bar" and clickData and 'points' in clickData and clickData['points']:
			point = clickData['points'][0]
			# customdata carries the label we need to drill into
			label = None
			if isinstance(point.get('customdata'), (list, tuple)):
				label = point['customdata'][0]
			else:
				label = point.get('customdata') or point.get('x')

			if state.get("level") == "country":
				# Go to city level for chosen country
				return {"level": "city", "country": label, "city": None, "category": None}, master
			elif state.get("level") == "city":
				# Go to category level for chosen city
				return {"level": "category", "country": state.get("country"), "city": label, "category": None}, master
			else:
				# Already at deepest level
				return state, master

		# Default: no change
		return state, master

	# Render chart + table based on current state and year; always re-query backend accordingly
	@app.callback(
		[
			Output("q8-bar", "figure"),
			Output("q8-table", "children"),
			Output("q8-breadcrumb", "children"),
			Output("q8-query-time", "children"),
			Output("q8-country-dd", "options"),
			Output("q8-city-dd", "options"),
			Output("q8-category-dd", "options"),
			Output("q8-top-bottom", "children"),
		],
		[
			Input("q8-state", "data"),
			Input("q8-year", "value"),
			Input("q8-update", "n_clicks"),
			Input("q8-metric", "value"),
		],
	)
	def render(state, year, _n_update, metric):
		# Normalize inputs
		year = int(year) if year else 2025
		metric = metric or "total"
		state = state or {"level": "country", "country": None, "city": None, "category": None}
		level = state.get("level", "country")
		country = state.get("country")
		city = state.get("city")
		selected_category = state.get("category")

		# Build params and fetch data from appropriate query based on metric
		params = {
			"year": year,
			"country": country if country else None,
			"city": city if city else None,
			"category": selected_category if selected_category else None,
		}
		endpoint = "query8" if metric == "total" else "query9"
		value_col = "total_revenue" if metric == "total" else "average_order_value"
		value_label = "Total Revenue" if metric == "total" else "Average Order Value"
		data, duration = make_api_request(endpoint, params)
		# Graceful fallback: if no data for selected category in this year, retry without category
		clear_category_due_to_empty = False
		if (not data or len(data) == 0) and selected_category:
			params_fallback = {**params, "category": None}
			data, duration = make_api_request(endpoint, params_fallback)
			if data:
				clear_category_due_to_empty = True

		df = pd.DataFrame(data) if data else pd.DataFrame({
			"country": [], "city": [], "category": [],
			"total_revenue": [], "unique_riders": []
		})

		if df.empty:
			fig = go.Figure().add_annotation(text="No data available", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
			return (
				fig,
				html.Div(),
				"",
				"",
				[],
				[],
				[],
				"",
			)

		# Ensure numeric
		for col in ["total_revenue", "unique_riders", "average_order_value"]:
			if col in df.columns:
				df[col] = pd.to_numeric(df[col])

		# Compute dropdown options fresh from df
		# With Query 8, when a category is selected, 'All Categories' rollups are not returned.
		# So select rows using the active metric category for option derivation too.
		metric_category = selected_category if selected_category else "All Categories"
		country_rows = df[(df["city"] == "All Cities") & (df["category"] == metric_category)]
		country_rows = country_rows[country_rows["country"] != "Grand Total"]
		country_list = country_rows["country"].dropna().unique().tolist()
		if country and country not in country_list:
			country_list.append(country)
		country_options = [{"label": c, "value": c} for c in country_list]
		if country:
			city_rows = df[(df["country"] == country) & (df["category"] == metric_category) & (df["city"] != "All Cities")]
			city_list = city_rows["city"].dropna().unique().tolist()
			# Keep existing selected city visible even if not present due to transient filter states
			if city and city not in city_list:
				city_list.append(city)
			city_options = [{"label": c, "value": c} for c in city_list]
		else:
			city_options = []
		if country and city:
			cat_rows = df[(df["country"] == country) & (df["city"] == city) & (df["category"] != "All Categories")]
			category_options = [{"label": c, "value": c} for c in cat_rows["category"].dropna().unique().tolist()]
		elif country:
			cat_rows = df[(df["country"] == country) & (df["category"] != "All Categories")]
			category_options = [{"label": c, "value": c} for c in cat_rows["category"].dropna().unique().tolist()]
		else:
			cat_rows = df[(df["category"] != "All Categories")]
			category_options = [{"label": c, "value": c} for c in cat_rows["category"].dropna().unique().tolist()]

		# Keep selected values
		country_value = country
		city_value = city
		category_value = None if clear_category_due_to_empty else selected_category

		# Build chart and table dataframes and labels
		chart_df = df.copy()
		table_df = df.copy()
		breadcrumb = [f"Year {year}"]
		if level == "country":
			# Chart (top-10 countries)
			if selected_category:
				chart_df = chart_df[(chart_df["city"] == "All Cities") & (chart_df["category"] == selected_category)]
			else:
				chart_df = chart_df[(chart_df["city"] == "All Cities") & (chart_df["category"] == "All Categories")]
			chart_df = chart_df[chart_df["country"] != "Grand Total"]
			chart_df = chart_df.sort_values(value_col, ascending=False).head(10)
			x_vals = chart_df["country"].tolist()
			# Table (all countries)
			table_df = df[(df["city"] == "All Cities") & (df["country"] != "Grand Total")]
			if selected_category:
				table_df = table_df[table_df["category"] == selected_category]
			else:
				table_df = table_df[table_df["category"] == "All Categories"]
			table_df = table_df.sort_values(value_col, ascending=False)
			title = f"{value_label} by Country ({year})"
		elif level == "city":
			breadcrumb.append(f"Country: {country}")
			# Determine top cities by their rollup totals for the selected scope (no frontend aggregation)
			metric_category = selected_category if selected_category else "All Categories"
			city_totals = df[(df["country"] == country) & (df["category"] == metric_category) & (df["city"] != "All Cities")]
			city_totals = city_totals.sort_values(value_col, ascending=False).head(10)
			city_order = city_totals["city"].tolist()
			# Chart detail rows: only top-10 cities
			chart_detail = df[(df["country"] == country) & (df["city"].isin(city_order)) & (df["category"] != "All Categories")]
			if selected_category:
				chart_detail = chart_detail[chart_detail["category"] == selected_category]
			# Ensure cities appear in the chosen order
			chart_detail["city"] = pd.Categorical(chart_detail["city"], categories=city_order, ordered=True)
			chart_detail = chart_detail.sort_values(["city", value_col], ascending=[True, False])
			chart_df = chart_detail.copy()
			# Table: all cities' detail rows within country (optionally restricted by category)
			table_df = df[(df["country"] == country) & (df["city"] != "All Cities") & (df["category"] != "All Categories")]
			if selected_category:
				table_df = table_df[table_df["category"] == selected_category]
			table_df = table_df.sort_values(["city", value_col], ascending=[True, False])
			x_vals = city_order
			title = f"{value_label} by City (stacked by Category) in {country} ({year})"
		else:
			breadcrumb.extend([f"Country: {country}", f"City: {city}"])
			# Chart: top-10 categories for the city
			chart_df = chart_df[(chart_df["country"] == country) & (chart_df["city"] == city)]
			chart_df = chart_df[chart_df["category"] != "All Categories"]
			if selected_category:
				chart_df = chart_df[chart_df["category"] == selected_category]
			chart_df = chart_df.sort_values(value_col, ascending=False).head(10)
			x_vals = chart_df["category"].tolist()
			# Table: all categories for the city (optionally restricted by selected_category)
			table_df = df[(df["country"] == country) & (df["city"] == city) & (df["category"] != "All Categories")]
			if selected_category:
				table_df = table_df[table_df["category"] == selected_category]
			table_df = table_df.sort_values(value_col, ascending=False)
			title = f"{value_label} by Category in {city}, {country} ({year})"

		# Build figure
		fig = go.Figure()
		if level == "city":
			# Stacked bars by category
			cats = chart_df["category"].dropna().unique().tolist()
			# Deterministic color map
			palette = [
				"#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
				"#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
			]
			color_map = {c: palette[i % len(palette)] for i, c in enumerate(sorted(cats))}
			# Add one trace per category
			for cat in sorted(cats):
				series = []
				for city_name in x_vals:
					row = chart_df[(chart_df["city"] == city_name) & (chart_df["category"] == cat)]
					val = float(row[value_col].iloc[0]) if not row.empty else 0.0
					series.append(val)
				fig.add_trace(go.Bar(
					x=x_vals,
					y=series,
					name=cat,
					marker_color=color_map.get(cat, COLORS['primary']),
					customdata=x_vals,
					hovertemplate=f"%{{x}}<br>Category: {cat}<br>Revenue: %{{y:.2f}}<extra></extra>",
				))
			fig.update_layout(barmode="stack")
		else:
			fig.add_trace(go.Bar(
				x=x_vals,
				y=chart_df[value_col],
				marker_color=COLORS['primary'],
				customdata=x_vals,
				hovertemplate=f"%{{x}}<br>{value_label}: %{{y:.2f}}<extra></extra>",
			))
		fig.update_layout(
			title=title,
			xaxis_title=("Country" if level == "country" else ("City" if level == "city" else "Category")),
			yaxis_title="Total Revenue",
			hovermode="x unified",
		)

		# Build table
		if level == "country":
			cols = ["country", "category", "total_revenue", "unique_riders"]
			headers = ["Country", "Category", value_label, "Unique Riders"]
		elif level == "city":
			# Show detailed rows per city-category
			cols = ["city", "category", "total_revenue", "unique_riders"]
			headers = ["City", "Category", value_label, "Unique Riders"]
		else:
			cols = ["category", "total_revenue", "unique_riders"]
			headers = ["Category", value_label, "Unique Riders"]

		# If using AOV, swap value column name for rendering
		if metric == "aov":
			cols = [c if c != "total_revenue" else value_col for c in cols]

		# Build DataTable for clearer alignment
		def fmt_amount(v):
			return f"{float(v):,.2f}" if pd.notnull(v) else ""
		def fmt_int(v):
			return (str(int(v)) if pd.notnull(v) else "")
		data_records = []
		for _, row in table_df[cols].iterrows():
			rec = {}
			for c in cols:
				if c == value_col:
					rec[c] = fmt_amount(row[c])
				elif c == "unique_riders":
					rec[c] = fmt_int(row[c])
				else:
					rec[c] = row[c]
			data_records.append(rec)
		columns = []
		for col_id, name in zip(cols, headers):
			columns.append({"name": name, "id": col_id})
		table = dash_table.DataTable(
			columns=columns,
			data=data_records,
			style_table={"width": "100%", "overflowX": "auto"},
			style_cell={"padding": "8px", "border": "1px solid #ddd", "textAlign": "left"},
			style_header={"backgroundColor": "#f6f6f6", "fontWeight": "bold", "border": "1px solid #ddd"},
			style_data_conditional=[
				{"if": {"column_id": "total_revenue"}, "textAlign": "right"},
				{"if": {"column_id": "unique_riders"}, "textAlign": "right"},
			],
			page_size=20,
			page_action="native",
		)

		# Highest & Lowest labels (context-aware)
		lines = []
		if level == "country" and not table_df.empty:
			# Compare countries (rollup rows)
			idx_max = table_df[value_col].astype(float).idxmax()
			idx_min = table_df[value_col].astype(float).idxmin()
			max_row = table_df.loc[idx_max]
			min_row = table_df.loc[idx_min]
			lines.append(
				f"Highest country: {max_row['country']} (\u20B1{float(max_row[value_col]):,.2f})  •  "
				f"Lowest country: {min_row['country']} (\u20B1{float(min_row[value_col]):,.2f})"
			)
		elif level == "city":
			# Line 1: cities by rollup totals for the selected scope
			metric_category = selected_category if selected_category else "All Categories"
			city_totals_hilo = df[(df["country"] == country) & (df["category"] == metric_category) & (df["city"] != "All Cities")]
			if not city_totals_hilo.empty:
				idx_max = city_totals_hilo[value_col].astype(float).idxmax()
				idx_min = city_totals_hilo[value_col].astype(float).idxmin()
				max_row = city_totals_hilo.loc[idx_max]
				min_row = city_totals_hilo.loc[idx_min]
				lines.append(
					f"Highest city: {max_row['city']} (\u20B1{float(max_row[value_col]):,.2f})  •  "
					f"Lowest city: {min_row['city']} (\u20B1{float(min_row[value_col]):,.2f})"
				)
			# Line 2: categories within current selection (all city-category rows in table_df)
			if not table_df.empty:
				idx_max_c = table_df[value_col].astype(float).idxmax()
				idx_min_c = table_df[value_col].astype(float).idxmin()
				max_row_c = table_df.loc[idx_max_c]
				min_row_c = table_df.loc[idx_min_c]
				lines.append(
					f"Highest category: {max_row_c['category']} in {max_row_c['city']} (\u20B1{float(max_row_c[value_col]):,.2f})  •  "
					f"Lowest category: {min_row_c['category']} in {min_row_c['city']} (\u20B1{float(min_row_c[value_col]):,.2f})"
				)
		else:  # category level
			if not table_df.empty:
				idx_max = table_df[value_col].astype(float).idxmax()
				idx_min = table_df[value_col].astype(float).idxmin()
				max_row = table_df.loc[idx_max]
				min_row = table_df.loc[idx_min]
				lines.append(
					f"Highest category: {max_row['category']} (\u20B1{float(max_row[value_col]):,.2f})  •  "
					f"Lowest category: {min_row['category']} (\u20B1{float(min_row[value_col]):,.2f})"
				)

		top_bottom_text = [html.Div(line) for line in lines] if lines else ""

		breadcrumb_txt = " » ".join(breadcrumb)

		return (
			fig,
			table,
			breadcrumb_txt,
			(f"Query executed in {duration} ms" if duration else ""),
			country_options,
			city_options,
			category_options,
			top_bottom_text,
		)

