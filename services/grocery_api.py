import hashlib
import logging
import re
from datetime import timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

API_URL = "https://grocery-api2.p.rapidapi.com/amazon"
SOURCE_NAME = "rapidapi_amazon_grocery"
PAUSE_CACHE_PREFIX = "grocery_api_paused"


def _api_headers():
    if not getattr(settings, "GROCERY_API_ENABLED", True):
        return None
    key = (getattr(settings, "RAPIDAPI_KEY", "") or "").strip()
    host = getattr(settings, "RAPIDAPI_HOST", "grocery-api2.p.rapidapi.com")
    if not key or key.lower().startswith(("your_", "replace_", "changeme")):
        return None
    return {
        "x-rapidapi-key": key,
        "x-rapidapi-host": host,
    }


def is_configured():
    return bool(_api_headers())


def is_enabled():
    return bool(getattr(settings, "GROCERY_API_ENABLED", True))


def _pause_cache_key(country):
    host = getattr(settings, "RAPIDAPI_HOST", "grocery-api2.p.rapidapi.com")
    return f"{PAUSE_CACHE_PREFIX}:{host}:{country}"


def _retry_after_seconds(response):
    if response is None:
        return None
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return max(int(retry_after), 1)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(retry_after)
        if retry_at:
            if timezone.is_naive(retry_at):
                retry_at = timezone.make_aware(retry_at, timezone=datetime_timezone.utc)
            return max(int((retry_at - timezone.now()).total_seconds()), 1)
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def _pause_api(country, seconds, reason):
    seconds = max(int(seconds or 0), 1)
    cache.set(_pause_cache_key(country), reason, seconds)


def _pause_seconds_for_status(status_code, response=None):
    if status_code == 403:
        return getattr(settings, "GROCERY_API_FORBIDDEN_PAUSE_SECONDS", 60 * 60)
    if status_code == 429:
        return (
            _retry_after_seconds(response)
            or getattr(settings, "GROCERY_API_RATE_LIMIT_PAUSE_SECONDS", 60 * 15)
        )
    return getattr(settings, "GROCERY_API_FAILURE_CACHE_SECONDS", 60 * 5)


def _first_product_list(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("products", "results", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _first_product_list(value)
            if nested:
                return nested
    return []


def _first_value(data, *keys, default=""):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _parse_price(value):
    if isinstance(value, dict):
        value = _first_value(value, "value", "amount", "current", "raw", "text")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    if not value:
        return Decimal("0.00")

    match = re.search(r"(\d+(?:[,.]\d{1,2})?)", str(value).replace(",", ""))
    if not match:
        return Decimal("0.00")
    try:
        return Decimal(match.group(1)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _parse_int(value):
    if isinstance(value, int):
        return value
    if not value:
        return 0
    match = re.search(r"\d+", str(value).replace(",", ""))
    return int(match.group(0)) if match else 0


def _parse_rating(value):
    if value in (None, ""):
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    rating = Decimal(match.group(0)).quantize(Decimal("0.1"))
    return max(Decimal("0.0"), min(Decimal("5.0"), rating))


def _image_url(raw):
    image = _first_value(raw, "image", "image_url", "thumbnail", "product_photo")
    if isinstance(image, list) and image:
        image = image[0]
    if isinstance(image, dict):
        image = _first_value(image, "url", "src")
    images = raw.get("images")
    if not image and isinstance(images, list) and images:
        first = images[0]
        image = _first_value(first, "url", "src") if isinstance(first, dict) else first
    return image or ""


def normalize_product(raw, fallback_category="Grocery"):
    title = _first_value(raw, "title", "name", "product_title")
    if not title:
        return None

    api_id = _first_value(raw, "asin", "id", "product_id", "url", default=title)
    stable_id = hashlib.sha256(str(api_id).encode("utf-8")).hexdigest()[:32]
    price = _parse_price(_first_value(raw, "price", "current_price", "price_raw", "price_string"))
    list_price = _parse_price(_first_value(raw, "list_price", "original_price", "old_price", "was_price"))
    rating = _parse_rating(_first_value(raw, "rating", "stars", "reviews_rating"))
    review_count = _parse_int(_first_value(raw, "reviews", "review_count", "ratings_total"))
    availability = _first_value(raw, "availability", "stock", default="In Stock")
    category = _first_value(raw, "category", "department", default=fallback_category)
    description = _first_value(raw, "description", "feature", "subtitle", default=title)

    return {
        "api_source": SOURCE_NAME,
        "api_product_id": stable_id,
        "title": str(title).strip(),
        "description": str(description).strip(),
        "price": list_price if list_price and list_price > price else price,
        "discount_price": price if list_price and list_price > price else None,
        "external_image_url": _image_url(raw),
        "category_name": str(category or fallback_category).strip()[:100],
        "availability": str(availability).strip()[:120],
        "is_out_of_stock": "out" in str(availability).lower() and "stock" in str(availability).lower(),
        "api_rating": rating,
        "api_review_count": review_count,
        "api_payload": raw,
    }


def search_products(query, page=1, country=None):
    query = (query or "grocery").strip()
    page = max(int(page or 1), 1)
    country = country or getattr(settings, "GROCERY_API_COUNTRY", "us")
    query_hash = hashlib.sha256(query.lower().encode("utf-8")).hexdigest()[:24]
    cache_key = f"grocery_api:{country}:{query_hash}:{page}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    pause_reason = cache.get(_pause_cache_key(country))
    if pause_reason:
        logger.debug("Skipping RapidAPI Grocery API request for query=%s page=%s: %s", query, page, pause_reason)
        return []

    if not is_enabled():
        logger.debug("RapidAPI Grocery API is disabled.")
        return []

    headers = _api_headers()
    if not headers:
        logger.info("RapidAPI Grocery API credentials are not configured.")
        return []

    params = {"query": query, "country": country, "page": page}
    try:
        response = requests.get(API_URL, headers=headers, params=params, timeout=12)
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else None
        if status_code in (403, 429):
            seconds = _pause_seconds_for_status(status_code, response)
            reason = f"RapidAPI returned HTTP {status_code}; paused requests for {seconds} seconds."
            _pause_api(country, seconds, reason)
            logger.warning(
                "RapidAPI Grocery API paused after HTTP %s for query=%s page=%s; retry in %s seconds.",
                status_code,
                query,
                page,
                seconds,
            )
        else:
            logger.warning("RapidAPI Grocery API request failed for query=%s page=%s: %s", query, page, exc)
        cache.set(cache_key, [], _pause_seconds_for_status(status_code, response))
        return []
    except requests.RequestException as exc:
        logger.warning("RapidAPI Grocery API request failed for query=%s page=%s: %s", query, page, exc)
        cache.set(cache_key, [], getattr(settings, "GROCERY_API_FAILURE_CACHE_SECONDS", 60 * 5))
        return []
    except ValueError:
        logger.warning("RapidAPI Grocery API returned non-JSON data for query=%s page=%s", query, page)
        cache.set(cache_key, [], getattr(settings, "GROCERY_API_FAILURE_CACHE_SECONDS", 60 * 5))
        return []

    products = [
        product
        for product in (normalize_product(item, fallback_category=query) for item in _first_product_list(payload))
        if product
    ]
    cache.set(cache_key, products, getattr(settings, "GROCERY_API_CACHE_SECONDS", 60 * 30))
    return products


def get_fruits():
    return search_products("fruits")


def get_vegetables():
    return search_products("vegetable")


def get_dairy_products():
    return search_products("dairy products")


def get_snacks():
    return search_products("snacks")


def get_beverages():
    return search_products("beverages")
