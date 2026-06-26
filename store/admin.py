from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from .models import (
    Profile, PhoneOTP, Review, UserProfile, Category,
    Subcategory, SubSubCategory, Product, CartItem, Order, OrderItem, OrderAddress, OTP,
    NotificationLog, NewsletterSubscriber, OrderTracking, OrderTrackingHistory, Notification,
    ContactMessage, OrderStatusHistory, Quotation, QuotationItem
)


# ---------- Category Admin ----------

class SubcategoryInline(admin.TabularInline):
    """Show subcategories inline within Category admin."""
    model = Subcategory
    extra = 1
    prepopulated_fields = {'slug': ('name',)}
    fields = ('name', 'slug', 'image', 'icon', 'description', 'is_active', 'sort_order')
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'image_preview', 'product_count']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']
    inlines = [SubcategoryInline]

    def image_preview(self, obj):
        """Show a small thumbnail of the category image."""
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:6px;" />', obj.image.url)
        return '-'
    image_preview.short_description = 'Image'

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'


# ---------- Subcategory Admin ----------

class SubSubCategoryInline(admin.TabularInline):
    """Show sub-subcategories inline within Subcategory admin."""
    model = SubSubCategory
    extra = 1
    prepopulated_fields = {'slug': ('name',)}
    fields = ('name', 'slug', 'image', 'icon', 'description', 'is_active', 'sort_order')
    show_change_link = True


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'slug', 'image_preview', 'product_count', 'is_active', 'sort_order']
    list_filter = ['category', 'is_active']
    list_select_related = ['category']
    list_editable = ['is_active', 'sort_order']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'category__name', 'description']
    autocomplete_fields = ['category']
    inlines = [SubSubCategoryInline]

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:6px;" />', obj.image.url)
        return '-'
    image_preview.short_description = 'Image'

    def product_count(self, obj):
        return obj.products.filter(is_out_of_stock=False).count()
    product_count.short_description = 'Products'


# ---------- Sub-Subcategory Admin ----------

@admin.register(SubSubCategory)
class SubSubCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'subcategory', 'slug', 'image_preview', 'product_count', 'is_active', 'sort_order']
    list_filter = ['subcategory__category', 'subcategory', 'is_active']
    list_select_related = ['subcategory__category']
    list_editable = ['is_active', 'sort_order']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'subcategory__name', 'subcategory__category__name', 'description']
    autocomplete_fields = ['subcategory']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:6px;" />', obj.image.url)
        return '-'
    image_preview.short_description = 'Image'

    def product_count(self, obj):
        return obj.products.filter(is_out_of_stock=False).count()
    product_count.short_description = 'Products'


# ---------- Product Admin ----------

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'subcategory', 'subsubcategory', 'price', 'discount_price', 'discount_percentage', 'api_source', 'is_out_of_stock', 'image_preview']
    list_filter = ['category', 'subcategory', 'subsubcategory', 'api_source', 'is_out_of_stock']
    list_select_related = ['category', 'subcategory']
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ['title', 'description', 'api_product_id']
    autocomplete_fields = ['category', 'subcategory', 'subsubcategory']
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'description', 'category', 'subcategory', 'subsubcategory')
        }),
        ('Pricing', {
            'fields': ('price', 'discount_price'),
        }),
        ('Media', {
            'fields': ('image', 'external_image_url', 'product_video', 'external_video_url', 'video_preview'),
            'description': 'Upload product images and videos. The video will display in a full-width 16:9 player on the product detail page.',
        }),
        ('Details', {
            'fields': ('weight', 'origin', 'expiry_date', 'nutrition_info', 'highlights'),
        }),
        ('Inventory', {
            'fields': ('is_out_of_stock', 'availability'),
        }),
        ('API Data', {
            'fields': ('api_source', 'api_product_id', 'api_rating', 'api_review_count', 'api_payload'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ['discount_percentage', 'video_preview']

    def video_preview(self, obj):
        if obj.product_video:
            return format_html(
                '<video width="320" controls style="border-radius:8px;max-width:100%;">'
                '<source src="{}" type="video/mp4">Your browser does not support the video tag.</video>',
                obj.product_video.url
            )
        if obj.external_video_url:
            url = obj.external_video_url
            if 'youtube.com' in url or 'youtu.be' in url:
                embed_url = url.replace('watch?v=', 'embed/') if 'watch?v=' in url else url
                return format_html(
                    '<iframe width="320" height="180" src="{}" frameborder="0" '
                    'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
                    'gyroscope; picture-in-picture" allowfullscreen style="border-radius:8px;max-width:100%;"></iframe>',
                    embed_url
                )
            return format_html('<a href="{}" target="_blank">Open external video URL</a>', url)
        return '-'
    video_preview.short_description = 'Video Preview'

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="60" height="60" style="object-fit:cover;border-radius:6px;" />', obj.image.url)
        if obj.external_image_url:
            return format_html('<img src="{}" width="60" height="60" style="object-fit:cover;border-radius:6px;" />', obj.external_image_url)
        return '-'
    image_preview.short_description = 'Image'

    def get_form(self, request, obj=None, **kwargs):
        """Limit subcategory and subsubcategory choices based on selected category."""
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.category:
            form.base_fields['subcategory'].queryset = Subcategory.objects.filter(
                category=obj.category
            )
        if obj and obj.subcategory:
            from .models import SubSubCategory
            form.base_fields['subsubcategory'].queryset = SubSubCategory.objects.filter(
                subcategory=obj.subcategory
            )
        return form

    class Media:
        """Custom JavaScript to dynamically filter subcategory dropdown
        when category changes in the Product admin form."""
        js = ('admin/product_subcategory.js',)


# ---------- Other Admin Registrations ----------

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'full_name_display', 'user_email', 'phone_number', 'state',
        'account_status', 'order_count', 'created_at', 'updated_at',
    ]
    list_filter = ['state', 'account_status', 'created_at']
    search_fields = [
        'user__username', 'user__first_name', 'user__last_name',
        'user__email', 'phone_number', 'address',
    ]
    readonly_fields = ['created_at', 'updated_at']
    list_select_related = ['user']

    def full_name_display(self, obj):
        return obj.user.get_full_name() or obj.user.username
    full_name_display.short_description = 'Full Name'
    full_name_display.admin_order_field = 'user__first_name'

    def user_email(self, obj):
        return obj.user.email or '-'
    user_email.short_description = 'Email'
    user_email.admin_order_field = 'user__email'

    def order_count(self, obj):
        return Order.objects.filter(user=obj.user).count()
    order_count.short_description = 'Orders'


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    list_select_related = ['product', 'user']


admin.site.register(CartItem)
admin.site.register(OTP)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'phone_number', 'is_email_verified', 'is_phone_verified',
        'verification_method', 'verified_at', 'profile_verified_at', 'created_at',
    ]
    list_filter = ['verification_method', 'is_email_verified', 'is_phone_verified']
    search_fields = ['user__username', 'user__email', 'phone_number']
    readonly_fields = ['created_at']


admin.site.register(PhoneOTP)
admin.site.register(NewsletterSubscriber)


# ---------- Order Status History Inline ----------

class OrderStatusHistoryInline(admin.TabularInline):
    """Inline display of order status history."""
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ['previous_status', 'new_status', 'changed_by_name', 'notes', 'created_at']
    fields = ['previous_status', 'new_status', 'changed_by_name', 'notes', 'created_at']
    ordering = ['-created_at']
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------- Order Admin ----------

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'quantity', 'price', 'total_price']
    fields = ['product', 'quantity', 'price', 'total_price']

    def total_price(self, obj):
        return f"Rs. {obj.total_price()}"
    total_price.short_description = 'Total'

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class OrderAddressInline(admin.StackedInline):
    model = OrderAddress
    extra = 0
    readonly_fields = [
        'full_name', 'email', 'phone', 'address_line1', 'address_line2',
        'city', 'state', 'postal_code', 'country', 'delivery_instructions',
        'latitude', 'longitude', 'created_at',
    ]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class NotificationLogInline(admin.TabularInline):
    """Inline show of notification logs for an order."""
    model = NotificationLog
    extra = 0
    readonly_fields = [
        'user', 'email_status', 'sms_status', 'email_sent_at', 'sms_sent_at',
        'email_error_message', 'sms_error_message', 'created_at',
    ]
    fields = [
        'email_status', 'sms_status', 'email_sent_at', 'sms_sent_at',
        'email_error_message', 'sms_error_message',
    ]
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_id_display', 'customer_name', 'customer_email', 'customer_phone',
        'payment_method_display', 'payment_status_badge', 'total_amount',
        'status_badge', 'notification_status_badge', 'delivery_city', 'created_at',
    ]
    list_filter = ['status', 'payment_status', 'payment_method', 'created_at', 'state']
    list_select_related = ['user']
    search_fields = [
        'order_id', 'user__username', 'user__first_name', 'user__last_name',
        'user__email', 'phone', 'address',
        'shipping_address__full_name', 'shipping_address__email',
        'shipping_address__phone',
    ]
    readonly_fields = [
        'user', 'stripe_session_id', 'total_amount', 'subtotal', 'tax_amount',
        'discount_amount', 'shipping_charge', 'created_at', 'updated_at',
        'order_id_display', 'customer_name_display', 'customer_email_display',
        'customer_phone_display', 'delivery_address_display', 'notification_details',
    ]
    date_hierarchy = 'created_at'
    inlines = [OrderAddressInline, OrderItemInline, OrderStatusHistoryInline, NotificationLogInline]
    
    actions = ['mark_as_confirmed', 'mark_as_packed', 'mark_as_out_for_delivery', 'mark_as_delivered', 'mark_as_cancelled']

    fieldsets = (
        ('Order Info', {
            'fields': ('order_id_display', 'user', 'status', 'created_at', 'updated_at'),
        }),
        ('Payment Info', {
            'fields': ('payment_method', 'payment_status', 'transaction_id', 'stripe_session_id',
                       'subtotal', 'tax_amount', 'discount_amount', 'shipping_charge', 'total_amount'),
        }),
        ('Customer Details', {
            'fields': ('customer_name_display', 'customer_email_display', 'customer_phone_display'),
        }),
        ('Delivery Info', {
            'fields': ('address', 'address_line1', 'city', 'state', 'pincode', 'phone',
                       'delivery_notes', 'expected_delivery_date', 'delivery_address_display'),
        }),
        ('Notification Status', {
            'fields': ('notification_details',),
            'classes': ('collapse',),
        }),
    )

    def order_id_display(self, obj):
        return obj.order_id or f"#{obj.id}"
    order_id_display.short_description = 'Order ID'
    order_id_display.admin_order_field = 'order_id'

    def customer_name(self, obj):
        shipping = getattr(obj, 'shipping_address', None)
        if shipping:
            return shipping.full_name
        return obj.user.get_full_name() or obj.user.username
    customer_name.short_description = 'Customer'
    customer_name.admin_order_field = 'user__first_name'

    def customer_email(self, obj):
        shipping = getattr(obj, 'shipping_address', None)
        if shipping and shipping.email:
            return shipping.email
        return obj.user.email or '-'
    customer_email.short_description = 'Email'

    def customer_phone(self, obj):
        shipping = getattr(obj, 'shipping_address', None)
        if shipping and shipping.phone:
            return shipping.phone
        return obj.phone or '-'
    customer_phone.short_description = 'Phone'

    def payment_method_display(self, obj):
        return obj.get_payment_method_display() if obj.payment_method else '-'
    payment_method_display.short_description = 'Payment'

    def payment_status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'paid': '#10b981',
            'failed': '#ef4444',
            'refunded': '#6366f1',
        }
        color = colors.get(obj.payment_status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_payment_status_display().upper(),
        )
    payment_status_badge.short_description = 'Payment Status'

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'confirmed': '#3b82f6',
            'packed': '#6366f1',
            'out_for_delivery': '#06b6d4',
            'delivered': '#10b981',
            'cancelled': '#ef4444',
            'failed': '#dc2626',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display().upper(),
        )
    status_badge.short_description = 'Status'

    def delivery_city(self, obj):
        return obj.city or '-'
    delivery_city.short_description = 'City'

    def customer_name_display(self, obj):
        shipping = getattr(obj, 'shipping_address', None)
        name = shipping.full_name if shipping else (obj.user.get_full_name() or obj.user.username)
        return name
    customer_name_display.short_description = 'Full Name'

    def customer_email_display(self, obj):
        shipping = getattr(obj, 'shipping_address', None)
        email = (shipping.email if shipping and shipping.email else '') or obj.user.email or '-'
        return email
    customer_email_display.short_description = 'Email'

    def customer_phone_display(self, obj):
        shipping = getattr(obj, 'shipping_address', None)
        phone = (shipping.phone if shipping and shipping.phone else '') or obj.phone or '-'
        return phone
    customer_phone_display.short_description = 'Phone'

    def delivery_address_display(self, obj):
        shipping = getattr(obj, 'shipping_address', None)
        if shipping:
            return shipping.formatted
        return obj.address or 'No address on file'
    delivery_address_display.short_description = 'Full Delivery Address'

    def notification_details(self, obj):
        """Show notification delivery status details."""
        log = NotificationLog.objects.filter(order=obj).first()
        if not log:
            return format_html(
                '<span style="color: #6c757d;">No notification log available. '
                'Notifications will be sent when order is confirmed.</span>'
            )

        email_icon = {
            'sent': '✅',
            'failed': '❌',
            'skipped': '⚠️',
            'pending': '⏳',
        }.get(log.email_status, '❓')

        sms_icon = {
            'sent': '✅',
            'failed': '❌',
            'skipped': '⚠️',
            'pending': '⏳',
        }.get(log.sms_status, '❓')

        html = '<table style="width:100%; border-collapse: collapse;">'
        html += '<tr><th style="text-align:left; padding:4px 8px;">Channel</th><th style="text-align:left; padding:4px 8px;">Status</th><th style="text-align:left; padding:4px 8px;">Time</th><th style="text-align:left; padding:4px 8px;">Error</th></tr>'
        html += f'<tr><td style="padding:4px 8px;">📧 Email</td><td style="padding:4px 8px;">{email_icon} {log.email_status.upper()}</td><td style="padding:4px 8px;">{log.email_sent_at or "-"}</td><td style="padding:4px 8px; color: #dc3545;">{log.email_error_message or "-"}</td></tr>'
        html += f'<tr><td style="padding:4px 8px;">📱 SMS</td><td style="padding:4px 8px;">{sms_icon} {log.sms_status.upper()}</td><td style="padding:4px 8px;">{log.sms_sent_at or "-"}</td><td style="padding:4px 8px; color: #dc3545;">{log.sms_error_message or "-"}</td></tr>'
        html += '</table>'
        return format_html(html)
    notification_details.short_description = 'Notification Delivery'

    def notification_status_badge(self, obj):
        """Show a colored badge for notification status."""
        log = NotificationLog.objects.filter(order=obj).first()
        if not log:
            return format_html('<span style="color: #6c757d;">⏳ Pending</span>')

        if log.email_status == 'sent' and log.sms_status == 'sent':
            return format_html('<span style="color: #198754; font-weight: bold;">✅ Delivered</span>')
        elif log.email_status == 'failed' or log.sms_status == 'failed':
            return format_html('<span style="color: #dc3545; font-weight: bold;">❌ Failed</span>')
        elif log.email_status == 'pending' or log.sms_status == 'pending':
            return format_html('<span style="color: #fd7e14; font-weight: bold;">⏳ Sending...</span>')
        else:
            return format_html('<span style="color: #6c757d;">⚠️ Partial</span>')
    notification_status_badge.short_description = 'Notifications'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'shipping_address'
        )

    def save_model(self, request, obj, form, change):
        """Override save to create status history entry when status changes."""
        if change:
            try:
                old_obj = Order.objects.get(pk=obj.pk)
                old_status = old_obj.status
                if old_status != obj.status:
                    # Create status history entry
                    changed_by_name = request.user.get_full_name() or request.user.username
                    OrderStatusHistory.objects.create(
                        order=obj,
                        previous_status=old_status,
                        new_status=obj.status,
                        changed_by=request.user if request.user.is_staff else None,
                        changed_by_name=changed_by_name,
                        notes=f"Status changed from {old_status} to {obj.status} by admin",
                    )
                    
                    # Send notification to user about status change
                    self._send_status_notification(obj, old_status)
            except Order.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

    def _send_status_notification(self, order, old_status):
        """Send notification to user when order status changes."""
        try:
            from .models import Notification
            status_messages = {
                'confirmed': f'Your order {order.order_id} has been confirmed. We\'re preparing your items!',
                'packed': f'Your order {order.order_id} has been packed and is ready for delivery.',
                'out_for_delivery': f'Your order {order.order_id} is out for delivery! Get ready to receive your groceries.',
                'delivered': f'Your order {order.order_id} has been delivered successfully. Enjoy your groceries! 🎉',
                'cancelled': f'Your order {order.order_id} has been cancelled. Please contact support for more information.',
            }
            
            if order.status in status_messages:
                message = status_messages[order.status]
                title = f"Order {order.get_status_display()}"
                
                # Create notification
                Notification.objects.create(
                    user=order.user,
                    title=title,
                    message=message,
                    notification_type='order',
                )
        except Exception:
            pass

    def mark_as_confirmed(self, request, queryset):
        for order in queryset:
            if order.status == 'pending':
                old_status = order.status
                order.status = 'confirmed'
                order.save()
                changed_by_name = request.user.get_full_name() or request.user.username
                OrderStatusHistory.objects.create(
                    order=order,
                    previous_status=old_status,
                    new_status='confirmed',
                    changed_by=request.user,
                    changed_by_name=changed_by_name,
                )
        self.message_user(request, "Selected orders marked as confirmed.")
    mark_as_confirmed.short_description = "Mark selected as Confirmed"

    def mark_as_packed(self, request, queryset):
        for order in queryset:
            old_status = order.status
            order.status = 'packed'
            order.save()
            changed_by_name = request.user.get_full_name() or request.user.username
            OrderStatusHistory.objects.create(
                order=order,
                previous_status=old_status,
                new_status='packed',
                changed_by=request.user,
                changed_by_name=changed_by_name,
            )
        self.message_user(request, "Selected orders marked as packed.")
    mark_as_packed.short_description = "Mark selected as Packed"

    def mark_as_out_for_delivery(self, request, queryset):
        for order in queryset:
            old_status = order.status
            order.status = 'out_for_delivery'
            order.save()
            changed_by_name = request.user.get_full_name() or request.user.username
            OrderStatusHistory.objects.create(
                order=order,
                previous_status=old_status,
                new_status='out_for_delivery',
                changed_by=request.user,
                changed_by_name=changed_by_name,
            )
        self.message_user(request, "Selected orders marked as out for delivery.")
    mark_as_out_for_delivery.short_description = "Mark selected as Out for Delivery"

    def mark_as_delivered(self, request, queryset):
        for order in queryset:
            old_status = order.status
            order.status = 'delivered'
            order.payment_status = 'paid'
            order.save()
            changed_by_name = request.user.get_full_name() or request.user.username
            OrderStatusHistory.objects.create(
                order=order,
                previous_status=old_status,
                new_status='delivered',
                changed_by=request.user,
                changed_by_name=changed_by_name,
            )
        self.message_user(request, "Selected orders marked as delivered.")
    mark_as_delivered.short_description = "Mark selected as Delivered"

    def mark_as_cancelled(self, request, queryset):
        for order in queryset:
            old_status = order.status
            order.status = 'cancelled'
            order.save()
            changed_by_name = request.user.get_full_name() or request.user.username
            OrderStatusHistory.objects.create(
                order=order,
                previous_status=old_status,
                new_status='cancelled',
                changed_by=request.user,
                changed_by_name=changed_by_name,
            )
        self.message_user(request, "Selected orders marked as cancelled.")
    mark_as_cancelled.short_description = "Mark selected as Cancelled"


# ---------- OrderStatusHistory Admin ----------

@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_link', 'previous_status_colored', 'new_status_colored',
        'changed_by_name', 'created_at',
    ]
    list_filter = ['new_status', 'created_at']
    search_fields = ['order__order_id', 'order__id', 'changed_by_name', 'notes']
    list_select_related = ['order', 'changed_by']
    date_hierarchy = 'created_at'
    readonly_fields = ['order', 'previous_status', 'new_status', 'changed_by', 'changed_by_name', 'notes', 'created_at']
    ordering = ['-created_at']

    def order_link(self, obj):
        url = reverse('admin:store_order_change', args=[obj.order.id])
        return format_html('<a href="{}">Order {}</a>', url, obj.order.order_id or f"#{obj.order.id}")
    order_link.short_description = 'Order'
    order_link.admin_order_field = 'order__id'

    def previous_status_colored(self, obj):
        colors = {
            'pending': '#f59e0b',
            'confirmed': '#3b82f6',
            'packed': '#6366f1',
            'out_for_delivery': '#06b6d4',
            'delivered': '#10b981',
            'cancelled': '#ef4444',
            'failed': '#dc2626',
        }
        color = colors.get(obj.previous_status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_previous_status_display().upper() if obj.previous_status else 'N/A',
        )
    previous_status_colored.short_description = 'Previous'

    def new_status_colored(self, obj):
        colors = {
            'pending': '#f59e0b',
            'confirmed': '#3b82f6',
            'packed': '#6366f1',
            'out_for_delivery': '#06b6d4',
            'delivered': '#10b981',
            'cancelled': '#ef4444',
            'failed': '#dc2626',
        }
        color = colors.get(obj.new_status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_new_status_display().upper(),
        )
    new_status_colored.short_description = 'New'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------- NotificationLog Admin ----------

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_link', 'customer_name', 'email_status_colored',
        'sms_status_colored', 'email_sent_at', 'sms_sent_at', 'created_at',
    ]
    list_filter = ['email_status', 'sms_status', 'created_at']
    search_fields = [
        'order__id', 'user__username', 'user__email',
        'email_error_message', 'sms_error_message',
    ]
    readonly_fields = [
        'order', 'user', 'email_status', 'sms_status',
        'email_sent_at', 'sms_sent_at',
        'email_error_message', 'sms_error_message', 'created_at',
    ]
    date_hierarchy = 'created_at'
    list_select_related = ['order', 'user']

    fieldsets = (
        ('Order & Customer', {
            'fields': ('order', 'user'),
        }),
        ('Email Delivery', {
            'fields': ('email_status', 'email_sent_at', 'email_error_message'),
        }),
        ('SMS Delivery', {
            'fields': ('sms_status', 'sms_sent_at', 'sms_error_message'),
        }),
        ('Timestamps', {
            'fields': ('created_at',),
        }),
    )

    def order_link(self, obj):
        url = reverse('admin:store_order_change', args=[obj.order.id])
        return format_html('<a href="{}">Order #{}</a>', url, obj.order.id)
    order_link.short_description = 'Order'
    order_link.admin_order_field = 'order__id'

    def customer_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    customer_name.short_description = 'Customer'
    customer_name.admin_order_field = 'user__first_name'

    def email_status_colored(self, obj):
        colors = {
            'sent': '#198754',
            'failed': '#dc3545',
            'skipped': '#fd7e14',
            'pending': '#6c757d',
        }
        color = colors.get(obj.email_status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.email_status.upper(),
        )
    email_status_colored.short_description = 'Email Status'

    def sms_status_colored(self, obj):
        colors = {
            'sent': '#198754',
            'failed': '#dc3545',
            'skipped': '#fd7e14',
            'pending': '#6c757d',
        }
        color = colors.get(obj.sms_status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.sms_status.upper(),
        )
    sms_status_colored.short_description = 'SMS Status'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# Inline profile in User admin
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fields = ['phone_number', 'age', 'address', 'state', 'profile_image', 'account_status']
    readonly_fields = ['created_at', 'updated_at']


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = [
        'username', 'first_name', 'last_name', 'email',
        'is_active', 'is_staff', 'date_joined',
    ]
    search_fields = ['username', 'first_name', 'last_name', 'email']


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# ---------- Order Tracking Admin ----------

class OrderTrackingHistoryInline(admin.TabularInline):
    """Inline display of tracking history."""
    model = OrderTrackingHistory
    extra = 0
    readonly_fields = ['status', 'description', 'created_at']
    fields = ['status', 'description', 'created_at']
    ordering = ['created_at']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderTracking)
class OrderTrackingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'order_link', 'customer_name', 'status_badge', 'tracking_number',
        'delivery_partner', 'estimated_delivery_date', 'current_location_short', 'updated_at',
    ]
    list_filter = ['status', 'delivery_partner', 'updated_at']
    search_fields = [
        'order__id', 'order__user__username', 'order__user__first_name',
        'order__user__last_name', 'tracking_number', 'delivery_partner',
    ]
    list_select_related = ['order__user', 'order__shipping_address']
    date_hierarchy = 'updated_at'
    inlines = [OrderTrackingHistoryInline]

    fieldsets = (
        ('Order Information', {
            'fields': ('order', 'order_status_display'),
            'description': 'Linked order and its current payment/fulfillment status.',
        }),
        ('Delivery Status', {
            'fields': ('status', 'notes'),
        }),
        ('Tracking Details', {
            'fields': ('tracking_number', 'delivery_partner', 'current_location'),
        }),
        ('Schedule', {
            'fields': ('estimated_delivery_date', 'updated_at'),
        }),
    )

    readonly_fields = ['order', 'order_status_display', 'updated_at']

    def order_link(self, obj):
        url = reverse('admin:store_order_change', args=[obj.order.id])
        return format_html('<a href="{}">Order #{}</a>', url, obj.order.id)
    order_link.short_description = 'Order'
    order_link.admin_order_field = 'order__id'

    def customer_name(self, obj):
        shipping = getattr(obj.order, 'shipping_address', None)
        if shipping:
            return shipping.full_name
        return obj.order.user.get_full_name() or obj.order.user.username
    customer_name.short_description = 'Customer'
    customer_name.admin_order_field = 'order__user__first_name'

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'confirmed': '#3b82f6',
            'packed': '#6366f1',
            'shipped': '#06b6d4',
            'out_for_delivery': '#f59e0b',
            'delivered': '#10b981',
            'cancelled': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display().upper(),
        )
    status_badge.short_description = 'Status'

    def current_location_short(self, obj):
        if obj.current_location:
            return obj.current_location[:50] + ('...' if len(obj.current_location) > 50 else '')
        return '-'
    current_location_short.short_description = 'Location'

    def order_status_display(self, obj):
        """Display the linked order's payment/fulfillment status."""
        return format_html(
            '<span style="font-weight: 500;">{}</span>',
            obj.order.get_status_display(),
        )
    order_status_display.short_description = 'Order Payment Status'

    def save_model(self, request, obj, form, change):
        """Override save to create a history entry when status changes."""
        if change:
            # Get the old status from the database
            old_status = OrderTracking.objects.filter(pk=obj.pk).values_list('status', flat=True).first()
            if old_status and old_status != obj.status:
                # Create a history entry
                description = f"Status updated to {obj.get_status_display()}"
                if obj.notes:
                    description = obj.notes
                OrderTrackingHistory.objects.create(
                    tracking=obj,
                    status=obj.status,
                    description=description,
                )
        else:
            # New tracking record - create initial history entry
            OrderTrackingHistory.objects.create(
                tracking=obj,
                status=obj.status,
                description='Order placed successfully',
            )
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'order__user', 'order__shipping_address'
        )


@admin.register(OrderTrackingHistory)
class OrderTrackingHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'tracking_link', 'status_badge', 'description_short', 'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['tracking__order__id', 'description']
    list_select_related = ['tracking__order']
    date_hierarchy = 'created_at'
    readonly_fields = ['tracking', 'status', 'description', 'created_at']
    ordering = ['-created_at']

    def tracking_link(self, obj):
        url = reverse('admin:store_ordertracking_change', args=[obj.tracking.id])
        return format_html('<a href="{}">Tracking #{} (Order #{})</a>', url, obj.tracking.id, obj.tracking.order.id)
    tracking_link.short_description = 'Tracking'
    tracking_link.admin_order_field = 'tracking__id'

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'confirmed': '#3b82f6',
            'packed': '#6366f1',
            'shipped': '#06b6d4',
            'out_for_delivery': '#f59e0b',
            'delivered': '#10b981',
            'cancelled': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display().upper(),
        )
    status_badge.short_description = 'Status'

    def description_short(self, obj):
        if obj.description:
            return obj.description[:80] + ('...' if len(obj.description) > 80 else '')
        return '-'
    description_short.short_description = 'Description'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------- Notification Admin ----------

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'title', 'notification_type', 'is_read', 'created_at',
    ]
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__username', 'user__email', 'title', 'message']
    list_select_related = ['user']
    date_hierarchy = 'created_at'
    list_editable = ['is_read']
    actions = ['mark_as_read', 'mark_as_unread']

    def is_read_badge(self, obj):
        if obj.is_read:
            return format_html('<span style="color: #198754;">&#10003; Read</span>')
        return format_html('<span style="color: #dc3545; font-weight: bold;">&#9679; Unread</span>')
    is_read_badge.short_description = 'Status'

    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
    mark_as_read.short_description = 'Mark selected as read'

    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False)
    mark_as_unread.short_description = 'Mark selected as unread'


# ---------- Contact Message Admin ----------

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'subject', 'created_at', 'colored_status')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'email', 'phone', 'subject', 'message')
    readonly_fields = ('created_at', 'ip_address')
    actions = ['mark_as_new', 'mark_as_read', 'mark_as_replied']
    list_display_links = ('name', 'subject')
    list_per_page = 25
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Customer Information', {
            'fields': ('name', 'email', 'phone')
        }),
        ('Message Details', {
            'fields': ('subject', 'message')
        }),
        ('Status & Metadata', {
            'fields': ('status', 'ip_address', 'created_at')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).defer('message')

    def colored_status(self, obj):
        colors = {
            'new': '#16A34A',
            'read': '#2563EB',
            'replied': '#9333EA',
        }
        color = colors.get(obj.status, '#6B7280')
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color, obj.get_status_display()
        )
    colored_status.short_description = 'Status'
    colored_status.admin_order_field = 'status'

    def mark_as_new(self, request, queryset):
        queryset.update(status='new', is_read=False)
    mark_as_new.short_description = 'Mark selected as New'

    def mark_as_read(self, request, queryset):
        queryset.update(status='read', is_read=True)
    mark_as_read.short_description = 'Mark selected as Read'

    def mark_as_replied(self, request, queryset):
        queryset.update(status='replied', is_read=True)
    mark_as_replied.short_description = 'Mark selected as Replied'


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'unit_price', 'total_price_display')

    def total_price_display(self, obj):
        return f"Rs. {obj.total_price()}"
    total_price_display.short_description = 'Total Price'


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('quotation_id', 'user', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('quotation_id', 'user__username', 'full_name', 'email', 'phone')
    inlines = [QuotationItemInline]
    date_hierarchy = 'created_at'