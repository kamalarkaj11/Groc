"""
Utility functions for login activity tracking, device/browser detection,
and IP geolocation.
"""
import logging
import re
import urllib.request
import urllib.error
import ssl
import json

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract the client IP address from the request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def get_user_agent_info(request):
    """
    Parse User-Agent string to extract browser, OS, and device type.
    Returns dict with keys: browser, os, device
    """
    ua_string = request.META.get('HTTP_USER_AGENT', '')
    if not ua_string:
        return {'browser': 'Unknown', 'os': 'Unknown', 'device': 'Unknown'}

    ua_lower = ua_string.lower()

    # Detect browser
    browser = 'Unknown'
    if 'edg/' in ua_lower:
        browser = 'Microsoft Edge'
    elif 'opr/' in ua_lower or 'opera' in ua_lower:
        browser = 'Opera'
    elif 'chrome' in ua_lower and 'chromium' not in ua_lower:
        browser = 'Google Chrome'
    elif 'firefox' in ua_lower:
        browser = 'Mozilla Firefox'
    elif 'safari' in ua_lower and 'chrome' not in ua_lower:
        browser = 'Safari'
    elif 'msie' in ua_lower or 'trident' in ua_lower:
        browser = 'Internet Explorer'

    # Detect OS
    os = 'Unknown'
    if 'windows' in ua_lower:
        if 'nt 10' in ua_lower:
            os = 'Windows 10/11'
        elif 'nt 6.3' in ua_lower:
            os = 'Windows 8.1'
        elif 'nt 6.2' in ua_lower:
            os = 'Windows 8'
        elif 'nt 6.1' in ua_lower:
            os = 'Windows 7'
        else:
            os = 'Windows'
    elif 'mac os' in ua_lower or 'macintosh' in ua_lower:
        os = 'macOS'
    elif 'iphone' in ua_lower or 'ipad' in ua_lower:
        os = 'iOS'
    elif 'android' in ua_lower:
        os = 'Android'
    elif 'linux' in ua_lower:
        os = 'Linux'

    # Detect device type
    device = 'Desktop'
    if 'mobile' in ua_lower or 'iphone' in ua_lower or 'android' in ua_lower:
        device = 'Mobile'
    elif 'tablet' in ua_lower or 'ipad' in ua_lower or 'tab' in ua_lower:
        device = 'Tablet'

    return {'browser': browser, 'os': os, 'device': device}


def get_location_from_ip(ip_address):
    """
    Get approximate location from IP address using ip-api.com.
    Returns dict with keys: city, state, country
    """
    if not ip_address or ip_address in ('127.0.0.1', 'localhost', '::1'):
        return {'city': '', 'state': '', 'country': 'Localhost'}

    try:
        # Using ip-api.com (free, no API key required for non-commercial use)
        url = f"http://ip-api.com/json/{ip_address}?fields=status,city,regionName,country"
        req = urllib.request.Request(url, headers={'User-Agent': 'GroceryHub/1.0'})
        
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        if data.get('status') == 'success':
            return {
                'city': data.get('city', ''),
                'state': data.get('regionName', ''),
                'country': data.get('country', ''),
            }
    except Exception as exc:
        logger.warning('IP geolocation failed for %s: %s', ip_address, exc)
    
    return {'city': '', 'state': '', 'country': ''}


def detect_login_method(request, user=None):
    """
    Detect the login method used based on request and session data.
    Returns one of: 'password', 'otp', 'google', 'facebook', 'twitter', 'github', 'other'
    """
    # Check session for OTP login
    if request.session.get('phone_for_otp') or request.session.get('signup_phone'):
        return 'otp'
    
    # Check for social login (can be extended based on your social auth implementation)
    # This depends on how you're implementing social auth
    # For now, we'll check common patterns
    social_auth_path = request.path
    if 'social' in social_auth_path or 'oauth' in social_auth_path:
        if 'google' in social_auth_path:
            return 'google'
        elif 'facebook' in social_auth_path:
            return 'facebook'
        elif 'twitter' in social_auth_path:
            return 'twitter'
        elif 'github' in social_auth_path:
            return 'github'
        return 'other'
    
    # Default to password login
    return 'password'


def check_if_new_login(user, ip_address, user_agent, device_type, browser, city, country):
    """
    Check if this login is from a new device/browser/location.
    Returns dict with flags: is_new_device, is_new_browser, is_new_location
    """
    is_new_device = False
    is_new_browser = False
    is_new_location = False
    
    # Get recent login activities (last 30 days)
    recent_logins = user.login_activities.filter(
        created_at__gte=timezone.now() - timezone.timedelta(days=30)
    )
    
    if not recent_logins.exists():
        # First login ever
        is_new_device = True
        is_new_browser = True
        is_new_location = True
        return {
            'is_new_device': is_new_device,
            'is_new_browser': is_new_browser,
            'is_new_location': is_new_location,
        }
    
    # Check device type
    if device_type and device_type != 'unknown':
        previous_devices = set(recent_logins.values_list('device_type', flat=True).distinct())
        if device_type not in previous_devices:
            is_new_device = True
    
    # Check browser
    if browser and browser != 'Unknown':
        # Extract browser name without version for comparison
        browser_name = browser.split()[0] if browser else 'Unknown'
        previous_browsers = set()
        for login in recent_logins:
            if login.browser:
                prev_browser_name = login.browser.split()[0]
                previous_browsers.add(prev_browser_name)
        if browser_name not in previous_browsers:
            is_new_browser = True
    
    # Check location (city + country)
    if city or country:
        previous_locations = set()
        for login in recent_logins:
            loc_key = f"{login.city}|{login.country}"
            previous_locations.add(loc_key)
        current_location = f"{city}|{country}"
        if current_location not in previous_locations and (city or country):
            is_new_location = True
    
    return {
        'is_new_device': is_new_device,
        'is_new_browser': is_new_browser,
        'is_new_location': is_new_location,
    }


def determine_security_status(is_new_device, is_new_browser, is_new_location):
    """
    Determine the security status based on new device/browser/location flags.
    """
    if is_new_device and is_new_browser and is_new_location:
        return 'suspicious'
    elif is_new_device:
        return 'new_device'
    elif is_new_browser:
        return 'new_browser'
    elif is_new_location:
        return 'new_location'
    return 'success'


def create_login_activity(user, request, login_method='password'):
    """
    Create a LoginActivity record for a successful login.
    Returns the created LoginActivity instance.
    """
    from .models import LoginActivity
    
    ip_address = get_client_ip(request)
    ua_info = get_user_agent_info(request)
    location = get_location_from_ip(ip_address)
    
    now = timezone.localtime(timezone.now())
    login_date = now.date()
    login_time = now.time()
    
    # Check if this is a new device/browser/location
    new_login_flags = check_if_new_login(
        user=user,
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        device_type=ua_info.get('device', 'unknown'),
        browser=ua_info.get('browser', 'Unknown'),
        city=location.get('city', ''),
        country=location.get('country', ''),
    )
    
    # Determine security status
    security_status = determine_security_status(
        new_login_flags['is_new_device'],
        new_login_flags['is_new_browser'],
        new_login_flags['is_new_location'],
    )
    
    # Create login activity record
    login_activity = LoginActivity.objects.create(
        user=user,
        login_date=login_date,
        login_time=login_time,
        device_type=ua_info.get('device', 'unknown'),
        browser=ua_info.get('browser', 'Unknown'),
        operating_system=ua_info.get('os', 'Unknown'),
        ip_address=ip_address,
        city=location.get('city', ''),
        state=location.get('state', ''),
        country=location.get('country', ''),
        login_method=login_method,
        security_status=security_status,
        is_new_device=new_login_flags['is_new_device'],
        is_new_browser=new_login_flags['is_new_browser'],
        is_new_location=new_login_flags['is_new_location'],
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )
    
    logger.info(
        'Login activity created: user=%s, method=%s, status=%s, new_device=%s, new_browser=%s, new_location=%s',
        user.username, login_method, security_status,
        new_login_flags['is_new_device'], new_login_flags['is_new_browser'], new_login_flags['is_new_location']
    )
    
    return login_activity