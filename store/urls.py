from django.urls import path
from . import views

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

    # AJAX: load subcategories for a category
    path('ajax/load-subcategories/', views.load_subcategories, name='load_subcategories'),
    
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
    path('logout/', views.logoutuser, name='logout'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    
    # Checkout & Stripe
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/save-location/', views.checkout_save_location, name='checkout_save_location'),
    path('checkout/create-session/', views.create_session, name='create_session'),
    path('checkout/success/<int:order_id>/', views.checkout_success, name='checkout_success'),
    path('checkout/cancel/', views.checkout_cancel, name='checkout_cancel'),
    
    # Stripe webhook (optional)
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
    

    # About & Contact
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
]

