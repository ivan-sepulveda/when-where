"""
Shared helper for computing the direct (great-circle) distance between
two points on Earth, given their latitude/longitude -- e.g. an origin
city and a destination city from tourist_cities.json, or an airport pair
from airports.json/airports_by_country.json. This is straight-line
"as the crow flies" distance, not an actual flight path/route distance
(which would need airline_routes.csv or similar) -- see the notes on
build_airports_by_country.py for why straight-line distance was chosen
as the starting point for this project's scoring instead of relying on
route data.

Uses the haversine formula, which treats Earth as a perfect sphere. This
is a small (~0.3%) simplification versus Earth's real oblate-spheroid
shape (Vincenty's formula is more precise but far more complex) -- fine
for travel-scoring purposes, and it's the same standard method used by
tools like GreatCircleMapper and Azure Maps' great-circle distance API.

Usage (as a library):
    from distance_calculator import calculate_distance
    calculate_distance(40.7128, -74.0060, 51.5074, -0.1278)          # NYC -> London, km
    calculate_distance(40.7128, -74.0060, 51.5074, -0.1278, unit="mi")  # same, in miles
"""

import math

# Mean Earth radius (IUGG value), the constant conventionally used with
# the haversine formula.
EARTH_RADIUS_KM = 6371.0088
KM_TO_MILES = 0.621371


def calculate_distance(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    unit: str = "km",
) -> float:
    """
    Great-circle distance between (origin_lat, origin_lon) and
    (dest_lat, dest_lon), in kilometers by default (pass unit="mi" for
    miles). Latitude/longitude are in decimal degrees.
    """
    if unit not in ("km", "mi"):
        raise ValueError(f"unit must be 'km' or 'mi', got {unit!r}")

    lat1, lon1, lat2, lon2 = (
        math.radians(origin_lat),
        math.radians(origin_lon),
        math.radians(dest_lat),
        math.radians(dest_lon),
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    central_angle = 2 * math.asin(math.sqrt(a))

    distance_km = EARTH_RADIUS_KM * central_angle
    return distance_km * KM_TO_MILES if unit == "mi" else distance_km
