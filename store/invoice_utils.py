"""
Invoice utility functions for GrocHub.
Handles PDF generation using WeasyPrint.
"""

import logging
import os
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def generate_invoice_pdf(order, request=None):
    """
    Generate a PDF invoice for the given order using WeasyPrint.
    Returns the PDF bytes.
    """
    from weasyprint import HTML
    
    try:
        # Get all required data
        invoice_data = get_invoice_context(order, request)
        
        # Render the HTML template
        html_string = render_to_string('invoices/invoice_template.html', invoice_data)
        
        # Generate PDF
        pdf_bytes = HTML(string=html_string).write_pdf()
        
        logger.info(f"Invoice PDF generated successfully for order {order.order_id}")
        return pdf_bytes
    
    except Exception as e:
        logger.error(f"Failed to generate invoice PDF for order {order.order_id}: {str(e)}")
        raise


def generate_invoice_html(order, request=None):
    """
    Generate the HTML version of the invoice for browser viewing.
    Returns HTML string.
    """
    invoice_data = get_invoice_context(order, request)
    html_string = render_to_string('invoices/invoice_template.html', invoice_data)
    return html_string


def get_invoice_context(order, request=None):
    """
    Build the full context dictionary for the invoice template.
    """
    from .models import OrderItem, OrderAddress
    
    # Get order items
    items = OrderItem.objects.filter(order=order).select_related('product')
    
    # Get shipping address
    shipping_address = getattr(order, 'shipping_address', None)
    
    # Build customer info
    customer_name = order.user.get_full_name() or order.user.username
    customer_email = order.user.email or ''
    customer_phone = ''
    
    if shipping_address:
        if shipping_address.full_name:
            customer_name = shipping_address.full_name
        if shipping_address.email:
            customer_email = shipping_address.email
        if shipping_address.phone:
            customer_phone = shipping_address.phone
    
    # Get user profile phone as fallback
    if not customer_phone:
        profile = getattr(order.user, 'userprofile', None)
        if profile and profile.phone_number:
            customer_phone = profile.phone_number
    
    # Build delivery address string
    delivery_address = ''
    if shipping_address:
        address_parts = []
        if shipping_address.full_name:
            address_parts.append(shipping_address.full_name)
        if shipping_address.address_line1:
            address_parts.append(shipping_address.address_line1)
        if shipping_address.address_line2:
            address_parts.append(shipping_address.address_line2)
        city_line = []
        if shipping_address.city:
            city_line.append(shipping_address.city)
        if shipping_address.state:
            city_line.append(shipping_address.get_state_display())
        if city_line:
            address_parts.append(', '.join(city_line))
        if shipping_address.postal_code:
            address_parts.append(shipping_address.postal_code)
        if shipping_address.country:
            address_parts.append(shipping_address.country)
        delivery_address = '\n'.join(address_parts)
    elif order.address:
        delivery_address = order.address
        if order.city:
            delivery_address += f'\n{order.city}'
        if order.state:
            delivery_address += f'\n{order.get_state_display()}'
        if order.pincode:
            delivery_address += f'\n{order.pincode}'
    
    # Subtotal from order items
    subtotal = sum(item.total_price() for item in items)
    
    # Calculate values
    subtotal = order.subtotal or subtotal
    discount = order.discount_amount or Decimal('0.00')
    shipping = order.shipping_charge or Decimal('0.00')
    tax = order.tax_amount or Decimal('0.00')
    grand_total = order.total_amount or (subtotal - discount + shipping + tax)
    
    # Invoice number
    invoice_number = f"INV-{order.order_id}-{order.id}"
    
    # Company info
    company_info = {
        'name': 'GrocHub',
        'tagline': 'Fresh Groceries, Delivered Fast',
        'address': '123, Green Avenue, Sector 12\nMG Road\nBangalore, Karnataka 560001\nIndia',
        'email': 'support@grochub.in',
        'phone': '+91-1800-123-4567',
        'gst': '29ABCDE1234F1Z5',
        'website': 'www.grochub.in',
    }
    
    # Get logo URL
    logo_url = None
    if request:
        logo_url = request.build_absolute_uri(settings.STATIC_URL + 'images/grochub-logo.png')
    
    # Payment details
    payment_method_display = dict(order.PAYMENT_METHOD_CHOICES).get(order.payment_method, order.payment_method)
    
    context = {
        'order': order,
        'items': items,
        'shipping_address': shipping_address,
        'delivery_address': delivery_address,
        'customer_name': customer_name,
        'customer_email': customer_email,
        'customer_phone': customer_phone,
        'invoice_number': invoice_number,
        'invoice_date': timezone.now().strftime('%d %B %Y'),
        'order_date': order.created_at.strftime('%d %B %Y'),
        'subtotal': subtotal,
        'discount': discount,
        'shipping': shipping,
        'tax': tax,
        'grand_total': grand_total,
        'company': company_info,
        'logo_url': logo_url,
        'payment_method_display': payment_method_display,
        'transaction_id': order.transaction_id or 'N/A',
        'payment_date': order.created_at.strftime('%d %B %Y %I:%M %p'),
        'payment_status_display': order.get_payment_status_display(),
        'order_status_display': order.get_status_display(),
        'is_pdf': False,
        'today': timezone.now(),
    }
    
    return context