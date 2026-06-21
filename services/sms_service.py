import logging

from django.conf import settings
from django.utils import timezone
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from store.models import NotificationLog

logger = logging.getLogger(__name__)


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
        logger.error(
            'Twilio not fully configured. has_sid=%s, has_token=%s, has_from_number=%s',
            bool(sid), bool(token), bool(from_number),
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


def send_order_confirmation_sms(order):
    """
    Send order confirmation SMS to the customer via Twilio.

    Responsibilities:
      - Fetch registered mobile number
      - Generate SMS text
      - Send via Twilio
      - Log success/failure
      - Update NotificationLog

    Args:
        order: Order instance (with related user, shipping_address)

    Returns:
        dict with keys: status ('success'|'failed'|'skipped'), channel='sms',
                        recipient, error (if any)
    """
    customer_name, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    if not customer_phone:
        logger.warning(
            'SMS SKIPPED: No phone number for order %s (user %s)',
            order.id, order.user.id,
        )
        log.sms_status = 'skipped'
        log.sms_error_message = 'No valid phone number'
        log.save()
        return {'status': 'skipped', 'channel': 'sms', 'reason': 'No phone number'}

    if order.total_amount is None or order.total_amount <= 0:
        logger.warning(
            'SMS SKIPPED: Invalid total amount %s for order %s',
            order.total_amount, order.id,
        )
        log.sms_status = 'skipped'
        log.sms_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'channel': 'sms', 'reason': 'Invalid total amount'}

    if not _verify_twilio_credentials():
        logger.error(
            'SMS FAILED: Twilio not configured for order %s', order.id,
        )
        log.sms_status = 'failed'
        log.sms_error_message = 'Twilio credentials not configured'
        log.save()
        return {'status': 'failed', 'channel': 'sms', 'error': 'Twilio not configured'}

    support_number = getattr(settings, 'SUPPORT_PHONE_NUMBER', '+91-XXXXX-XXXXX')

    message_text = (
        f"Hello {customer_name},\n\n"
        f"Your order #{order.id} has been confirmed successfully.\n\n"
        f"Total Amount: ₹{order.total_amount}\n\n"
        f"Expected Delivery: Within 3-4 business days\n\n"
        f"Thank you for shopping with us.\n\n"
        f"Customer Support:\n"
        f"{support_number}"
    )

    try:
        client = Client(
            getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
            getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
        )
        logger.info(
            'Sending confirmation SMS for order %s to %s',
            order.id, customer_phone,
        )
        twilio_message = client.messages.create(
            body=message_text,
            from_=getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
            to=customer_phone,
        )
        logger.info(
            'Twilio API response for order %s: SID=%s, status=%s',
            order.id, twilio_message.sid, twilio_message.status,
        )

        if twilio_message.sid:
            log.sms_status = 'sent'
            log.sms_sent_at = timezone.now()
            log.sms_error_message = ''
            log.save()
            logger.info(
                '✓ SMS Sent Successfully | Order #%s | To: %s | SID: %s',
                order.id, customer_phone, twilio_message.sid,
            )
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
        logger.error(
            '✗ SMS Failed (Twilio error) | Order #%s | To: %s | Error: %s',
            order.id, customer_phone, error_msg,
            exc_info=True,
        )
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            '✗ SMS Failed | Order #%s | To: %s | Error: %s',
            order.id, customer_phone, error_msg,
            exc_info=True,
        )
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()
        return {'status': 'failed', 'channel': 'sms', 'error': error_msg}
