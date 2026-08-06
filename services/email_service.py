import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

from store.models import Order, NotificationLog, NewsletterSubscriber, LoginActivity

import re

logger = logging.getLogger(__name__)

AUTH_EMAIL_LOGGER = logging.getLogger('store.auth_emails')


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


def send_welcome_email(user):
    """
    Send a welcome email to a newly registered user.
    """
    if not user.email:
        AUTH_EMAIL_LOGGER.warning('WELCOME EMAIL SKIPPED: No email address for user %s', user.id)
        return {'status': 'skipped', 'channel': 'email', 'reason': 'No email address'}

    if not _verify_smtp_credentials():
        AUTH_EMAIL_LOGGER.error('WELCOME EMAIL FAILED: SMTP not configured for user %s', user.id)
        return {'status': 'failed', 'channel': 'email', 'error': 'SMTP not configured'}

    user_name = user.get_full_name() or user.first_name or user.username
    created_at = timezone.localtime(user.date_joined).strftime('%d %B %Y, %I:%M %p') if user.date_joined else 'N/A'
    support_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@groceryhub.com')
    login_url = getattr(settings, 'SITE_URL', '') + '/login/'
    home_url = getattr(settings, 'SITE_URL', '') + '/'

    subject = 'Welcome to GrocHub – Your Account Has Been Created Successfully!'

    html_message = render_to_string('emails/welcome_email.html', {
        'user_name': user_name,
        'email': user.email,
        'created_at': created_at,
        'login_url': login_url,
        'home_url': home_url,
        'support_email': support_email,
    })
    plain_message = strip_tags(html_message)

    try:
        AUTH_EMAIL_LOGGER.info('Sending welcome email to %s (user %s)', user.email, user.id)
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            AUTH_EMAIL_LOGGER.info('WELCOME EMAIL SENT SUCCESSFULLY | User %s | To: %s', user.id, user.email)
            return {'status': 'success', 'channel': 'email', 'recipient': user.email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        AUTH_EMAIL_LOGGER.error('WELCOME EMAIL FAILED | User %s | To: %s | Error: %s', user.id, user.email, error_msg, exc_info=True)
        return {'status': 'failed', 'channel': 'email', 'error': error_msg}


def send_login_notification_email(user, request, login_activity=None):
    """
    Send a login notification email to the user after a successful login.
    
    Args:
        user: User instance
        request: HttpRequest object (for IP, User-Agent extraction)
        login_activity: Optional LoginActivity instance (if already created)
    
    Returns:
        dict with keys: status ('success'|'failed'|'skipped'), channel='email',
                        recipient, error (if any)
    """
    if not user.email:
        AUTH_EMAIL_LOGGER.warning('LOGIN NOTIFICATION SKIPPED: No email address for user %s', user.id)
        return {'status': 'skipped', 'channel': 'email', 'reason': 'No email address'}

    if not _verify_smtp_credentials():
        AUTH_EMAIL_LOGGER.error('LOGIN NOTIFICATION FAILED: SMTP not configured for user %s', user.id)
        return {'status': 'failed', 'channel': 'email', 'error': 'SMTP not configured'}

    now = timezone.localtime(timezone.now())
    user_name = user.get_full_name() or user.first_name or user.username
    login_date = now.strftime('%d %B %Y')
    login_time = now.strftime('%I:%M %p')
    ip_address = _get_client_ip(request)
    ua_info = _get_user_agent_info(request)

    support_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@groceryhub.com')
    change_password_url = getattr(settings, 'SITE_URL', '') + '/change-password/'
    support_email_url = f'mailto:{support_email}'

    # Determine if this is a new device/browser/location
    is_new_device = False
    is_new_browser = False
    is_new_location = False
    security_warning = ''
    
    if login_activity:
        is_new_device = login_activity.is_new_device
        is_new_browser = login_activity.is_new_browser
        is_new_location = login_activity.is_new_location
        
        if is_new_device and is_new_browser and is_new_location:
            security_warning = 'This login was detected from a new device, browser, and location that have not been used with your account before. If this was not you, please change your password immediately.'
        elif is_new_device:
            security_warning = 'This login was detected from a new device that has not been used with your account before.'
        elif is_new_browser:
            security_warning = 'This login was detected from a new browser that has not been used with your account before.'
        elif is_new_location:
            security_warning = 'This login was detected from a new location that has not been used with your account before.'

    subject = 'Security Alert: New Login to Your GrocHub Account'

    html_message = render_to_string('emails/login_notification.html', {
        'user_name': user_name,
        'login_date': login_date,
        'login_time': login_time,
        'email': user.email,
        'browser': ua_info.get('browser', 'Unknown'),
        'device': ua_info.get('device', 'Unknown'),
        'os': ua_info.get('os', 'Unknown'),
        'ip_address': ip_address,
        'change_password_url': change_password_url,
        'support_email_url': support_email_url,
        'support_email': support_email,
        'login_history_url': '',
        'security_warning': security_warning,
        'is_new_device': is_new_device,
        'is_new_browser': is_new_browser,
        'is_new_location': is_new_location,
    })
    plain_message = strip_tags(html_message)

    try:
        AUTH_EMAIL_LOGGER.info('Sending login notification to %s (user %s)', user.email, user.id)
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            AUTH_EMAIL_LOGGER.info('LOGIN NOTIFICATION SENT SUCCESSFULLY | User %s | To: %s', user.id, user.email)
            
            # Update login activity if provided
            if login_activity:
                login_activity.email_sent = True
                login_activity.save(update_fields=['email_sent'])
            
            return {'status': 'success', 'channel': 'email', 'recipient': user.email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        AUTH_EMAIL_LOGGER.error('LOGIN NOTIFICATION FAILED | User %s | To: %s | Error: %s', user.id, user.email, error_msg, exc_info=True)
        
        # Update login activity if provided
        if login_activity:
            login_activity.email_error = error_msg
            login_activity.save(update_fields=['email_error'])
        
        return {'status': 'failed', 'channel': 'email', 'error': error_msg}


def _get_customer_info(order):
    """Extract customer name, email, phone from order and related models."""
    shipping_address = getattr(order, 'shipping_address', None)

    customer_name = order.user.get_full_name() or order.user.username
    if shipping_address and shipping_address.full_name:
        customer_name = shipping_address.full_name

    customer_email = order.user.email
    if not customer_email and shipping_address and shipping_address.email:
        customer_email = shipping_address.email

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

    return customer_name, customer_email, customer_phone


def _verify_smtp_credentials():
    """Verify SMTP credentials are configured properly."""
    host = getattr(settings, 'EMAIL_HOST', None)
    port = getattr(settings, 'EMAIL_PORT', None)
    user = getattr(settings, 'EMAIL_HOST_USER', None)
    password = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    if not all([host, port, user, password, from_email]):
        logger.error('SMTP not fully configured. host=%s, port=%s, user=%s, has_password=%s, from_email=%s', host, port, user, bool(password), from_email)
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


def send_order_confirmation_email(order):
    """
    Send order confirmation email to the customer.
    """
    customer_name, customer_email, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    if not customer_email:
        logger.warning('EMAIL SKIPPED: No email address for order %s', order.id)
        log.email_status = 'skipped'
        log.email_error_message = 'No valid email address'
        log.save()
        return {'status': 'skipped', 'channel': 'email', 'reason': 'No email address'}

    if order.total_amount is None or order.total_amount <= 0:
        logger.warning('EMAIL SKIPPED: Invalid total amount %s for order %s', order.total_amount, order.id)
        log.email_status = 'skipped'
        log.email_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'channel': 'email', 'reason': 'Invalid total amount'}

    if not _verify_smtp_credentials():
        logger.error('EMAIL FAILED: SMTP not configured for order %s', order.id)
        log.email_status = 'failed'
        log.email_error_message = 'SMTP credentials not configured'
        log.save()
        return {'status': 'failed', 'channel': 'email', 'error': 'SMTP not configured'}

    shipping_address = getattr(order, 'shipping_address', None)
    order_items = list(order.items.select_related('product').all())

    expected_delivery = timezone.now() + timedelta(days=3)
    support_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'kamalarkaj11@gmail.com')
    support_phone = getattr(settings, 'SUPPORT_PHONE_NUMBER', '+91-XXXXX-XXXXX')

    payment_method = 'Card Payment (Stripe)'

    subject = 'Order Confirmed – Thank You for Shopping With Us!'
    html_message = render_to_string('emails/order_confirmation.html', {
        'order': order,
        'order_items': order_items,
        'shipping_address': shipping_address,
        'customer_name': customer_name,
        'customer_email': customer_email,
        'customer_phone': customer_phone,
        'expected_delivery': expected_delivery,
        'payment_method': payment_method,
        'support_email': support_email,
        'support_phone': support_phone,
        'support_hours': 'Mon–Sat, 9:00 AM – 8:00 PM (IST)',
    })
    plain_message = strip_tags(html_message)

    try:
        logger.info('Sending confirmation email for order %s to %s', order.id, customer_email)
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [customer_email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            log.email_status = 'sent'
            log.email_sent_at = timezone.now()
            log.email_error_message = ''
            log.save()
            logger.info('Email Sent Successfully | Order #%s | To: %s', order.id, customer_email)
            return {'status': 'success', 'channel': 'email', 'recipient': customer_email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error('Email Failed | Order #%s | To: %s | Error: %s', order.id, customer_email, error_msg, exc_info=True)
        log.email_status = 'failed'
        log.email_error_message = error_msg
        log.save()
        return {'status': 'failed', 'channel': 'email', 'error': error_msg}


def send_contact_notification(contact_message):
    """Send a notification email to the admin when a new contact form is submitted."""
    admin_email = 'kamalarkaj11@gmail.com'
    website_name = 'GrocHub'

    subject = f'New Contact Form Submission - {website_name}'
    submitted_at = contact_message.created_at.strftime('%Y-%m-%d %I:%M %p') if contact_message.created_at else 'N/A'

    html_message = render_to_string('emails/contact_notification.html', {
        'contact': contact_message,
        'submitted_at': submitted_at,
        'website_name': website_name,
        'admin_email': admin_email,
        'support_phone': getattr(settings, 'SUPPORT_PHONE_NUMBER', '+91-XXXXX-XXXXX'),
    })
    plain_message = strip_tags(html_message)

    try:
        logger.info('Sending contact notification for %s to %s', contact_message.email, admin_email)
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [admin_email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            logger.info('Contact notification sent successfully | From: %s', contact_message.email)
            return {'status': 'success', 'recipient': admin_email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error('Contact notification failed | From: %s | Error: %s', contact_message.email, error_msg, exc_info=True)
        return {'status': 'failed', 'error': error_msg}


def send_contact_confirmation(contact_message):
    """Send a confirmation email to the user who submitted the contact form."""
    website_name = 'GrocHub'
    subject = f'Thank You for Contacting {website_name}'

    html_message = render_to_string('emails/contact_confirmation.html', {
        'contact': contact_message,
        'website_name': website_name,
        'support_email': settings.DEFAULT_FROM_EMAIL,
        'support_phone': getattr(settings, 'SUPPORT_PHONE_NUMBER', '+91-XXXXX-XXXXX'),
    })
    plain_message = strip_tags(html_message)

    try:
        logger.info('Sending contact confirmation to %s', contact_message.email)
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [contact_message.email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            logger.info('Contact confirmation sent successfully to %s', contact_message.email)
            return {'status': 'success', 'recipient': contact_message.email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error('Contact confirmation failed | To: %s | Error: %s', contact_message.email, error_msg, exc_info=True)
        return {'status': 'failed', 'error': error_msg}


def send_newsletter_notification(subscriber_email, subscribed_at):
    """Send a notification email to the admin when a new user subscribes to the newsletter."""
    admin_email = settings.DEFAULT_FROM_EMAIL
    recipient_email = 'kamalarkaj11@gmail.com'
    website_name = 'GrocHub'

    subject = 'New Newsletter Subscription'
    subscription_date = subscribed_at.strftime('%Y-%m-%d %I:%M %p')

    plain_message = '\n'.join([
        'A new user has subscribed to the newsletter.',
        f'Subscriber Email: {subscriber_email}',
        f'Subscription Date: {subscription_date}',
    ])

    html_message = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #198754, #20c997); padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="color: #fff; margin: 0; font-size: 24px;">{website_name}</h1>
        </div>
        <div style="background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px; border: 1px solid #e0e0e0;">
            <p style="font-size: 16px; color: #333;">A new user has subscribed to the newsletter.</p>
            <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; background: #fff; font-weight: bold; color: #555;">Subscriber Email</td>
                    <td style="padding: 10px; border: 1px solid #ddd; background: #fff; color: #333;">{subscriber_email}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; background: #f5f5f5; font-weight: bold; color: #555;">Subscription Date</td>
                    <td style="padding: 10px; border: 1px solid #ddd; background: #f5f5f5; color: #333;">{subscription_date}</td>
                </tr>
            </table>
        </div>
        <p style="color: #999; font-size: 12px; margin-top: 20px; text-align: center;">
            This is an automated notification from {website_name}.
        </p>
    </div>
    '''

    try:
        logger.info('Sending newsletter subscription notification for %s to %s', subscriber_email, recipient_email)
        sent_count = send_mail(
            subject,
            plain_message,
            admin_email,
            [recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            logger.info('Newsletter notification sent successfully | Subscriber: %s', subscriber_email)
            return {'status': 'success'}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error('Newsletter notification failed | Subscriber: %s | Error: %s', subscriber_email, error_msg, exc_info=True)
        return {'status': 'failed', 'error': error_msg}