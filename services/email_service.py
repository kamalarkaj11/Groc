import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

from store.models import Order, NotificationLog, NewsletterSubscriber

logger = logging.getLogger(__name__)


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
        logger.error(
            'SMTP not fully configured. host=%s, port=%s, user=%s, has_password=%s, from_email=%s',
            host, port, user, bool(password), from_email,
        )
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

    Responsibilities:
      - Generate HTML email from template
      - Load customer & order details
      - Send via SMTP
      - Log success/failure
      - Update NotificationLog

    Args:
        order: Order instance (with related user, items, shipping_address)

    Returns:
        dict with keys: status ('success'|'failed'|'skipped'), channel='email',
                        recipient, error (if any)
    """
    customer_name, customer_email, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    if not customer_email:
        logger.warning(
            'EMAIL SKIPPED: No email address for order %s (user %s)',
            order.id, order.user.id,
        )
        log.email_status = 'skipped'
        log.email_error_message = 'No valid email address'
        log.save()
        return {'status': 'skipped', 'channel': 'email', 'reason': 'No email address'}

    if order.total_amount is None or order.total_amount <= 0:
        logger.warning(
            'EMAIL SKIPPED: Invalid total amount %s for order %s',
            order.total_amount, order.id,
        )
        log.email_status = 'skipped'
        log.email_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'channel': 'email', 'reason': 'Invalid total amount'}

    if not _verify_smtp_credentials():
        logger.error(
            'EMAIL FAILED: SMTP not configured for order %s', order.id,
        )
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
        logger.info(
            'Sending confirmation email for order %s to %s (SMTP: %s:%s)',
            order.id, customer_email,
            getattr(settings, 'EMAIL_HOST', 'unknown'),
            getattr(settings, 'EMAIL_PORT', 'unknown'),
        )
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [customer_email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(
            'SMTP response for order %s: sent_count=%s',
            order.id, sent_count,
        )
        if sent_count == 1:
            log.email_status = 'sent'
            log.email_sent_at = timezone.now()
            log.email_error_message = ''
            log.save()
            logger.info(
                'Email Sent Successfully | Order #%s | To: %s',
                order.id, customer_email,
            )
            return {'status': 'success', 'channel': 'email', 'recipient': customer_email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            'Email Failed | Order #%s | To: %s | Error: %s',
            order.id, customer_email, error_msg,
            exc_info=True,
        )
        log.email_status = 'failed'
        log.email_error_message = error_msg
        log.save()
        return {'status': 'failed', 'channel': 'email', 'error': error_msg}


def send_contact_notification(contact_message):
    """
    Send a notification email to the admin when a new contact form is submitted.

    Args:
        contact_message: ContactMessage instance

    Returns:
        dict with keys: status ('success'|'failed'), error (if any)
    """
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
        logger.info(
            'Sending contact notification for %s to %s',
            contact_message.email, admin_email,
        )
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [admin_email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            logger.info(
                'Contact notification sent successfully | From: %s',
                contact_message.email,
            )
            return {'status': 'success', 'recipient': admin_email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            'Contact notification failed | From: %s | Error: %s',
            contact_message.email, error_msg,
            exc_info=True,
        )
        return {'status': 'failed', 'error': error_msg}


def send_contact_confirmation(contact_message):
    """
    Send a confirmation email to the user who submitted the contact form.

    Args:
        contact_message: ContactMessage instance

    Returns:
        dict with keys: status ('success'|'failed'), error (if any)
    """
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
        logger.info(
            'Sending contact confirmation to %s',
            contact_message.email,
        )
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [contact_message.email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            logger.info(
                'Contact confirmation sent successfully to %s',
                contact_message.email,
            )
            return {'status': 'success', 'recipient': contact_message.email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            'Contact confirmation failed | To: %s | Error: %s',
            contact_message.email, error_msg,
            exc_info=True,
        )
        return {'status': 'failed', 'error': error_msg}


def send_newsletter_notification(subscriber_email, subscribed_at):
    """
    Send a notification email to the admin when a new user subscribes to the newsletter.

    Args:
        subscriber_email (str): The email address that subscribed.
        subscribed_at (datetime): The timestamp of subscription.

    Returns:
        dict with keys: status ('success'|'failed'), error (if any)
    """
    admin_email = settings.DEFAULT_FROM_EMAIL
    recipient_email = 'kamalarkaj11@gmail.com'
    website_name = 'GrocHub'

    subject = 'New Newsletter Subscription'

    subscription_date = subscribed_at.strftime('%Y-%m-%d %I:%M %p')

    # Build email body
    body_parts = [
        'A new user has subscribed to the newsletter.\n',
        f'Subscriber Email: {subscriber_email}',
        f'Subscription Date: {subscription_date}',
    ]
    plain_message = '\n'.join(body_parts)

    # HTML version
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
        logger.info(
            'Sending newsletter subscription notification for %s to %s',
            subscriber_email, recipient_email,
        )
        sent_count = send_mail(
            subject,
            plain_message,
            admin_email,
            [recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            logger.info(
                'Newsletter notification sent successfully | Subscriber: %s',
                subscriber_email,
            )
            return {'status': 'success'}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            'Newsletter notification failed | Subscriber: %s | Error: %s',
            subscriber_email, error_msg,
            exc_info=True,
        )
        return {'status': 'failed', 'error': error_msg}
