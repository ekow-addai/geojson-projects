# ---------------------------------------
# 📦 Libraries
# ---------------------------------------
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import wkt
import folium
from folium import GeoJson
import branca.colormap as cm
import re

# ---------------------------------------
# 📄 Data prep
# ---------------------------------------
datasets
datasets['PROGRESS'].head(1)

df_init = datasets['PROGRESS']

df_init.rename(columns={
    'COUNTRY': 'country',
    'NEST': 'nest',
    'REGION': 'region',
    'DISTRICT': 'district',
    'FACILITIES': 'facilities',
    'DIRECT_INDIRECT': 'direct_indirect',
    'HF_STATUS': 'hf_status',
    'TYPE_SUMMARY': 'type_summary',
    'BLOOD_UNITS_DELIVERED': 'blood_units_delivered',
    'VACCINE_DOSES_DELIVERED': 'vaccine_doses_delivered',
    'TOTAL_DELIVERIES': 'total_deliveries',
    'EMERGENCY_DELIVERIES': 'emergency_deliveries',
    'SU_30': '30_day_utilization',
    'SU_60': '60_day_utilization',
    'SU_90': '90_day_utilization'
}, inplace=True)

df_init['blood_units_delivered'] = df_init['blood_units_delivered'].fillna(0).astype(int)
df_init['vaccine_doses_delivered'] = df_init['vaccine_doses_delivered'].fillna(0).astype(int)

# ---------------------------------------
# 🧠 Summary generator
# ---------------------------------------
def parse_direct_count(direct_indirect_str):
    match = re.search(r'(\d+)\s+Direct', str(direct_indirect_str))
    return int(match.group(1)) if match else 0

def generate_summary_py(row):
    facilities = row.get("facilities", 0)
    direct_indirect = row.get("direct_indirect", "")
    type_summary = str(row.get("type_summary", "")).lower()
    utilization_90 = row.get("90_day_utilization", 0)

    direct_count = parse_direct_count(direct_indirect)
    ordering_l90 = int(round((utilization_90 / 100) * facilities))
    gap = facilities - ordering_l90

    if facilities == 0:
        return None

    summary = f"Zipline serves {facilities} {'facility' if facilities == 1 else 'facilities'} in this area. "

    if direct_count == 0:
        summary += "None have direct dropsites. "
    elif direct_count == facilities:
        summary += f"All {facilities} have direct dropsites. "
    elif direct_count == 1:
        summary += "Only 1 has a direct dropsite. "
    else:
        summary += f"Only {direct_count} have direct dropsites. "

    if "hospital" not in type_summary:
        summary += "The district has no Hospitals. "

    if gap == facilities:
        summary += "No facility in this district has placed any order in the last 90 days."
    elif gap == 1:
        summary += "1 facility has not placed any order in the last 90 days."
    elif gap > 1:
        summary += f"{gap} facilities have not placed any order in the last 90 days."

    return summary.strip()

df_init["summary"] = df_init.apply(generate_summary_py, axis=1)

# ---------------------------------------
# 🌍 Geo boundaries
# ---------------------------------------
url = "https://raw.githubusercontent.com/ekow-addai/Geojson/991399c5983d67c5ad405c58e5efe579e33982e2/final%20geoboundaries/final_merged_geoboundaries.csv"
geo_df = pd.read_csv(url)
geo_df["geometry"] = geo_df["geometry_wkt"].apply(wkt.loads)

geo_gdf = gpd.GeoDataFrame(geo_df, geometry="geometry")
geo_gdf.rename(columns={'District': 'district', 'Country': 'country'}, inplace=True)

df_afr1 = df_init.merge(geo_gdf[['district', 'country', 'geometry']], on=['district', 'country'], how='left')
gdf_afr1 = gpd.GeoDataFrame(df_afr1, geometry='geometry').set_crs("EPSG:4326")

# ---------------------------------------
# 💬 Tooltip
# ---------------------------------------
def format_nest(nest_string):
    if pd.isnull(nest_string):
        return "N/A"
    parts = [part.strip() for part in nest_string.split(',')]
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]

def create_tooltip_html(row):
    return f"""
    <div style="font-family: Arial; font-size: 12px; padding: 8px; line-height: 1.5; border-radius: 6px; text-align: left;">
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 6px;">🗺️{row['district']} ({row['region']})</div>
        <div style="font-size: 13px; margin-bottom: 10px;"><b><i>✈️ Served by {format_nest(row['nest'])}</i></b></div>
        <div style="margin-bottom: 6px;"><b style="font-size: 14px;">🔎 Summary</b><br>{row['summary']}</div>
        <div style="margin-bottom: 6px;"><b style="font-size: 14px;">📍 District Overview</b><br>
            • Facilities: {row['facilities']:,}<br>
            • Direct/Indirect: {row['direct_indirect']}<br>
            • HF Status: {row['hf_status']}<br>
            • Type Summary: {row['type_summary']}</div>
        <div style="margin-bottom: 6px;"><b style="font-size: 14px;">📊 Service Utilization</b><br>
            • Last 30 Days: {row['30_day_utilization']}%<br>
            • Last 60 Days: {row['60_day_utilization']}%<br>
            • Last 90 Days: {row['90_day_utilization']}%</div>
        <div><b style="font-size: 14px;">📦 Impact Overview</b><br>
            • Total Deliveries: {row['total_deliveries']:,} packages<br>
            • Blood Units Delivered: {row['blood_units_delivered']:,} units<br>
            • Vaccine Doses Delivered: {row['vaccine_doses_delivered']:,} doses<br>
            • Emergency Deliveries: {row['emergency_deliveries']} of all deliveries</div>
    </div>
    """

gdf_afr1['tooltip_html'] = gdf_afr1.apply(create_tooltip_html, axis=1)

# ---------------------------------------
# 🗺️ Folium Map (30/60/90 layers, no legend)
# ---------------------------------------
def get_colormap(df, column_name):
    values = df[column_name]
    min_val = round(values.min())
    max_val = round(values.max())
    if min_val == max_val:
        min_val = 0
    colors = cm.linear.Spectral_03.to_step(10).colors
    cmap = cm.LinearColormap(colors, vmin=min_val, vmax=max_val).to_step(10)
    return cmap  # No caption added

def create_layer(gdf, column, name):
    cmap = get_colormap(gdf, column)
    style_fn = lambda x: {
        "weight": 0.5,
        'color': 'black',
        'fillColor': cmap(x['properties'][column]),
        'fillOpacity': 0.75
    }
    geo_layer = folium.GeoJson(
        gdf,
        name=name,
        style_function=style_fn,
        highlight_function=lambda x: {
            'fillColor': '#000000',
            'color': '#000000',
            'fillOpacity': 0.50,
            'weight': 0.1
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['tooltip_html'],
            aliases=[''],
            sticky=True,
            parse_html=True
        )
    )
    return geo_layer

# Create base map
map_afr1 = folium.Map(location=[7.9455, -1.0232], zoom_start=7, tiles=None)
folium.TileLayer('CartoDB positron', name="Light Map", control=False).add_to(map_afr1)

# Layers: 30-day, 60-day, 90-day
layer30 = create_layer(gdf_afr1, '30_day_utilization', '30-Day Utilization')
layer60 = create_layer(gdf_afr1, '60_day_utilization', '60-Day Utilization')
layer90 = create_layer(gdf_afr1, '90_day_utilization', '90-Day Utilization')

# Add layers to map
map_afr1.add_child(layer30)
map_afr1.add_child(layer60)
map_afr1.add_child(layer90)

# Toggle control
folium.LayerControl(collapsed=False).add_to(map_afr1)

# ✅ Display final map
map_afr1
