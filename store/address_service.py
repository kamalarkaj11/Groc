import json
import logging
import ssl
import time
import urllib.request as urllib_request
from urllib.parse import quote
from django.core.cache import cache

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "GroceryHub/1.0"
CACHE_PREFIX_SEARCH = "addr_search_"
CACHE_PREFIX_REVERSE = "addr_reverse_"
CACHE_TIMEOUT = 3600
RATE_LIMIT_DELAY = 1.0

_last_request_time = 0


def _respect_rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)
    _last_request_time = time.time()


def _build_address_parts(address_data):
    parts = {}
    if not address_data:
        return parts
    parts["house_number"] = address_data.get("house_number", "")
    parts["road"] = address_data.get("road", "")
    parts["street"] = (
        address_data.get("road", "")
        or address_data.get("pedestrian", "")
        or address_data.get("footway", "")
        or address_data.get("street", "")
    )
    parts["area"] = (
        address_data.get("suburb", "")
        or address_data.get("neighbourhood", "")
        or address_data.get("quarter", "")
    )
    parts["locality"] = (
        address_data.get("city_district", "")
        or address_data.get("county", "")
    )
    parts["village"] = address_data.get("village", "")
    parts["town"] = address_data.get("town", "")
    parts["city"] = (
        address_data.get("city", "")
        or address_data.get("town", "")
        or address_data.get("village", "")
        or address_data.get("municipality", "")
    )
    parts["district"] = (
        address_data.get("county", "")
        or address_data.get("state_district", "")
        or address_data.get("district", "")
    )
    parts["state"] = address_data.get("state", "")
    parts["country"] = address_data.get("country", "India")
    parts["postcode"] = address_data.get("postcode", "")
    parts["country_code"] = address_data.get("country_code", "")
    return parts


def _build_full_address(address_data, display_name=""):
    if display_name:
        return display_name
    parts_list = []
    for key in ("house_number", "road", "suburb", "neighbourhood",
                "city", "town", "village", "state", "postcode", "country"):
        val = address_data.get(key, "")
        if val:
            parts_list.append(val)
    return ", ".join(parts_list) if parts_list else ""


def search_address(query, limit=8):
    if not query or len(query.strip()) < 2:
        return []
    query = query.strip()
    cache_key = f"{CACHE_PREFIX_SEARCH}{query}_{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        _respect_rate_limit()
        encoded_query = quote(query)
        url = (
            f"{NOMINATIM_SEARCH_URL}?"
            f"q={encoded_query}&format=jsonv2&addressdetails=1&limit={limit}"
        )
        req = urllib_request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl._create_unverified_context()
        with urllib_request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = []
        for item in data:
            address_data = item.get("address", {})
            addr_parts = _build_address_parts(address_data)
            bounding_box = item.get("boundingbox", [])
            result = {
                "place_id": str(item.get("place_id", "")),
                "display_name": item.get("display_name", ""),
                "latitude": item.get("lat", ""),
                "longitude": item.get("lon", ""),
                "osm_type": item.get("osm_type", ""),
                "osm_id": str(item.get("osm_id", "")),
                "bounding_box": ",".join(bounding_box) if bounding_box else "",
                "type": item.get("type", ""),
                "category": item.get("category", ""),
                "importance": item.get("importance", 0),
                **addr_parts,
            }
            results.append(result)
        cache.set(cache_key, results, CACHE_TIMEOUT)
        return results
    except Exception as exc:
        logger.error("[address_service] search_address error: %s", exc)
        return []


def reverse_geocode(lat, lon):
    cache_key = f"{CACHE_PREFIX_REVERSE}{lat}_{lon}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        _respect_rate_limit()
        url = (
            f"{NOMINATIM_REVERSE_URL}?"
            f"format=jsonv2&lat={lat}&lon={lon}&addressdetails=1"
        )
        req = urllib_request.Request(url, headers={"User-Agent": USER_AGENT})
        ctx = ssl._create_unverified_context()
        with urllib_request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data or data.get("error"):
            return None
        address_data = data.get("address", {})
        addr_parts = _build_address_parts(address_data)
        bounding_box = data.get("boundingbox", [])
        result = {
            "place_id": str(data.get("place_id", "")),
            "display_name": data.get("display_name", ""),
            "latitude": str(lat),
            "longitude": str(lon),
            "osm_type": data.get("osm_type", ""),
            "osm_id": str(data.get("osm_id", "")),
            "bounding_box": ",".join(bounding_box) if bounding_box else "",
            **addr_parts,
        }
        cache.set(cache_key, result, CACHE_TIMEOUT)
        return result
    except Exception as exc:
        logger.error("[address_service] reverse_geocode error: %s", exc)
        return None


def validate_coordinates(lat, lon):
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return {"valid": False, "error": "Invalid coordinate format."}
    if not (-90 <= lat_f <= 90):
        return {"valid": False, "error": "Latitude must be between -90 and 90."}
    if not (-180 <= lon_f <= 180):
        return {"valid": False, "error": "Longitude must be between -180 and 180."}
    return {"valid": True, "latitude": round(lat_f, 6), "longitude": round(lon_f, 6)}
