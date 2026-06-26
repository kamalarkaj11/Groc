from django.urls import path
from . import views
from . import admin_views

app_name = 'store'

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/<slug:slug>/', views.product_detail, name='product_detail'),

    # Category & Subcategory pages
    path('category/<slug:category_slug>/', views.category_products, name='category_products'),
    path('category/<slug:category_slug>/<slug:subcategory_slug>/', views.subcategory_products, name='subcategory_products'),
    path('category/<slug:category_slug>/<slug:subcategory_slug>/<slug:subsubcategory_slug>/', views.subsubcategory_products, name='subsubcategory_products'),

    # AJAX: load subcategories for a category
    path('ajax/load-subcategories/', views.load_subcategories, name='load_subcategories'),

    # JSON APIs
    path('api/products/', views.api_products, name='api_products'),
    path('api/products/search/', views.api_product_search, name='api_product_search'),
    path('api/cart/', views.api_cart, name='api_cart'),
    path('api/cart/add/', views.api_cart_add, name='api_cart_add'),
    path('api/order/create/', views.api_order_create, name='api_order_create'),
    
    # Cart
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/update-batch/', views.update_cart_batch, name='update_cart_batch'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/count/', views.cart_count, name='cart_count'),
    path('cart/summary/', views.cart_summary, name='cart_summary'),
    
    # Auth
    path('login/', views.normal_login_view, name='login'),
    path('signup/phone/', views.signup_phone_view, name='signup_phone'),
    path('signup/verify/', views.signup_verify_otp_view, name='signup_verify_phone_otp'),
    path('signup/resend/', views.signup_resend_otp_view, name='signup_resend_phone_otp'),
    path('signup/success/', views.signup_success, name='signup_success'),
    path('phone-login/', views.login_with_phone_view, name='phone_login'),
    path('verify-otp/', views.verify_otp_view, name='verify_phone_login_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_phone_otp'),
    path('resend-otp/email/', views.resend_otp, name='resend_otp'),
    path('signup/', views.signup, name='signup'),
    path('verify-email-otp/', views.verify_email_otp_view, name='verify_email_otp'),
    path('verify-phone-otp/', views.verify_phone_otp_view, name='verify_signup_phone_otp'),
    path('resend-email-otp/', views.resend_email_otp_view, name='resend_email_otp'),
    path('resend-phone-otp/', views.resend_phone_otp_view, name='resend_signup_phone_otp'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('verify-otp/<str:username>/', views.verify_otp, name='verify_otp'),
    path('profile/', views.profile, name='profile'),
    path('profile/dashboard/', views.profile_dashboard, name='profile_dashboard'),
    path('logout/', views.logoutuser, name='logout'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    
    # Checkout & Stripe
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/save-location/', views.checkout_save_location, name='checkout_save_location'),
    path('api/save-current-location/', views.save_current_location, name='save_current_location'),
    path('checkout/create-session/', views.create_session, name='create_session'),
    path('checkout/success/<int:order_id>/', views.checkout_success, name='checkout_success'),
    path('checkout/cancel/', views.checkout_cancel, name='checkout_cancel'),
    
    # Stripe webhook (optional)
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
    

    # Newsletter
    path('newsletter/subscribe/', views.newsletter_subscribe, name='newsletter_subscribe'),

    # About & Contact
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),

    # Order Tracking
    path('my-orders/', views.my_orders, name='my_orders'),
    path('profile/orders/', views.my_orders, name='profile_orders'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('track-order/<int:order_id>/', views.track_order, name='track_order'),
    path('api/orders/status/<int:order_id>/', views.api_order_status, name='api_order_status'),

    # Profile Verification
    path('profile/send-otp/', views.profile_send_otp, name='profile_send_otp'),
    path('profile/verify-otp/', views.profile_verify_otp, name='profile_verify_otp'),

    # Invoice URLs
    path('orders/<int:order_id>/invoice/', views.order_invoice_view, name='order_invoice'),
    path('orders/<int:order_id>/invoice/pdf/', views.order_invoice_pdf, name='order_invoice_pdf'),
    path('orders/<int:order_id>/invoice/print/', views.order_invoice_print, name='order_invoice_print'),

    # Admin Order Management (superuser/staff only)
    path('admin/orders/', admin_views.admin_order_dashboard, name='admin_order_dashboard'),
    path('admin/orders/<int:order_id>/', admin_views.admin_order_detail, name='admin_order_detail'),
    path('admin/orders/bulk/update/', admin_views.admin_bulk_update_orders, name='admin_bulk_update_orders'),
    path('admin/orders/export/csv/', admin_views.admin_export_orders, name='admin_export_orders'),
    path('admin/orders/api/stats/', admin_views.admin_order_stats_api, name='admin_order_stats_api'),
    path('admin/orders/<int:order_id>/invoice/regenerate/', views.admin_regenerate_invoice, name='admin_regenerate_invoice'),
    path('admin/orders/<int:order_id>/invoice/history/', views.admin_invoice_history, name='admin_invoice_history'),

    # Notifications
    path('notifications/', views.notifications_page, name='notifications'),
    path('api/notifications/', views.api_notification_list, name='api_notification_list'),
    path('api/notifications/unread-count/', views.api_notification_unread_count, name='api_notification_unread_count'),
    path('api/notifications/mark-read/', views.api_notification_mark_read, name='api_notification_mark_read'),
    path('api/notifications/mark-unread/', views.api_notification_mark_unread, name='api_notification_mark_unread'),
    path('api/notifications/delete/', views.api_notification_delete, name='api_notification_delete'),
    path('api/notifications/mark-all-read/', views.api_notification_mark_all_read, name='api_notification_mark_all_read'),
    path('api/notifications/clear-all/', views.api_notification_clear_all, name='api_notification_clear_all'),

    # Quotations Customer
    path('quotations/request/', views.request_quotation, name='request_quotation'),
    path('quotations/', views.my_quotations, name='my_quotations'),
    path('quotations/<int:quotation_id>/', views.quotation_detail, name='quotation_detail'),
    path('quotations/<int:quotation_id>/pay/', views.pay_quotation, name='pay_quotation'),

    # Quotations Admin
    path('admin/quotations/', admin_views.admin_quotation_dashboard, name='admin_quotation_dashboard'),
    path('admin/quotations/<int:quotation_id>/', admin_views.admin_quotation_detail, name='admin_quotation_detail'),
]

