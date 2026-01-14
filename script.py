import requests
import pandas as pd

# Configuration
LAT, LON = 52.3791283, 4.900272
RADIUS_KM = 1




# Overpass API requires a custom User-Agent to identify the application.
HEADERS = {
    'User-Agent': 'BusinessEntityFetcher/1.0'
}

# AMENITY: Strict whitelist of commercial-focused amenities
# Excludes public utilities like 'bench', 'toilets', 'parking'.
AMENITY_WHITELIST = [
    "restaurant", "cafe", "fast_food", "bar", "pub", "ice_cream", "food_court",
    "bank", "bureau_de_change", "pharmacy", "dentist", "doctors", "clinic",
    "veterinary", "cinema", "theatre", "nightclub", "casino", "marketplace",
    "post_office", "fuel", "car_rental", "car_wash"
]
AMENITY_REGEX = "|".join(AMENITY_WHITELIST)

# SHOP: Blacklist (include most, exclude non-business states)
SHOP_BLACKLIST = ["vacant", "no", "disused"]
SHOP_EXCLUDE_REGEX = "|".join(SHOP_BLACKLIST)


# Using Overpass QL Union to combine different keys.
# [out:json][timeout:25]; -> Output format and server timeout.
# (around:radius,lat,lon) -> Spatial filter applied to each node/way/relation.
radius_meters = RADIUS_KM * 1000
overpass_query = f"""
[out:json][timeout:25];
(
  // 1. Amenities: Commercial whitelist
  node["amenity"~"^({AMENITY_REGEX})$"](around:{radius_meters},{LAT},{LON});
  way["amenity"~"^({AMENITY_REGEX})$"](around:{radius_meters},{LAT},{LON});
  relation["amenity"~"^({AMENITY_REGEX})$"](around:{radius_meters},{LAT},{LON});

  // 2. Shops: All valid shops
  node["shop"]["shop"!~"^({SHOP_EXCLUDE_REGEX})$"](around:{radius_meters},{LAT},{LON});
  way["shop"]["shop"!~"^({SHOP_EXCLUDE_REGEX})$"](around:{radius_meters},{LAT},{LON});
  relation["shop"]["shop"!~"^({SHOP_EXCLUDE_REGEX})$"](around:{radius_meters},{LAT},{LON});

  // 3. Offices: All offices (commercial/professional)
  node["office"](around:{radius_meters},{LAT},{LON});
  way["office"](around:{radius_meters},{LAT},{LON});
  relation["office"](around:{radius_meters},{LAT},{LON});

  // 4. Tourism: Hotels and accommodation
  node["tourism"~"^(hotel|hostel|guest_house|motel)$"](around:{radius_meters},{LAT},{LON});
  way["tourism"~"^(hotel|hostel|guest_house|motel)$"](around:{radius_meters},{LAT},{LON});
  relation["tourism"~"^(hotel|hostel|guest_house|motel)$"](around:{radius_meters},{LAT},{LON});

  // 5. Craft: Skilled trades (often distinct from shops)
  node["craft"](around:{radius_meters},{LAT},{LON});
  way["craft"](around:{radius_meters},{LAT},{LON});
  relation["craft"](around:{radius_meters},{LAT},{LON});
  
  // 6. Leisure: Commercial leisure (gyms, etc)
  node["leisure"~"^(fitness_centre|sports_centre|bowling_alley|water_park)$"](around:{radius_meters},{LAT},{LON});
  way["leisure"~"^(fitness_centre|sports_centre|bowling_alley|water_park)$"](around:{radius_meters},{LAT},{LON});
  relation["leisure"~"^(fitness_centre|sports_centre|bowling_alley|water_park)$"](around:{radius_meters},{LAT},{LON});
);
out center;
"""

# Query execution
OVERPASS_URL = "http://overpass-api.de/api/interpreter"

try:
    response = requests.get(OVERPASS_URL, params={'data': overpass_query}, headers=HEADERS)
    response.raise_for_status() # Raise error for 4xx/5xx status codes
    
    data = response.json()
    elements = data.get('elements', [])
    
    print(f"Total Business Entities Found: {len(elements)}")

    if elements:
        df = pd.json_normalize(elements)

        # Categorization Logic: Hierarchical assignment of business type
        def categorize_business(row):
            tags = row.get('tags', {})
            # Use 'get' with None default to avoid KeyErrors if column missing in normalize
            if pd.notna(row.get('tags.shop')): return f"Shop: {row['tags.shop']}"
            if pd.notna(row.get('tags.amenity')): return f"Amenity: {row['tags.amenity']}"
            if pd.notna(row.get('tags.office')): return f"Office: {row['tags.office']}"
            if pd.notna(row.get('tags.tourism')): return f"Tourism: {row['tags.tourism']}"
            if pd.notna(row.get('tags.craft')): return f"Craft: {row['tags.craft']}"
            if pd.notna(row.get('tags.leisure')): return f"Leisure: {row['tags.leisure']}"
            return "Other"

        df['business_category'] = df.apply(categorize_business, axis=1)

        # Basic analysis
        print("\nTop 10 Business Categories:")
        print(df['business_category'].value_counts().head(10))
        
        # Display sample columns of interest
        cols_to_show = ['business_category', 'tags.name', 'tags.addr:postcode']
        # Filter for columns that actually exist in the dataframe
        valid_cols = [c for c in cols_to_show if c in df.columns]
        print(f"\nPreview:\n{df[valid_cols].head(10)}")

        # Save to excel, only the cols_to_show
        df.to_excel("business_entities.xlsx", columns=valid_cols, index=False)


    else:
        print("No data found for the specified radius.")

except requests.exceptions.RequestException as e:
    print(f"API Request Error: {e}")
except Exception as e:
    print(f"Processing Error: {e}")