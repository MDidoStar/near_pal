"""Country > Governorate > City (offline file) > Neighborhood (OpenStreetMap)."""
import json
from pathlib import Path

import requests
import streamlit as st

# locations.json: {country: {governorate: [[city, lat, lon], ...]}}
# Source: github.com/dr5hn/countries-states-cities-database (ODbL)
DATA_FILE = Path(__file__).resolve().parent.parent / "locations.json"

# OpenStreetMap Overpass servers, tried in order until one answers
OVERPASS_URLS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


@st.cache_data(show_spinner=False)
def load_locations():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=24 * 3600, show_spinner="Loading neighborhoods...")
def get_neighborhoods(lat, lon, radius_m=10000):
    query = f"""
    [out:json][timeout:25];
    (
      node["place"~"^(suburb|neighbourhood|quarter)$"](around:{radius_m},{lat},{lon});
      way["place"~"^(suburb|neighbourhood|quarter)$"](around:{radius_m},{lat},{lon});
      relation["place"~"^(suburb|neighbourhood|quarter)$"](around:{radius_m},{lat},{lon});
    );
    out tags;
    """
    elements = None
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query},
                                 headers={"User-Agent": "nearpal/1.0"}, timeout=20)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except (requests.RequestException, ValueError):
            continue
    if elements is None:
        raise ConnectionError("No Overpass server responded")
    names = {(el.get("tags", {}).get("name:en") or el.get("tags", {}).get("name")) for el in elements}
    return sorted(n for n in names if n)


def location_picker(key="loc"):
    """Cascading selectboxes. Returns dict(country, governorate, city, neighborhood)."""
    locations = load_locations()
    countries = list(locations.keys())
    country = st.selectbox("Country", countries, index=countries.index("Egypt"), key=f"{key}_country")
    governorate = st.selectbox("Governorate", list(locations[country].keys()), key=f"{key}_gov")
    cities = locations[country][governorate]
    city_names = [c[0] for c in cities]
    city = st.selectbox("City", city_names, key=f"{key}_city")
    _, lat, lon = cities[city_names.index(city)]

    neighborhoods = []
    if lat is not None and lon is not None:
        try:
            neighborhoods = get_neighborhoods(lat, lon)
        except ConnectionError:
            st.warning("Couldn't reach OpenStreetMap to load neighborhoods.")
    if neighborhoods:
        neighborhood = st.selectbox("Neighborhood", neighborhoods, key=f"{key}_hood")
    else:
        neighborhood = st.text_input("Neighborhood (none found, type it in)", key=f"{key}_hood_txt")
    return {"country": country, "governorate": governorate, "city": city,
            "neighborhood": neighborhood.strip()}
