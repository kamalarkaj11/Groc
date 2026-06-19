from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Profile, PhoneOTP, Review, UserProfile, Category,
    Subcategory, SubSubCategory, Product, CartItem, Order, OrderItem, OrderAddress, OTP,
    NotificationLog
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
admin.site.register(Profile)
admin.site.register(PhoneOTP)


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
        'id', 'customer_name', 'customer_email', 'customer_phone',
        'total_amount', 'status', 'notification_status_badge', 'delivery_city', 'created_at',
    ]
    list_filter = ['status', 'created_at', 'state']
    list_select_related = ['user']
    search_fields = [
        'user__username', 'user__first_name', 'user__last_name',
        'user__email', 'phone', 'address',
        'shipping_address__full_name', 'shipping_address__email',
        'shipping_address__phone',
    ]
    readonly_fields = [
        'user', 'stripe_session_id', 'total_amount', 'created_at',
        'customer_name_display', 'customer_email_display', 'customer_phone_display',
        'delivery_address_display', 'notification_details',
    ]
    date_hierarchy = 'created_at'
    inlines = [OrderAddressInline, OrderItemInline, NotificationLogInline]

    fieldsets = (
        ('Order Info', {
            'fields': ('user', 'status', 'total_amount', 'stripe_session_id', 'created_at'),
        }),
        ('Customer Details', {
            'fields': ('customer_name_display', 'customer_email_display', 'customer_phone_display'),
        }),
        ('Delivery Info', {
            'fields': ('address', 'address_line1', 'city', 'state', 'pincode', 'phone',
                       'delivery_address_display'),
        }),
        ('Notification Status', {
            'fields': ('notification_details',),
            'classes': ('collapse',),
        }),
    )

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