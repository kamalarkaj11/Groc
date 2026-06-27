"""
Super Admin Order Management Views
Only accessible by superuser/staff members.
"""
import csv
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Order, OrderItem, OrderAddress, OrderStatusHistory, OrderTracking, Notification, UserProfile, Quotation, QuotationItem

logger = logging.getLogger(__name__)


def admin_required(view_func):
    """Decorator to restrict access to superuser/staff only."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "Access denied. Admin privileges required.")
            return redirect('store:home')
        return view_func(request, *args, **kwargs)
    return wrapper


@staff_member_required
def admin_order_dashboard(request):
    """Super Admin Order Management Dashboard with statistics and all orders."""
    # Dashboard Statistics
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='pending').count()
    confirmed_orders = Order.objects.filter(status='confirmed').count()
    processing_orders = Order.objects.filter(status='processing').count()
    packed_orders = Order.objects.filter(status='packed').count()
    shipped_orders = Order.objects.filter(status='shipped').count()
    out_for_delivery_orders = Order.objects.filter(status='out_for_delivery').count()
    delivered_orders = Order.objects.filter(status='delivered').count()
    cancelled_orders = Order.objects.filter(status='cancelled').count()
    returned_orders = Order.objects.filter(status='returned').count()
    
    total_revenue = Order.objects.filter(
        payment_status='paid'
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    today = timezone.now().date()
    today_orders = Order.objects.filter(created_at__date=today).count()
    
    # Monthly revenue (current month)
    month_start = today.replace(day=1)
    monthly_revenue = Order.objects.filter(
        payment_status='paid',
        created_at__date__gte=month_start
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    # Base queryset
    orders = Order.objects.select_related(
        'user', 'shipping_address'
    ).prefetch_related(
        'items__product', 'tracking', 'status_history'
    )

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        orders = orders.filter(
            Q(order_id__icontains=search_query) |
            Q(id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(shipping_address__full_name__icontains=search_query) |
            Q(shipping_address__email__icontains=search_query) |
            Q(shipping_address__phone__icontains=search_query) |
            Q(items__product__title__icontains=search_query)
        ).distinct()

    # Filter by Order Status
    status_filter = request.GET.get('status', '').strip()
    if status_filter and status_filter in dict(Order.ORDER_STATUS_CHOICES):
        orders = orders.filter(status=status_filter)

    # Filter by Payment Status
    payment_filter = request.GET.get('payment', '').strip()
    if payment_filter and payment_filter in dict(Order.PAYMENT_STATUS_CHOICES):
        orders = orders.filter(payment_status=payment_filter)

    # Filter by Payment Method
    method_filter = request.GET.get('method', '').strip()
    if method_filter and method_filter in dict(Order.PAYMENT_METHOD_CHOICES):
        orders = orders.filter(payment_method=method_filter)

    # Date Presets
    date_preset = request.GET.get('date_preset', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if date_preset == 'today':
        orders = orders.filter(created_at__date=today)
    elif date_preset == 'yesterday':
        yesterday = today - timedelta(days=1)
        orders = orders.filter(created_at__date=yesterday)
    elif date_preset == 'last7':
        orders = orders.filter(created_at__date__gte=today - timedelta(days=7))
    elif date_preset == 'last30':
        orders = orders.filter(created_at__date__gte=today - timedelta(days=30))
    else:
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)

    # Sort
    sort_by = request.GET.get('sort', '-created_at')
    valid_sorts = {
        'latest': '-created_at',
        'oldest': 'created_at',
        'highest': '-total_amount',
        'lowest': 'total_amount',
    }
    sort_field = valid_sorts.get(sort_by, '-created_at')
    orders = orders.order_by(sort_field)

    # Pagination
    paginator = Paginator(orders, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'orders': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'search_query': search_query,
        'status_filter': status_filter,
        'payment_filter': payment_filter,
        'method_filter': method_filter,
        'date_preset': date_preset,
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        # Statistics
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'confirmed_orders': confirmed_orders,
        'processing_orders': processing_orders,
        'packed_orders': packed_orders,
        'shipped_orders': shipped_orders,
        'out_for_delivery_orders': out_for_delivery_orders,
        'delivered_orders': delivered_orders,
        'cancelled_orders': cancelled_orders,
        'returned_orders': returned_orders,
        'total_revenue': total_revenue,
        'today_orders': today_orders,
        'monthly_revenue': monthly_revenue,
        # Choices for filters
        'status_choices': Order.ORDER_STATUS_CHOICES,
        'payment_status_choices': Order.PAYMENT_STATUS_CHOICES,
        'payment_method_choices': Order.PAYMENT_METHOD_CHOICES,
        'sort_choices': [
            ('latest', 'Latest First'),
            ('oldest', 'Oldest First'),
            ('highest', 'Highest Amount'),
            ('lowest', 'Lowest Amount'),
        ],
    }
    return render(request, 'admin/orders/dashboard.html', context)


@staff_member_required
def admin_order_detail(request, order_id):
    """Super Admin Order Detail page with full information and update capabilities."""
    order = get_object_or_404(
        Order.objects.select_related('user', 'shipping_address').prefetch_related(
            'items__product', 'tracking', 'status_history__changed_by'
        ),
        id=order_id
    )
    
    items = OrderItem.objects.filter(order=order).select_related('product')
    shipping_address = getattr(order, 'shipping_address', None)
    status_history = OrderStatusHistory.objects.filter(order=order).order_by('-created_at')
    tracking, created = OrderTracking.objects.get_or_create(order=order)
    
    # Get user profile
    user_profile = getattr(order.user, 'userprofile', None)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            new_status = request.POST.get('status', '').strip()
            if new_status and new_status in dict(Order.ORDER_STATUS_CHOICES):
                old_status = order.status
                if old_status != new_status:
                    order.status = new_status
                    order.save()
                    
                    # Create status history
                    changed_by_name = request.user.get_full_name() or request.user.username
                    OrderStatusHistory.objects.create(
                        order=order,
                        previous_status=old_status,
                        new_status=new_status,
                        changed_by=request.user,
                        changed_by_name=changed_by_name,
                        notes=f"Status updated by admin from {old_status} to {new_status}",
                    )
                    
                    # Send notifications
                    _send_order_notifications(order, old_status, new_status, request)
                    
                    messages.success(request, f"Order {order.order_id} status updated to {order.get_status_display()}")
                else:
                    messages.warning(request, "Order is already in this status.")
        
        elif action == 'update_payment':
            new_payment_status = request.POST.get('payment_status', '').strip()
            new_payment_method = request.POST.get('payment_method', '').strip()
            transaction_id = request.POST.get('transaction_id', '').strip()
            
            if new_payment_status and new_payment_status in dict(Order.PAYMENT_STATUS_CHOICES):
                order.payment_status = new_payment_status
            if new_payment_method and new_payment_method in dict(Order.PAYMENT_METHOD_CHOICES):
                order.payment_method = new_payment_method
            if transaction_id:
                order.transaction_id = transaction_id
            order.save()
            messages.success(request, f"Payment details updated for Order {order.order_id}")
        
        elif action == 'update_delivery':
            address_line1 = request.POST.get('address_line1', '').strip()
            city = request.POST.get('city', '').strip()
            state = request.POST.get('state', '').strip()
            pincode = request.POST.get('pincode', '').strip()
            phone = request.POST.get('phone', '').strip()
            delivery_notes = request.POST.get('delivery_notes', '').strip()
            
            if shipping_address:
                if address_line1:
                    shipping_address.address_line1 = address_line1
                if city:
                    shipping_address.city = city
                if state:
                    shipping_address.state = state
                if pincode:
                    shipping_address.postal_code = pincode
                if phone:
                    shipping_address.phone = phone
                if delivery_notes:
                    shipping_address.delivery_instructions = delivery_notes
                shipping_address.save()
            else:
                # Create shipping address if it doesn't exist
                OrderAddress.objects.create(
                    order=order,
                    full_name=order.user.get_full_name() or order.user.username,
                    address_line1=address_line1 or order.address_line1,
                    city=city or order.city,
                    state=state or order.state,
                    postal_code=pincode or order.pincode,
                    phone=phone or order.phone,
                    delivery_instructions=delivery_notes,
                )
            
            # Also update order fields
            if address_line1:
                order.address_line1 = address_line1
            if city:
                order.city = city
            if state:
                order.state = state
            if pincode:
                order.pincode = pincode
            if phone:
                order.phone = phone
            if delivery_notes:
                order.delivery_notes = delivery_notes
            order.save()
            
            messages.success(request, f"Delivery details updated for Order {order.order_id}")
        
        return redirect('store:admin_order_detail', order_id=order.id)

    context = {
        'order': order,
        'items': items,
        'shipping_address': shipping_address,
        'status_history': status_history,
        'tracking': tracking,
        'user_profile': user_profile,
        'status_choices': Order.ORDER_STATUS_CHOICES,
        'payment_status_choices': Order.PAYMENT_STATUS_CHOICES,
        'payment_method_choices': Order.PAYMENT_METHOD_CHOICES,
    }
    return render(request, 'admin/orders/detail.html', context)


@staff_member_required
@require_POST
def admin_bulk_update_orders(request):
    """Handle bulk order status updates."""
    order_ids = request.POST.getlist('order_ids')
    new_status = request.POST.get('status', '').strip()
    
    if not order_ids or not new_status:
        messages.error(request, "Please select orders and a status.")
        return redirect('store:admin_order_dashboard')
    
    if new_status not in dict(Order.ORDER_STATUS_CHOICES):
        messages.error(request, "Invalid status selected.")
        return redirect('store:admin_order_dashboard')
    
    updated_count = 0
    for order_id in order_ids:
        try:
            order = Order.objects.get(id=order_id)
            old_status = order.status
            if old_status != new_status:
                order.status = new_status
                order.save()
                
                changed_by_name = request.user.get_full_name() or request.user.username
                OrderStatusHistory.objects.create(
                    order=order,
                    previous_status=old_status,
                    new_status=new_status,
                    changed_by=request.user,
                    changed_by_name=changed_by_name,
                    notes=f"Bulk status update from {old_status} to {new_status}",
                )
                
                _send_order_notifications(order, old_status, new_status, request)
                updated_count += 1
        except Order.DoesNotExist:
            continue
    
    messages.success(request, f"{updated_count} order(s) updated to {dict(Order.ORDER_STATUS_CHOICES).get(new_status, new_status)}")
    return redirect('store:admin_order_dashboard')


@staff_member_required
def admin_export_orders(request):
    """Export orders to CSV."""
    # Build queryset with filters (same as dashboard)
    orders = Order.objects.select_related(
        'user', 'shipping_address'
    ).prefetch_related('items__product')

    search_query = request.GET.get('q', '').strip()
    if search_query:
        orders = orders.filter(
            Q(order_id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query)
        ).distinct()

    status_filter = request.GET.get('status', '').strip()
    if status_filter and status_filter in dict(Order.ORDER_STATUS_CHOICES):
        orders = orders.filter(status=status_filter)

    payment_filter = request.GET.get('payment', '').strip()
    if payment_filter and payment_filter in dict(Order.PAYMENT_STATUS_CHOICES):
        orders = orders.filter(payment_status=payment_filter)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="orders_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Order ID', 'Order Number', 'Customer Name', 'Username', 'Email', 'Phone',
        'Order Date', 'Status', 'Payment Method', 'Payment Status', 'Transaction ID',
        'Subtotal', 'Tax', 'Discount', 'Shipping', 'Total Amount',
        'Delivery Address', 'City', 'State', 'Pincode',
        'Products'
    ])
    
    for order in orders:
        shipping = getattr(order, 'shipping_address', None)
        customer_name = shipping.full_name if shipping else (order.user.get_full_name() or order.user.username)
        customer_email = shipping.email if shipping and shipping.email else order.user.email or ''
        customer_phone = shipping.phone if shipping and shipping.phone else order.phone or ''
        
        products_list = '; '.join([
            f"{item.product.title} x{item.quantity} (Rs.{item.price})" 
            for item in order.items.all()
        ])
        
        writer.writerow([
            order.order_id or order.id,
            order.id,
            customer_name,
            order.user.username,
            customer_email,
            customer_phone,
            order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            order.get_status_display(),
            order.get_payment_method_display(),
            order.get_payment_status_display(),
            order.transaction_id or '',
            str(order.subtotal),
            str(order.tax_amount),
            str(order.discount_amount),
            str(order.shipping_charge),
            str(order.total_amount),
            shipping.address_line1 if shipping else order.address_line1,
            shipping.city if shipping else order.city,
            shipping.get_state_display() if shipping and shipping.state else order.get_state_display() if order.state else '',
            shipping.postal_code if shipping else order.pincode,
            products_list,
        ])
    
    return response


@staff_member_required
def admin_order_stats_api(request):
    """API endpoint for dashboard statistics (for AJAX refresh)."""
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    data = {
        'total_orders': Order.objects.count(),
        'pending_orders': Order.objects.filter(status='pending').count(),
        'confirmed_orders': Order.objects.filter(status='confirmed').count(),
        'processing_orders': Order.objects.filter(status='processing').count(),
        'packed_orders': Order.objects.filter(status='packed').count(),
        'shipped_orders': Order.objects.filter(status='shipped').count(),
        'out_for_delivery_orders': Order.objects.filter(status='out_for_delivery').count(),
        'delivered_orders': Order.objects.filter(status='delivered').count(),
        'cancelled_orders': Order.objects.filter(status='cancelled').count(),
        'returned_orders': Order.objects.filter(status='returned').count(),
        'total_revenue': str(Order.objects.filter(payment_status='paid').aggregate(total=Sum('total_amount'))['total'] or 0),
        'today_orders': Order.objects.filter(created_at__date=today).count(),
        'monthly_revenue': str(Order.objects.filter(payment_status='paid', created_at__date__gte=month_start).aggregate(total=Sum('total_amount'))['total'] or 0),
    }
    return JsonResponse(data)


def _send_order_notifications(order, old_status, new_status, request):
    """Send notifications when order status changes."""
    try:
        status_messages = {
            'confirmed': f'Your order {order.order_id} has been confirmed. We\'re preparing your items!',
            'processing': f'Your order {order.order_id} is now being processed.',
            'packed': f'Your order {order.order_id} has been packed and is ready for delivery.',
            'shipped': f'Your order {order.order_id} has been shipped!',
            'out_for_delivery': f'Your order {order.order_id} is out for delivery! Get ready to receive your groceries.',
            'delivered': f'Your order {order.order_id} has been delivered successfully. Enjoy your groceries! 🎉',
            'cancelled': f'Your order {order.order_id} has been cancelled. Please contact support for more information.',
            'returned': f'Your order {order.order_id} has been marked as returned.',
        }
        
        if new_status in status_messages:
            message = status_messages[new_status]
            title = f"Order {order.get_status_display()}"
            
            # Create in-app notification
            Notification.objects.create(
                user=order.user,
                title=title,
                message=message,
                notification_type='order',
            )
            
            # Try to send email notification
            try:
                from django.core.mail import send_mail
                from django.template.loader import render_to_string
                from django.utils.html import strip_tags
                
                customer_email = order.user.email
                if customer_email:
                    customer_name = order.user.get_full_name() or order.user.username
                    subject = f"GrocHub - Order {order.order_id} {order.get_status_display()}"
                    
                    html_message = render_to_string('emails/order_status_update.html', {
                        'order': order,
                        'customer_name': customer_name,
                        'old_status': dict(Order.ORDER_STATUS_CHOICES).get(old_status, old_status),
                        'new_status': dict(Order.ORDER_STATUS_CHOICES).get(new_status, new_status),
                        'message': message,
                        'track_url': f"/track-order/{order.id}/",
                    })
                    plain_message = strip_tags(html_message)
                    
                    send_mail(
                        subject,
                        plain_message,
                        'noreply@grochub.com',
                        [customer_email],
                        html_message=html_message,
                        fail_silently=True,
                    )
            except Exception as e:
                logger.warning(f"Failed to send status update email for order {order.id}: {e}")
            
            # Try to send SMS notification
            try:
                from twilio.rest import Client
                from django.conf import settings
                
                customer_phone = order.phone
                if not customer_phone:
                    shipping = getattr(order, 'shipping_address', None)
                    if shipping and shipping.phone:
                        customer_phone = shipping.phone
                
                if customer_phone and settings.TWILIO_ACCOUNT_SID:
                    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                    sms_text = f"GrocHub: Your Order #{order.order_id} has been updated to \"{order.get_status_display()}\". Track: https://grochub.com/track-order/{order.id}/"
                    client.messages.create(
                        body=sms_text,
                        from_=settings.TWILIO_PHONE_NUMBER,
                        to=customer_phone,
                    )
            except Exception as e:
                logger.warning(f"Failed to send status update SMS for order {order.id}: {e}")
                
    except Exception as e:
        logger.error(f"Error sending notifications for order {order.id}: {e}")


