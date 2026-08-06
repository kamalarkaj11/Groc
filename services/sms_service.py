import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from store.models import NotificationLog, LoginActivity

logger = logging.getLogger(__name__)
SMS_AUTH_LOGGER = logging.getLogger('store.auth_emails')


def _get_client_ip(request):
    """Extract the client IP address from the request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def _get_user_agent_info(request):
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


def _get_customer_info(order):
    """Extract customer name, phone from order and related models."""
    shipping_address = getattr(order, 'shipping_address', None)

    customer_name = order.user.get_full_name() or order.user.username
    if shipping_address and shipping_address.full_name:
        customer_name = shipping_address.full_name

    customer_phone = ''
    if shipping_address and shipping_address.phone:
        customer_phone = shipping_address.phone
    else:
        user_profile = getattr(order.user, 'userprofile', None)
        if user_profile and user_profile.phone_number:
            customer_phone = user_profile.phone_number
        else:
            phone_profile = getattr(order.user, 'phone_profile', None)
            if phone_profile and phone_profile.phone_number:
                customer_phone = phone_profile.phone_number

    return customer_name, customer_phone


def _verify_twilio_credentials():
    """Verify Twilio credentials are configured properly."""
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
    from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)

    if not all([sid, token, from_number]):
        logger.error('Twilio not fully configured. has_sid=%s, has_token=%s, has_from_number=%s', bool(sid), bool(token), bool(from_number))
        return False
    return True


def _get_or_create_notification_log(order):
    """Get existing NotificationLog for the order or create a new one."""
    log = NotificationLog.objects.filter(order=order).first()
    if not log:
        log = NotificationLog.objects.create(
            order=order,
            user=order.user,
            email_status='pending',
            sms_status='pending',
        )
    return log


def send_welcome_sms(user):
    """
    Send a welcome SMS to a user who just signed up using their phone number.
    """
    # Get the phone number from the user's profile(s)
    phone_profile = getattr(user, 'phone_profile', None)
    user_profile = getattr(user, 'userprofile', None)
    phone_number = None

    if phone_profile and phone_profile.phone_number:
        phone_number = phone_profile.phone_number
    elif user_profile and user_profile.phone_number:
        phone_number = user_profile.phone_number

    if not phone_number:
        SMS_AUTH_LOGGER.warning('WELCOME SMS SKIPPED: No phone number for user %s', user.id)
        return {'status': 'skipped', 'channel': 'sms', 'reason': 'No phone number'}

    if not _verify_twilio_credentials():
        SMS_AUTH_LOGGER.error('WELCOME SMS FAILED: Twilio not configured for user %s', user.id)
        return {'status': 'failed', 'channel': 'sms', 'error': 'Twilio not configured'}

    user_name = user.get_full_name() or user.first_name or user.username
    support_number = getattr(settings, 'SUPPORT_PHONE_NUMBER', '+91-XXXXX-XXXXX')

    message_text = (
        f"Welcome to GrocHub!\n\n"
        f"Hi {user_name},\n\n"
        f"Your GrocHub account has been created successfully using this mobile number.\n\n"
        f"You can now securely log in, shop for groceries, track your orders, "
        f"manage your wishlist, and enjoy fast delivery.\n\n"
        f"Thank you for choosing GrocHub!\n\n"
        f"Support: {support_number}"
    )

    try:
        client = Client(
            getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
            getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
        )
        SMS_AUTH_LOGGER.info('Sending welcome SMS to %s (user %s)', phone_number, user.id)
        twilio_message = client.messages.create(
            body=message_text,
            from_=getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
            to=phone_number,
        )
        if twilio_message.sid:
            SMS_AUTH_LOGGER.info('WELCOME SMS SENT SUCCESSFULLY | User %s | To: %s | SID: %s', user.id, phone_number, twilio_message.sid)
            return {
                'status': 'success',
                'channel': 'sms',
                'recipient': phone_number,
                'twilio_sid': twilio_message.sid,
            }
        else:
            raise RuntimeError(f'Twilio did not return a message SID (status: {twilio_message.status})')

    except TwilioRestException as exc:
        error_msg = f'Twilio error {exc.code}: {exc.msg}'
        SMS_AUTH_LOGGER.error('WELCOME SMS FAILED (Twilio error) | User %s | To: %s | Error: %s', user.id, phone_number, error_msg, exc_info=True)
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}

    except Exception as exc:
        error_msg = str(exc)
        SMS_AUTH_LOGGER.error('WELCOME SMS FAILED | User %s | To: %s | Error: %s', user.id, phone_number, error_msg, exc_info=True)
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}


def send_login_notification_sms(user, request, login_activity=None):
    """
    Send a login notification SMS to the user after a successful login.
    
    Args:
        user: User instance
        request: HttpRequest object (for User-Agent extraction)
        login_activity: Optional LoginActivity instance (if already created)
    
    Returns:
        dict with keys: status ('success'|'failed'|'skipped'), channel='sms',
                        recipient, error (if any)
    """
    # Get the phone number from the user's profile(s)
    phone_profile = getattr(user, 'phone_profile', None)
    user_profile = getattr(user, 'userprofile', None)
    phone_number = None

    if phone_profile and phone_profile.phone_number:
        phone_number = phone_profile.phone_number
    elif user_profile and user_profile.phone_number:
        phone_number = user_profile.phone_number

    if not phone_number:
        SMS_AUTH_LOGGER.warning('LOGIN SMS SKIPPED: No phone number for user %s', user.id)
        return {'status': 'skipped', 'channel': 'sms', 'reason': 'No phone number'}

    if not _verify_twilio_credentials():
        SMS_AUTH_LOGGER.error('LOGIN SMS FAILED: Twilio not configured for user %s', user.id)
        return {'status': 'failed', 'channel': 'sms', 'error': 'Twilio not configured'}

    now = timezone.localtime(timezone.now())
    user_name = user.get_full_name() or user.first_name or user.username
    login_date = now.strftime('%d %B %Y')
    login_time = now.strftime('%I:%M %p')
    ua_info = _get_user_agent_info(request)
    device_name = ua_info.get('device', 'Unknown')
    support_number = getattr(settings, 'SUPPORT_PHONE_NUMBER', '+91-XXXXX-XXXXX')

    # Build SMS message
    message_lines = [
        "GroceryHub Security Alert",
        "",
        f"Hi {user_name},",
        "",
        "Your account was successfully logged in.",
        "",
        f"Date: {login_date}",
        f"Time: {login_time}",
        f"Device: {device_name}",
        "",
        "If this wasn't you, change your password immediately.",
        "",
        f"-GroceryHub"
    ]
    
    # Add security warning if new device/browser/location
    if login_activity:
        if login_activity.is_new_device:
            message_lines.insert(4, "This login was from a new device.")
        if login_activity.is_new_browser:
            message_lines.insert(4, "This login was from a new browser.")
        if login_activity.is_new_location:
            message_lines.insert(4, "This login was from a new location.")
    
    message_text = '\n'.join(message_lines)

    try:
        client = Client(
            getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
            getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
        )
        SMS_AUTH_LOGGER.info('Sending login notification SMS to %s (user %s)', phone_number, user.id)
        twilio_message = client.messages.create(
            body=message_text,
            from_=getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
            to=phone_number,
        )
        if twilio_message.sid:
            SMS_AUTH_LOGGER.info('LOGIN SMS SENT SUCCESSFULLY | User %s | To: %s | SID: %s', user.id, phone_number, twilio_message.sid)
            
            # Update login activity if provided
            if login_activity:
                login_activity.sms_sent = True
                login_activity.save(update_fields=['sms_sent'])
            
            return {
                'status': 'success',
                'channel': 'sms',
                'recipient': phone_number,
                'twilio_sid': twilio_message.sid,
            }
        else:
            raise RuntimeError(f'Twilio did not return a message SID (status: {twilio_message.status})')

    except TwilioRestException as exc:
        error_msg = f'Twilio error {exc.code}: {exc.msg}'
        SMS_AUTH_LOGGER.error('LOGIN SMS FAILED (Twilio error) | User %s | To: %s | Error: %s', user.id, phone_number, error_msg, exc_info=True)
        
        # Update login activity if provided
        if login_activity:
            login_activity.sms_error = error_msg
            login_activity.save(update_fields=['sms_error'])
        
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}

    except Exception as exc:
        error_msg = str(exc)
        SMS_AUTH_LOGGER.error('LOGIN SMS FAILED | User %s | To: %s | Error: %s', user.id, phone_number, error_msg, exc_info=True)
        
        # Update login activity if provided
        if login_activity:
            login_activity.sms_error = error_msg
            login_activity.save(update_fields=['sms_error'])
        
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}


def send_order_confirmation_sms(order):
    """
    Send order confirmation SMS to the customer via Twilio.
    """
    customer_name, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    if not customer_phone:
        logger.warning('SMS SKIPPED: No phone number for order %s', order.id)
        log.sms_status = 'skipped'
        log.sms_error_message = 'No valid phone number'
        log.save()
        return {'status': 'skipped', 'channel': 'sms', 'reason': 'No phone number'}

    if order.total_amount is None or order.total_amount <= 0:
        logger.warning('SMS SKIPPED: Invalid total amount %s for order %s', order.total_amount, order.id)
        log.sms_status = 'skipped'
        log.sms_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'channel': 'sms', 'reason': 'Invalid total amount'}

    if not _verify_twilio_credentials():
        logger.error('SMS FAILED: Twilio not configured for order %s', order.id)
        log.sms_status = 'failed'
        log.sms_error_message = 'Twilio credentials not configured'
        log.save()
        return {'status': 'failed', 'channel': 'sms', 'error': 'Twilio not configured'}

    support_number = getattr(settings, 'SUPPORT_PHONE_NUMBER', '+91-XXXXX-XXXXX')

    message_text = (
        f"Hello {customer_name}, your order #{order.id} has been confirmed successfully. "
        f"Total Amount: ₹{order.total_amount}. "
        f"Thank you for shopping with GrocHub."
    )

    try:
        client = Client(
            getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
            getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
        )
        logger.info('Sending confirmation SMS for order %s to %s', order.id, customer_phone)
        twilio_message = client.messages.create(
            body=message_text,
            from_=getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
            to=customer_phone,
        )
        logger.info('Twilio API response for order %s: SID=%s, status=%s', order.id, twilio_message.sid, twilio_message.status)

        if twilio_message.sid:
            log.sms_status = 'sent'
            log.sms_sent_at = timezone.now()
            log.sms_error_message = ''
            log.save()
            logger.info('SMS Sent Successfully | Order #%s | To: %s | SID: %s', order.id, customer_phone, twilio_message.sid)
            return {
                'status': 'success',
                'channel': 'sms',
                'recipient': customer_phone,
                'twilio_sid': twilio_message.sid,
            }
        else:
            raise RuntimeError(f'Twilio did not return a message SID (status: {twilio_message.status})')

    except TwilioRestException as exc:
        error_msg = f'Twilio error {exc.code}: {exc.msg}'
        logger.error('SMS Failed (Twilio error) | Order #%s | To: %s | Error: %s', order.id, customer_phone, error_msg, exc_info=True)
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}

    except Exception as exc:
        error_msg = str(exc)
        logger.error('SMS Failed | Order #%s | To: %s | Error: %s', order.id, customer_phone, error_msg, exc_info=True)
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}