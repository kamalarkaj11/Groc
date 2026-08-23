"""
Invoice utility functions for GrocHub.
Handles PDF generation using ReportLab (pure Python, no system deps).
"""

import logging
import io
from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)


def generate_invoice_pdf(order, request=None):
    """
    Generate a PDF invoice for the given order using ReportLab.
    Returns the PDF bytes.

    This is a pure-Python implementation with no system library dependencies.
    Works on Windows, macOS, and Linux without GTK, wkhtmltopdf, or any
    external binary.
    """
    try:
        invoice_data = get_invoice_context(order, request)
        return _build_pdf(invoice_data)
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
    try:
        if request and hasattr(request, 'build_absolute_uri'):
            logo_url = request.build_absolute_uri(settings.STATIC_URL + 'images/grochub-logo.png')
    except Exception:
        pass
    
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


# ============================================================
# ReportLab PDF Builder
# ============================================================

# --- Colours ---
GREEN_DARK = colors.HexColor('#0a3d2e')
GREEN_MID = colors.HexColor('#1a6b4a')
GREEN_ACCENT = colors.HexColor('#27ae60')
YELLOW_ACCENT = colors.HexColor('#ffc857')
CHARCOAL = colors.HexColor('#1a1a2e')
GREY_MUTED = colors.HexColor('#888888')
GREY_LIGHT = colors.HexColor('#f0f2f5')
GREY_BORDER = colors.HexColor('#e8eaed')
WHITE = colors.white
BLACK = colors.black

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

# --- Styles ---
_styles = getSampleStyleSheet()

style_h1 = ParagraphStyle('InvH1', parent=_styles['Heading1'],
    fontSize=22, leading=26, textColor=WHITE, spaceAfter=0, spaceBefore=0,
    fontName='Helvetica-Bold')
style_h2 = ParagraphStyle('InvH2', parent=_styles['Heading2'],
    fontSize=14, leading=17, textColor=GREEN_DARK, spaceAfter=6,
    fontName='Helvetica-Bold')
style_h3 = ParagraphStyle('InvH3', parent=_styles['Heading3'],
    fontSize=9, leading=11, textColor=WHITE, spaceAfter=2,
    fontName='Helvetica-Bold')
style_body = ParagraphStyle('InvBody', parent=_styles['Normal'],
    fontSize=9, leading=12, textColor=CHARCOAL, spaceAfter=0, spaceBefore=0,
    fontName='Helvetica')
style_body_small = ParagraphStyle('InvBodySmall', parent=style_body,
    fontSize=8, leading=10, textColor=GREY_MUTED)
style_label = ParagraphStyle('InvLabel', parent=style_body,
    fontSize=7, leading=9, textColor=GREY_MUTED, fontName='Helvetica-Bold')
style_table_header = ParagraphStyle('InvTH', fontName='Helvetica-Bold',
    fontSize=8, leading=10, textColor=CHARCOAL)
style_table_cell = ParagraphStyle('InvTC', fontName='Helvetica',
    fontSize=8, leading=10, textColor=CHARCOAL)
style_total = ParagraphStyle('InvTotal', fontName='Helvetica-Bold',
    fontSize=14, leading=17, textColor=GREEN_DARK)
style_footer_text = ParagraphStyle('InvFooter', fontName='Helvetica',
    fontSize=8, leading=10, textColor=colors.HexColor('#777'))
style_thankyou = ParagraphStyle('InvTY', fontName='Helvetica-Bold',
    fontSize=12, leading=15, textColor=GREEN_DARK)
style_watermark = ParagraphStyle('InvWM', fontName='Helvetica-Bold',
    fontSize=72, leading=86, textColor=colors.HexColor('#0a3d2e'),
    alignment=TA_CENTER)


def _table_cell(text, style=style_table_cell):
    return Paragraph(str(text or ''), style)


def _build_pdf(ctx):
    """Build and return PDF bytes from the invoice context."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Invoice {ctx['invoice_number']}",
        author=ctx['company']['name'],
    )
    
    story = []
    
    # ── Header ──
    header_data = [
        [Paragraph(f"<b>{ctx['company']['name']}</b>", style_h1),
         Paragraph('TAX INVOICE', ParagraphStyle('InvTitleRight',
             parent=style_h1, fontSize=18, leading=22, alignment=TA_RIGHT))],
        [Paragraph(ctx['company']['tagline'], ParagraphStyle('InvTagline',
             parent=style_body, fontSize=8, textColor=colors.HexColor('#ccc'))),
         Paragraph(f"<b>{ctx['invoice_number']}</b>", ParagraphStyle('InvNumRight',
             parent=style_body, fontSize=9, textColor=colors.HexColor('#ddd'), alignment=TA_RIGHT))],
    ]
    header_col_w = [CONTENT_W * 0.55, CONTENT_W * 0.45]
    t = Table(header_data, colWidths=header_col_w)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GREEN_DARK),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('TOPPADDING', (0, 0), (-1, -1), 13),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 13),
        ('ROWBACKGROUNDS', (0, 1), (-1, 1), [GREEN_MID]),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    
    # ── Info Row ──
    from_address = ctx['company']['address'].replace('\n', '<br/>')
    info_data = [
        [Paragraph('<b>From</b>', style_label),
         Paragraph('<b>Invoice Date</b>', style_label),
         Paragraph('<b>Order ID</b>', style_label)],
        [Paragraph(f"<b>{ctx['company']['name']}</b>", style_body),
         Paragraph(ctx['invoice_date'], style_body),
         Paragraph(ctx['order'].order_id or str(ctx['order'].id), style_body)],
        [Paragraph(from_address, style_body_small),
         Paragraph(f"Order Date: {ctx['order_date']}", style_body_small),
         Paragraph(f"GSTIN: {ctx['company']['gst']}", style_body_small)],
    ]
    t = Table(info_data, colWidths=[CONTENT_W * 0.4, CONTENT_W * 0.3, CONTENT_W * 0.3])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 2), (-1, 2), 0.5, GREY_BORDER),
        ('LINEBELOW', (1, 2), (1, 2), 0.5, GREY_BORDER),
        ('LINEBELOW', (2, 2), (2, 2), 0.5, GREY_BORDER),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))
    
    # ── Bill To / Order Summary ──
    delivery = ctx['delivery_address'].replace('\n', '<br/>') if ctx['delivery_address'] else 'Address not available'
    summary_text = (
        f"<b>Order Status:</b> {ctx['order_status_display']}<br/>"
        f"<b>Payment:</b> {ctx['payment_status_display']}<br/>"
        f"<b>Items:</b> {len(ctx['items'])} product{'s' if len(ctx['items']) != 1 else ''}<br/>"
        f"<b>Order Total:</b> ₹{ctx['grand_total']:.2f}"
    )
    addr_data = [
        [Paragraph('<b>Bill To</b>', style_label),
         Paragraph('<b>Order Summary</b>', style_label)],
        [Paragraph(f"<b>{ctx['customer_name']}</b>", style_body),
         Paragraph(summary_text, style_body_small)],
        [Paragraph(delivery, style_body_small), ''],
    ]
    contact_parts = []
    if ctx['customer_email']:
        contact_parts.append(f"✉ {ctx['customer_email']}")
    if ctx['customer_phone']:
        contact_parts.append(f"📞 {ctx['customer_phone']}")
    if contact_parts:
        contact_line = '&nbsp;&nbsp;'.join(contact_parts)
        addr_data.append([Paragraph(contact_line, style_body_small), ''])
    
    addr_col_w = [CONTENT_W * 0.5, CONTENT_W * 0.5]
    t = Table(addr_data, colWidths=addr_col_w)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, -1), (-1, -1), 1, GREY_LIGHT),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))
    
    # ── Items Table ──
    item_header = ['#', 'Product', 'Qty', 'Price', 'Total']
    col_w = [16, CONTENT_W - 16 - 60 - 70 - 70, 60, 70, 70]
    
    item_rows = [item_header]
    for i, item in enumerate(ctx['items'], 1):
        # Prefer the immutable snapshot name; fall back to the live product.
        product_name = item.product_name or (item.product.title if item.product else 'Product')
        weight = item.product.weight if item.product and item.product.weight else ''
        meta_parts = []
        if weight:
            meta_parts.append(f"Weight: {weight}")
        meta_str = f"<br/><font size=7 color='#999'>{' | '.join(meta_parts)}</font>" if meta_parts else ''
        
        item_rows.append([
            str(i),
            f"{product_name}{meta_str}",
            str(item.quantity),
            f"₹{item.price:.2f}",
            f"₹{item.total_price():.2f}",
        ])
    
    t = Table(item_rows, colWidths=col_w, repeatRows=1)
    table_style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), GREEN_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (4, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, GREY_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, GREY_LIGHT]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    t.setStyle(TableStyle(table_style_cmds))
    story.append(t)
    story.append(Spacer(1, 12))
    
    # ── Summary ──
    summary_rows = []
    summary_rows.append([Paragraph('Subtotal', style_body), Paragraph(f"₹{ctx['subtotal']:.2f}", style_body)])
    if ctx['discount'] > 0:
        summary_rows.append([Paragraph('Discount', style_body),
                             Paragraph(f"-₹{ctx['discount']:.2f}", ParagraphStyle('Disc', parent=style_body, textColor=colors.HexColor('#e74c3c')))])
    if ctx['shipping'] > 0:
        summary_rows.append([Paragraph('Delivery Charges', style_body), Paragraph(f"₹{ctx['shipping']:.2f}", style_body)])
    else:
        summary_rows.append([Paragraph('Delivery Charges', style_body),
                             Paragraph('FREE', ParagraphStyle('Free', parent=style_body, textColor=GREEN_ACCENT))])
    if ctx['tax'] > 0:
        summary_rows.append([Paragraph('Tax / GST', style_body), Paragraph(f"₹{ctx['tax']:.2f}", style_body)])
    summary_rows.append(['', ''])
    summary_rows.append([Paragraph('<b>Grand Total</b>', style_total), Paragraph(f"<b>₹{ctx['grand_total']:.2f}</b>", style_total)])
    
    summary_col_w = [CONTENT_W - 140, 140]
    t = Table(summary_rows, colWidths=summary_col_w)
    t.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 2, GREEN_DARK),
        ('LINEBELOW', (0, -2), (-1, -2), 0.5, GREY_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))
    
    # ── Payment Details ──
    pay_rows = [
        [Paragraph('<b>Payment Information</b>', style_label),
         Paragraph('<b>Transaction ID</b>', style_label),
         Paragraph('<b>Payment Date</b>', style_label),
         Paragraph('<b>Payment Status</b>', style_label)],
        [Paragraph(ctx['payment_method_display'], style_body),
         Paragraph(ctx.get('transaction_id', 'N/A'), style_body),
         Paragraph(ctx['payment_date'], style_body),
         Paragraph(ctx['payment_status_display'], style_body)],
    ]
    pay_col_w = [CONTENT_W * 0.25, CONTENT_W * 0.25, CONTENT_W * 0.25, CONTENT_W * 0.25]
    t = Table(pay_rows, colWidths=pay_col_w)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GREY_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, 1), [WHITE]),
    ]))
    story.append(t)
    story.append(Spacer(1, 24))
    
    # ── Footer ──
    footer_rows = [
        [Paragraph('<b>Customer Support</b>', style_label),
         Paragraph('<b>Terms &amp; Conditions</b>', style_label),
         Paragraph('<b>Return &amp; Refund Policy</b>', style_label)],
        [Paragraph(
            f"<b>Email:</b> {ctx['company']['email']}<br/>"
            f"<b>Phone:</b> {ctx['company']['phone']}<br/>"
            f"<b>Web:</b> {ctx['company']['website']}",
            style_footer_text),
         Paragraph(
            "• Goods once sold will not be taken back or exchanged.<br/>"
            "• Subject to Bangalore jurisdiction.<br/>"
            "• Delivery timelines are estimates only.<br/>"
            "• This is a computer-generated invoice.",
            style_footer_text),
         Paragraph(
            "• Damaged/expired items can be replaced within 24 hours.<br/>"
            "• Refunds processed within 5-7 business days.<br/>"
            "• Contact support for any issues.",
            style_footer_text)],
    ]
    footer_col_w = [CONTENT_W * 0.33, CONTENT_W * 0.33, CONTENT_W * 0.34]
    t = Table(footer_rows, colWidths=footer_col_w)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    
    # ── Thank You + Signature ──
    story.append(Spacer(1, 8))
    thanks_rows = [
        [Paragraph(f"<b>Thank you for shopping with {ctx['company']['name']}!</b>", style_thankyou),
         Paragraph('<br/>', style_body)],
    ]
    thanks_col_w = [CONTENT_W - 120, 120]
    t = Table(thanks_rows, colWidths=thanks_col_w)
    t.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 1, GREY_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    
    # Build PDF
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes