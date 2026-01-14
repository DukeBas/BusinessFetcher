import streamlit as st
import requests
import pandas as pd
import io
import re

# Overpass API requires a custom User-Agent to identify the application.
HEADERS = {
    'User-Agent': 'BusinessEntityFetcher/1.0'
}
OVERPASS_URL = "http://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Lists for filtering logic
AMENITY_WHITELIST = [
    "restaurant", "cafe", "fast_food", "bar", "pub", "ice_cream", "food_court",
    "bank", "bureau_de_change", "pharmacy", "dentist", "doctors", "clinic",
    "veterinary", "cinema", "theatre", "nightclub", "casino", "marketplace",
    "post_office", "fuel", "car_rental", "car_wash"
]
AMENITY_REGEX = "|".join(AMENITY_WHITELIST)

SHOP_BLACKLIST = ["vacant", "no", "disused"]
SHOP_EXCLUDE_REGEX = "|".join(SHOP_BLACKLIST)


def geocode_location(query):
    """
    Determines if the input is 'lat, lon' or a place name.
    Returns (lat, lon) tuple or raises an error.
    """
    # 1. Try to parse as specific coordinates first (e.g. "52.3, 4.9")
    try:
        parts = query.split(',')
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        pass  # Not coordinates, proceed to geocoding

    # 2. Use Nominatim API for name search
    params = {'q': query, 'format': 'json', 'limit': 1}
    response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS)
    response.raise_for_status()
    data = response.json()

    if not data:
        raise ValueError(f"Could not find location: '{query}'")

    return float(data[0]['lat']), float(data[0]['lon'])


def get_osm_data(lat, lon, radius_km):
    """
    Queries the Overpass API for business entities within a specific radius.
    Returns a DataFrame or raises an error.
    """
    radius_meters = radius_km * 1000

    # Overpass QL Query
    overpass_query = f"""
    [out:json][timeout:25];
    (
      // 1. Amenities: Commercial whitelist
      node["amenity"~"^({AMENITY_REGEX})$"](around:{radius_meters},{lat},{lon});
      way["amenity"~"^({AMENITY_REGEX})$"](around:{radius_meters},{lat},{lon});
      relation["amenity"~"^({AMENITY_REGEX})$"](around:{radius_meters},{lat},{lon});

      // 2. Shops: All valid shops
      node["shop"]["shop"!~"^({SHOP_EXCLUDE_REGEX})$"](around:{radius_meters},{lat},{lon});
      way["shop"]["shop"!~"^({SHOP_EXCLUDE_REGEX})$"](around:{radius_meters},{lat},{lon});
      relation["shop"]["shop"!~"^({SHOP_EXCLUDE_REGEX})$"](around:{radius_meters},{lat},{lon});

      // 3. Offices: All offices
      node["office"](around:{radius_meters},{lat},{lon});
      way["office"](around:{radius_meters},{lat},{lon});
      relation["office"](around:{radius_meters},{lat},{lon});

      // 4. Tourism: Hotels and accommodation
      node["tourism"~"^(hotel|hostel|guest_house|motel)$"](around:{radius_meters},{lat},{lon});
      way["tourism"~"^(hotel|hostel|guest_house|motel)$"](around:{radius_meters},{lat},{lon});
      relation["tourism"~"^(hotel|hostel|guest_house|motel)$"](around:{radius_meters},{lat},{lon});

      // 5. Craft: Skilled trades
      node["craft"](around:{radius_meters},{lat},{lon});
      way["craft"](around:{radius_meters},{lat},{lon});
      relation["craft"](around:{radius_meters},{lat},{lon});
      
      // 6. Leisure: Commercial leisure
      node["leisure"~"^(fitness_centre|sports_centre|bowling_alley|water_park)$"](around:{radius_meters},{lat},{lon});
      way["leisure"~"^(fitness_centre|sports_centre|bowling_alley|water_park)$"](around:{radius_meters},{lat},{lon});
      relation["leisure"~"^(fitness_centre|sports_centre|bowling_alley|water_park)$"](around:{radius_meters},{lat},{lon});
    );
    out center;
    """

    response = requests.get(OVERPASS_URL, params={
                            'data': overpass_query}, headers=HEADERS)

    # Custom error handling for 500/504 errors (Server overload) vs 400 (Bad Request)
    if response.status_code >= 500:
        raise ConnectionError(
            "The OpenStreetMap server is currently overloaded. Please wait a few seconds and try again.")

    response.raise_for_status()

    return response.json()


def process_data(data):
    """
    Normalizes JSON data and applies categorization logic.
    """
    elements = data.get('elements', [])
    if not elements:
        return pd.DataFrame()

    df = pd.json_normalize(elements)

    def categorize_business(row):
        # Helper to categorize based on tags
        tags = row.get('tags', {}) if isinstance(row.get('tags'), dict) else {}

        if 'tags.shop' in row and pd.notna(row['tags.shop']):
            return f"Shop: {row['tags.shop']}"
        if 'tags.amenity' in row and pd.notna(row['tags.amenity']):
            return f"Amenity: {row['tags.amenity']}"
        if 'tags.office' in row and pd.notna(row['tags.office']):
            return f"Office: {row['tags.office']}"
        if 'tags.tourism' in row and pd.notna(row['tags.tourism']):
            return f"Tourism: {row['tags.tourism']}"
        if 'tags.craft' in row and pd.notna(row['tags.craft']):
            return f"Craft: {row['tags.craft']}"
        if 'tags.leisure' in row and pd.notna(row['tags.leisure']):
            return f"Leisure: {row['tags.leisure']}"
        return "Other"

    df['business_category'] = df.apply(categorize_business, axis=1)
    return df


# Streamlit App Layout
st.set_page_config(page_title="OSM Business Extractor", page_icon="🌍")

st.title("🌍 OSM Business Data Extractor")
st.markdown(
    "Enter a location name (e.g., 'Amsterdam') OR coordinates (e.g., '52.37, 4.90') and a radius.")

# Input layout
col1, col2 = st.columns([3, 1])
with col1:
    location_query = st.text_input(
        "Location Name or Lat,Lon", value="Amsterdam Centraal")
with col2:
    radius_input = st.number_input(
        "Radius (km)", value=1.0, min_value=0.1, max_value=50.0)

if st.button("Get Data", type="primary"):
    with st.spinner("Locating and querying OpenStreetMap..."):
        try:
            # Geocode the input string
            lat, lon = geocode_location(location_query)
            st.info(f"Searching around: {lat:.5f}, {lon:.5f}")

            # Fetch Data
            json_data = get_osm_data(lat, lon, radius_input)

            # Process Data
            df = process_data(json_data)

            if df.empty:
                st.warning("No data found for this location/radius.")
            else:
                st.success(f"Found {len(df)} business entities!")

                # Sort DataFrame for better readability
                sort_cols = []
                if 'business_category' in df.columns:
                    sort_cols.append('business_category')
                if 'tags.name' in df.columns:
                    sort_cols.append('tags.name')

                if sort_cols:
                    df = df.sort_values(by=sort_cols, ascending=True)

                # Show Category Breakdown
                st.subheader("Business Categories")
                st.bar_chart(df['business_category'].value_counts())

                # Prepare DataFrame for Display and Download
                desired_cols = ['business_category', 'tags.name', 'tags.addr:street',
                                'tags.addr:housenumber', 'tags.addr:postcode', 'tags.website']
                existing_cols = [c for c in desired_cols if c in df.columns]

                # Show Category Breakdown
                st.subheader("Top 10 Business Categories")
                st.bar_chart(df['business_category'].value_counts().head(10))

                # Display Preview
                st.subheader("Data Preview (First 50 Rows)")
                st.dataframe(df[existing_cols].head(50))

                # Excel Download Logic (In-Memory)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='OSM Data')

                st.download_button(
                    label="📥 Download Excel File",
                    data=buffer.getvalue(),
                    file_name="osm_business_data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        except ValueError as ve:
            st.error(f"Input Error: {ve}")
        except ConnectionError as ce:
            st.error(str(ce))
        except requests.exceptions.RequestException as re:
            st.error(f"Network Error: {re}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
