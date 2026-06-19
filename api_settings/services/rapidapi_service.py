import logging
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_masked_key():
    key = getattr(settings, "RAPIDAPI_KEY", "") or ""
    if not key:
        return "Not configured"
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def get_api_status():
    key = getattr(settings, "RAPIDAPI_KEY", "") or ""
    host = getattr(settings, "RAPIDAPI_HOST", "") or ""
    enabled = getattr(settings, "GROCERY_API_ENABLED", False)

    if not key or not host:
        return "not_configured"
    if not enabled:
        return "disabled"
    return "configured"


def test_rapidapi_connection():
    host = getattr(settings, "RAPIDAPI_HOST", "") or ""
    key = getattr(settings, "RAPIDAPI_KEY", "") or ""

    if not host or not key:
        return {
            "status_code": None,
            "success": False,
            "message": "API key or host not configured.",
            "response": "",
            "timestamp": timezone.now().isoformat(),
        }

    url = f"https://{host}"
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": host,
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        success = response.status_code == 200

        if response.status_code == 403:
            message = "Invalid API key or access denied."
        elif response.status_code == 429:
            message = "Rate limit exceeded. Try again later."
        elif response.status_code == 404:
            message = "API endpoint not found. Check the host configuration."
        elif success:
            message = "API connected successfully."
        else:
            message = f"Unexpected status code: {response.status_code}"

        return {
            "status_code": response.status_code,
            "success": success,
            "message": message,
            "response": response.text[:500],
            "timestamp": timezone.now().isoformat(),
        }
    except requests.Timeout:
        return {
            "status_code": None,
            "success": False,
            "message": "Connection timed out. Check your network or API host.",
            "response": "",
            "timestamp": timezone.now().isoformat(),
        }
    except requests.ConnectionError:
        return {
            "status_code": None,
            "success": False,
            "message": "Connection failed. Check your network connection.",
            "response": "",
            "timestamp": timezone.now().isoformat(),
        }
    except requests.RequestException as exc:
        logger.warning("RapidAPI test connection failed: %s", exc)
        return {
            "status_code": None,
            "success": False,
            "message": f"Request error: {exc}",
            "response": "",
            "timestamp": timezone.now().isoformat(),
        }
