from datetime import timedelta
import json
import logging
import random
from decimal import Decimal, InvalidOperation
import urllib.request as urllib_request

import phonenumbers
import re
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import IntegrityError
from django.db import models
from django.db.models import Avg, Count, Q, Sum
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods, require_POST
from twilio.rest import Client


from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .forms import CustomUserCreationForm, ProfileForm, ChangePasswordForm, CheckoutShippingForm, OTPVerificationForm, PhoneLoginForm, PhoneOTPForm, PhoneSignupForm
from .models import (Category, Subcategory, Order, OrderAddress, OrderItem, Product, Review, UserProfile, CartItem,
                     Profile, PhoneOTP, OTP, NewsletterSubscriber)
from .notifications import send_order_notifications as trigger_order_notifications
from .signals import create_otp, generate_and_send_otp, send_otp_email
from .api_products import CATEGORY_QUERIES, sync_products_for_query, warm_home_products

logger = logging.getLogger(__name__)
PHONE_OTP_RESEND_COOLDOWN_SECONDS = 30
PHONE_OTP_MAX_ATTEMPTS = 3


def deliver_email_otp(user, request=None, create_new=False):
    otp = create_otp(user) if create_new else user.otps.filter(is_latest=True).first()
    if not otp:
        otp = create_otp(user)

    if request:
        request.session.pop('email_otp_delivery_failed', None)
        request.session.pop('email_otp_debug_code', None)

    try:
        send_otp_email(user, otp)
        return otp, True, ''
    except Exception as exc:
        logger.warning('Email OTP was not delivered for %s: %s', user.email, exc)
        if request:
            request.session['email_otp_delivery_failed'] = True
            if getattr(settings, 'EMAIL_OTP_SHOW_ON_DELIVERY_FAILURE', False):
                request.session['email_otp_debug_code'] = otp.otp
        return otp, False, str(exc)


def get_stripe_minimum_amount():
    try:
        minimum = Decimal(str(getattr(settings, 'STRIPE_MINIMUM_PAYMENT_AMOUNT', '50.00')))
    except (InvalidOperation, TypeError, ValueError):
        minimum = Decimal('50.00')
    return minimum.quantize(Decimal('0.01'))


def normalize_phone_number(phone_text):
    phone_text = (phone_text or '').strip()
    if not phone_text:
        return None
    try:
        parsed = phonenumbers.parse(phone_text, 'IN')
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


def generate_otp():
    return f"{random.randint(0, 999999):06d}"


def build_username_from_phone(phone):
    digits = re.sub(r'\D', '', phone)
    if not digits:
        digits = str(random.randint(100000, 999999))
    base_username = f"user_{digits[-10:]}"
    username = base_username[:30]
    suffix = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username[:26]}_{suffix}"
        suffix += 1
    return username


def send_otp_via_twilio(phone, otp):
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_PHONE_NUMBER
    if not account_sid or not auth_token or not from_number:
        raise RuntimeError('Twilio credentials are not configured.')

    client = Client(account_sid, auth_token)
    message_text = f"Your OTP is {otp}"
    message = client.messages.create(
        body=message_text,
        from_=from_number,
        to=phone,
    )
    return message.sid


def create_or_update_phone_otp(phone, otp_code):
    otp_object = PhoneOTP.objects.create(phone=phone, otp=otp_code)
    return otp_object


def create_password_change_otp(user):
    OTP.objects.filter(user=user, is_latest=True).update(is_latest=False)
    otp_code = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=5)
    otp = OTP.objects.create(
        user=user,
        otp=otp_code,
        expires_at=expires_at,
        max_attempts=3,
        is_latest=True,
    )
    return otp


def send_password_change_email(user, otp_code):
    subject = 'Password Change Verification OTP'
    message = f'Your OTP for password change is: {otp_code}'
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def init_password_change_session(request, otp):
    request.session['password_change_user_id'] = request.user.id
    request.session['password_change_email_otp'] = otp.otp
    request.session['password_change_otp_created_time'] = timezone.now().isoformat()
    request.session['password_change_otp_last_sent'] = timezone.now().isoformat()
    request.session['password_change_otp_attempts'] = 0
    request.session['password_change_verified'] = False


def clear_password_change_session(request):
    keys = [
        'password_change_user_id',
        'password_change_email_otp',
        'password_change_otp_created_time',
        'password_change_otp_last_sent',
        'password_change_otp_attempts',
        'password_change_verified',
    ]
    for key in keys:
        request.session.pop(key, None)


def normal_login_view(request):
    """Normal username/password login view"""
    if request.user.is_authenticated:
        return redirect('store:dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        remember_me = request.POST.get('remember_me')
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                if remember_me:
                    # Set session expiry to 30 days
                    request.session.set_expiry(60 * 60 * 24 * 30)
                else:
                    # Set session expiry to browser close
                    request.session.set_expiry(0)
                messages.success(request, f"Welcome back, {username}!")
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('store:dashboard')
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    
    return render(request, 'login.html', {'form': form})


def signup_phone_view(request):
    if request.user.is_authenticated:
        return redirect('store:dashboard')

    if request.method == 'POST':
        form = PhoneSignupForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone']
            existing = Profile.objects.filter(phone_number=phone).exists()
            if existing:
                messages.warning(request, 'This phone number is already registered. Please log in instead.')
                return render(request, 'enter_phone.html', {'form': form})

            latest_otp = PhoneOTP.objects.filter(phone=phone).first()
            if latest_otp and not latest_otp.can_resend:
                wait_seconds = 30 - int((timezone.now() - latest_otp.created_at).total_seconds())
                messages.warning(request, f'Please wait {wait_seconds} seconds before requesting a new OTP.')
                return render(request, 'enter_phone.html', {'form': form})

            otp_code = generate_otp()
            try:
                send_otp_via_twilio(phone, otp_code)
            except Exception:
                logger.exception('Twilio send failed for %s', phone)
                messages.error(request, 'Unable to send OTP at this time. Please try again later.')
                return render(request, 'enter_phone.html', {'form': form})

            create_or_update_phone_otp(phone, otp_code)
            request.session['signup_phone'] = phone
            request.session['signup_otp_sent_at'] = timezone.now().isoformat()
            messages.success(request, f'OTP sent to {phone}. Please verify it within 5 minutes.')
            return redirect('store:signup_verify_phone_otp')
    else:
        form = PhoneSignupForm()

    return render(request, 'enter_phone.html', {'form': form})


def login_with_phone_view(request):
    if request.method == 'POST':
        form = PhoneLoginForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone']
            logger.info('Phone login requested for: %s', phone)
            profile = Profile.objects.filter(phone_number=phone).select_related('user').first()
            logger.info('Phone profile found: %s', bool(profile))
            if not profile:
                messages.warning(request, 'This phone number is not registered. Please sign up first.')
                return render(request, 'phone_login.html', {'form': form})

            otp_code = generate_otp()
            try:
                send_otp_via_twilio(phone, otp_code)
            except Exception as exc:
                logger.exception('Twilio send failed for %s', phone)
                messages.error(request, 'Unable to send OTP at this time. Please try again later.')
                return render(request, 'phone_login.html', {'form': form})

            create_or_update_phone_otp(phone, otp_code)
            request.session['phone_for_otp'] = phone
            request.session['otp_sent_at'] = timezone.now().isoformat()
            messages.success(request, f'OTP sent to {phone}. Please verify within 5 minutes.')
            return redirect('store:verify_phone_login_otp')
    else:
        form = PhoneLoginForm()
    return render(request, 'phone_login.html', {'form': form})


def verify_otp_view(request):
    phone = request.session.get('phone_for_otp')
    if not phone:
        messages.error(request, 'Session expired or invalid. Please enter your phone number again.')
        return redirect('store:phone_login')

    latest_otp = PhoneOTP.objects.filter(phone=phone).first()
    if not latest_otp:
        messages.error(request, 'No OTP request found. Please request a new OTP.')
        return redirect('store:phone_login')

    if request.method == 'POST':
        form = PhoneOTPForm(request.POST)
        if form.is_valid():
            otp_input = form.cleaned_data['otp']
            if latest_otp.is_expired:
                messages.error(request, 'OTP expired. Please resend a new code.')
                return render(request, 'verify_otp.html', {
                    'form': form,
                    'phone': phone,
                    'change_number_url_name': 'store:phone_login',
                    'resend_url_name': 'store:resend_phone_otp',
                })

            if latest_otp.attempts >= 3:
                messages.error(request, 'Maximum OTP attempts reached. Please resend a new code.')
                return render(request, 'verify_otp.html', {
                    'form': form,
                    'phone': phone,
                    'change_number_url_name': 'store:phone_login',
                    'resend_url_name': 'store:resend_phone_otp',
                })

            if otp_input != latest_otp.otp:
                latest_otp.attempts += 1
                latest_otp.save()
                remaining = max(0, 3 - latest_otp.attempts)
                messages.error(request, f'Invalid OTP. You have {remaining} attempt(s) left.')
                return render(request, 'verify_otp.html', {
                    'form': form,
                    'phone': phone,
                    'change_number_url_name': 'store:phone_login',
                    'resend_url_name': 'store:resend_phone_otp',
                })

            profile = Profile.objects.filter(phone_number=phone).select_related('user').first()
            logger.info('OTP verification for phone: %s, profile exists: %s', phone, bool(profile))
            if not profile:
                messages.error(request, 'This phone number is not registered. Please sign up first.')
                return redirect('store:phone_login')

            user = profile.user
            profile.is_phone_verified = True
            profile.save()

            # Keep UserProfile in sync with phone OTP login so profile page shows the phone number.
            user_profile, _ = UserProfile.objects.get_or_create(user=user)
            user_profile.phone_number = phone
            user_profile.save()

            latest_otp.attempts += 1
            latest_otp.save()

            login(request, user)
            request.session.pop('phone_for_otp', None)
            messages.success(request, 'Logged in successfully using OTP!')
            return redirect('store:dashboard')
    else:
        form = PhoneOTPForm()
    return render(request, 'verify_otp.html', {'form': form, 'phone': phone, 'change_number_url_name': 'store:phone_login', 'resend_url_name': 'store:resend_phone_otp'})


def signup_verify_otp_view(request):
    phone = request.session.get('signup_phone')
    if not phone:
        messages.error(request, 'Session expired or invalid. Please enter your phone number again.')
        return redirect('store:signup_phone')

    latest_otp = PhoneOTP.objects.filter(phone=phone).first()
    if not latest_otp:
        messages.error(request, 'No OTP request found. Please request a new OTP.')
        return redirect('store:signup_phone')

    if request.method == 'POST':
        form = PhoneOTPForm(request.POST)
        if form.is_valid():
            otp_input = form.cleaned_data['otp']
            if latest_otp.is_expired:
                messages.error(request, 'OTP expired. Please resend a new code.')
                return render(request, 'verify_otp.html', {
                    'form': form,
                    'phone': phone,
                    'change_number_url_name': 'store:signup_phone',
                    'resend_url_name': 'store:signup_resend_phone_otp',
                })

            if latest_otp.attempts >= 3:
                messages.error(request, 'Maximum OTP attempts reached. Please resend a new code.')
                return render(request, 'verify_otp.html', {
                    'form': form,
                    'phone': phone,
                    'change_number_url_name': 'store:signup_phone',
                    'resend_url_name': 'store:signup_resend_phone_otp',
                })

            if otp_input != latest_otp.otp:
                latest_otp.attempts += 1
                latest_otp.save()
                remaining = max(0, 3 - latest_otp.attempts)
                messages.error(request, f'Invalid OTP. You have {remaining} attempt(s) left.')
                return render(request, 'verify_otp.html', {
                    'form': form,
                    'phone': phone,
                    'change_number_url_name': 'store:signup_phone',
                    'resend_url_name': 'store:signup_resend_phone_otp',
                })

            username = build_username_from_phone(phone)
            user = User.objects.create(username=username)
            user.set_unusable_password()
            user.is_active = True
            user.save()

            profile = Profile.objects.create(user=user, phone_number=phone, is_phone_verified=True)
            user_profile, _ = UserProfile.objects.get_or_create(user=user)
            user_profile.phone_number = phone
            user_profile.save()

            login(request, user)
            request.session.pop('signup_phone', None)
            request.session.pop('signup_otp_sent_at', None)
            messages.success(request, 'Phone verified successfully! You are now logged in.')
            return redirect('store:signup_success')
    else:
        form = PhoneOTPForm()

    return render(request, 'verify_otp.html', {
        'form': form,
        'phone': phone,
        'change_number_url_name': 'store:signup_phone',
        'resend_url_name': 'store:signup_resend_phone_otp',
    })


@require_POST
def resend_otp_view(request):
    phone = request.session.get('phone_for_otp')
    if not phone:
        return JsonResponse({'success': False, 'error': 'Session expired. Please start again.'}, status=400)

    latest_otp = PhoneOTP.objects.filter(phone=phone).first()
    if latest_otp and not latest_otp.can_resend:
        wait_seconds = 30 - int((timezone.now() - latest_otp.created_at).total_seconds())
        return JsonResponse({'success': False, 'error': f'Please wait {wait_seconds} seconds before resending.'}, status=429)

    otp_code = generate_otp()
    try:
        send_otp_via_twilio(phone, otp_code)
    except Exception as exc:
        logger.exception('Twilio resend failed for %s', phone)
        return JsonResponse({'success': False, 'error': 'Unable to resend OTP right now.'}, status=500)

    create_or_update_phone_otp(phone, otp_code)
    request.session['otp_sent_at'] = timezone.now().isoformat()
    return JsonResponse({'success': True, 'message': 'OTP resent successfully.'})


@require_POST
def signup_resend_otp_view(request):
    phone = request.session.get('signup_phone')
    if not phone:
        return JsonResponse({'success': False, 'error': 'Session expired. Please start again.'}, status=400)

    latest_otp = PhoneOTP.objects.filter(phone=phone).first()
    if latest_otp and not latest_otp.can_resend:
        wait_seconds = 30 - int((timezone.now() - latest_otp.created_at).total_seconds())
        return JsonResponse({'success': False, 'error': f'Please wait {wait_seconds} seconds before resending.'}, status=429)

    otp_code = generate_otp()
    try:
        send_otp_via_twilio(phone, otp_code)
    except Exception:
        logger.exception('Twilio resend failed for %s', phone)
        return JsonResponse({'success': False, 'error': 'Unable to resend OTP right now.'}, status=500)

    create_or_update_phone_otp(phone, otp_code)
    request.session['signup_otp_sent_at'] = timezone.now().isoformat()
    return JsonResponse({'success': True, 'message': 'OTP resent successfully.'})


def signup_success(request):
    if not request.user.is_authenticated:
        return redirect('store:login')
    return render(request, 'success.html')


def dashboard(request):
    """Redirect to the enhanced profile dashboard."""
    if not request.user.is_authenticated:
        return redirect('store:login')
    return redirect('store:profile_dashboard')


def home(request):
    warm_home_products()
    featured_products = Product.objects.filter(is_out_of_stock=False).select_related('category', 'subcategory').order_by('-created_at')[:12]
    categories = Category.objects.prefetch_related('subcategories').annotate(
        active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
    ).filter(is_active=True).order_by('sort_order')[:6]
    context = {
        'featured_products': featured_products,
        'products': featured_products,
        'categories': categories,
    }
    return render(request, 'home.html', context)

def product_list(request):
    query = request.GET.get('q')
    category_slug = request.GET.get('category')
    subcategory_slug = request.GET.get('subcategory')

    if query:
        sync_products_for_query(query, page=request.GET.get('page', 1), limit=24)
    elif category_slug:
        sync_products_for_query(CATEGORY_QUERIES.get(category_slug, category_slug), page=request.GET.get('page', 1), limit=24)
    else:
        warm_home_products()

    products = Product.objects.filter(is_out_of_stock=False).select_related('category', 'subcategory').order_by('-created_at', '-id')

    if query:
        products = products.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if category_slug:
        products = products.filter(category__slug=category_slug)
    if subcategory_slug:
        products = products.filter(subcategory__slug=subcategory_slug)

    categories = Category.objects.prefetch_related('subcategories').annotate(
        active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
    ).filter(is_active=True).order_by('sort_order')

    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'products': page_obj,
        'categories': categories,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'query': query,
        'selected_category': category_slug,
        'selected_subcategory': subcategory_slug,
    }
    return render(request, 'products/list.html', context)

def product_detail(request, slug):
    product = get_object_or_404(Product.objects.select_related('category', 'subcategory'), is_out_of_stock=False, slug=slug)
    
    # Dynamic data
    reviews = product.reviews.all()[:5]  # Recent 5 reviews
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
    if avg_rating:
        avg_rating = round(float(avg_rating), 1)
        review_count = reviews.count()
    elif product.api_rating:
        avg_rating = float(product.api_rating)
        review_count = product.api_review_count
    else:
        avg_rating = 0
        review_count = 0
    
    related_products = Product.objects.filter(
        category=product.category,
        is_out_of_stock=False
    ).exclude(id=product.id)[:4]
    
    # Fallback highlights if empty
    if not product.highlights:
        product.highlights = ['100% Fresh', 'Quality Guaranteed', 'Fast Delivery']
    
    # Fallback nutrition
    if not product.nutrition_info:
        product.nutrition_info = {
            'calories': '85 kcal',
            'protein': '2.5g',
            'carbs': '18g',
            'fat': '0.3g',
            'fiber': '2.8g'
        }
    
    if request.method == 'POST' and request.user.is_authenticated:
        rating = request.POST.get('rating')
        comment = request.POST.get('comment') or ''
        try:
            Review.objects.create(
                product=product,
                user=request.user,
                rating=int(rating),
                comment=comment.strip()
            )
            messages.success(request, 'Review added successfully!')
        except ValueError:
            messages.error(request, 'Invalid rating.')
        return redirect('store:product_detail', slug=slug)
    
    # Recalculate reviews after potential add
    reviews = product.reviews.all()[:5]
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
    if avg_rating:
        avg_rating = round(float(avg_rating), 1)
        review_count = reviews.count()
    elif product.api_rating:
        avg_rating = float(product.api_rating)
        review_count = product.api_review_count
    else:
        avg_rating = 0
        review_count = 0
    
    context = {
        'product': product,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'review_count': review_count,
        'related_products': related_products,
        'rating_choices': Review.RATING_CHOICES,
    }
    return render(request, 'products/detail.html', context)


@login_required
def cart_view(request):
    cart_items = CartItem.objects.filter(user=request.user)
    total = sum(item.total_price() for item in cart_items)
    context = {
        'cart_items': cart_items,
        'total': total,
    }
    return render(request, 'cart.html', context)

@login_required
def update_cart_batch(request):
    if request.method == 'POST':
        quantities = request.POST.getlist('quantities')
        cart_items = CartItem.objects.filter(user=request.user)
        updated = 0
        for item in cart_items:
            try:
                qty = int(quantities[updated])
                if qty > 0:
                    item.quantity = qty
                    item.save()
                    updated += 1
                else:
                    item.delete()
            except (ValueError, IndexError):
                pass
        if updated > 0:
            messages.success(request, f'Cart updated with {updated} items!')
        else:
            messages.warning(request, 'No valid quantities provided.')
    return redirect('store:cart')

@login_required
def add_to_cart(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        try:
            quantity = max(int(request.POST.get('qty', 1)), 1)
        except (TypeError, ValueError):
            quantity = 1
        product = get_object_or_404(Product, id=product_id)
        cart_item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={'quantity': quantity}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()
        messages.success(request, f'{product.title} added to cart!')
    return redirect('store:cart')


def _product_image_url(product):
    if product.external_image_url:
        return product.external_image_url
    if product.image:
        return product.image.url
    return ""


def _serialize_product(product):
    rating = product.api_rating
    review_count = product.api_review_count
    local_rating = product.reviews.aggregate(Avg('rating'))['rating__avg']
    if local_rating:
        rating = round(Decimal(str(local_rating)), 1)
        review_count = product.reviews.count()
    return {
        'id': product.id,
        'title': product.title,
        'slug': product.slug,
        'description': product.description,
        'price': str(product.get_price()),
        'original_price': str(product.price),
        'image': _product_image_url(product),
        'rating': str(rating or ''),
        'reviews': review_count or 0,
        'availability': product.availability or ('Out of Stock' if product.is_out_of_stock else 'In Stock'),
        'category': product.category.name,
        'detail_url': request_path_for_product(product),
    }


def request_path_for_product(product):
    return f"/products/{product.slug}/"


def api_products(request):
    query = request.GET.get('q') or request.GET.get('query') or ''
    page = request.GET.get('page', 1)
    if query:
        sync_products_for_query(query, page=page, limit=24)
    products = Product.objects.filter(is_out_of_stock=False).select_related('category').order_by('-created_at', '-id')
    if query:
        products = products.filter(Q(title__icontains=query) | Q(description__icontains=query))
    return JsonResponse({
        'products': [_serialize_product(product) for product in products[:24]],
    })


def api_product_search(request):
    query = (request.GET.get('q') or request.GET.get('query') or '').strip()
    if len(query) >= 2:
        sync_products_for_query(query, limit=10)
    products = Product.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query),
        is_out_of_stock=False,
    ).select_related('category').order_by('-created_at', '-id')[:8] if query else []
    return JsonResponse({
        'results': [
            {
                'id': product.id,
                'title': product.title,
                'price': str(product.get_price()),
                'image': _product_image_url(product),
                'url': request_path_for_product(product),
                'category': product.category.name,
            }
            for product in products
        ]
    })


@login_required
def api_cart(request):
    cart_items = CartItem.objects.filter(user=request.user).select_related('product', 'product__category')
    return JsonResponse({
        'items': [
            {
                'id': item.id,
                'quantity': item.quantity,
                'total': str(item.total_price()),
                'product': _serialize_product(item.product),
            }
            for item in cart_items
        ],
        'total': str(sum(item.total_price() for item in cart_items)),
    })


@login_required
@require_POST
def api_cart_add(request):
    product_id = request.POST.get('product_id')
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except ValueError:
        payload = {}
    product_id = product_id or payload.get('product_id')
    quantity = payload.get('quantity') or request.POST.get('quantity') or request.POST.get('qty') or 1
    try:
        quantity = max(int(quantity), 1)
    except (TypeError, ValueError):
        quantity = 1
    product = get_object_or_404(Product, id=product_id, is_out_of_stock=False)
    cart_item, created = CartItem.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': quantity},
    )
    if not created:
        cart_item.quantity += quantity
        cart_item.save()
    return JsonResponse({'success': True, 'item_count': CartItem.objects.filter(user=request.user).count()})


@login_required
@require_POST
def api_order_create(request):
    cart_items = CartItem.objects.filter(user=request.user).select_related('product')
    if not cart_items:
        return JsonResponse({'success': False, 'error': 'Cart is empty.'}, status=400)
    total = sum(item.total_price() for item in cart_items)
    order = Order.objects.create(user=request.user, total_amount=total, status='pending')
    for item in cart_items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity,
            price=item.product.get_price(),
        )
    cart_items.delete()
    return JsonResponse({'success': True, 'order_id': order.id, 'total': str(total)})

@login_required
def update_cart(request):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        action = request.POST.get('action')
        try:
            item = CartItem.objects.get(id=item_id, user=request.user)
            if action == 'increase':
                item.quantity += 1
            elif action == 'decrease' and item.quantity > 1:
                item.quantity -= 1
            item.save()
            messages.success(request, 'Cart updated!')
        except CartItem.DoesNotExist:
            messages.error(request, 'Item not found.')
    return redirect('store:cart')

@login_required
def remove_from_cart(request):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        try:
            item = CartItem.objects.get(id=item_id, user=request.user)
            item.delete()
            messages.success(request, 'Item removed from cart!')
        except CartItem.DoesNotExist:
            pass
    return redirect('store:cart')

def cart_count(request):
    """
    Return cart item count as JSON for navbar badge.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'count': 0})
    count = CartItem.objects.filter(user=request.user).count()
    return JsonResponse({'count': count})

def cart_summary(request):
    """
    Return cart count and grandtotal as JSON for navbar.
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'count': 0,
            'grandtotal': '0',
        })
    cart_items = CartItem.objects.filter(user=request.user)
    count = cart_items.count()
    grandtotal = sum(item.total_price() for item in cart_items)
    return JsonResponse({
        'count': count,
        'grandtotal': str(grandtotal),
    })


def logoutuser(request):
    logout(request)
    messages.info(request, 'Logged out successfully.')
    return redirect('store:home')

def signup(request):
    if request.user.is_authenticated:
        return redirect('store:dashboard')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            profile = UserProfile.objects.get(user=user)
            profile.age = form.cleaned_data.get('age')
            profile.phone_number = form.cleaned_data.get('phone_number')
            profile.address = form.cleaned_data.get('address')
            profile.state = form.cleaned_data.get('state')
            profile.save()

            normalized_phone = form.cleaned_data.get('phone_number')
            request.session['signup_user_id'] = user.id
            request.session['signup_phone'] = normalized_phone
            request.session['email_verified'] = False
            request.session['email_otp_resend_at'] = timezone.now().isoformat()

            _, email_sent, _ = deliver_email_otp(user, request=request)
            if email_sent:
                messages.success(request, 'Account created. Please verify your email address with the code we sent.')
            else:
                messages.warning(request, 'Account created, but we could not send the email OTP right now. Please use resend OTP.')
            return redirect('store:verify_email_otp')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})


def verify_email_otp_view(request):
    signup_user_id = request.session.get('signup_user_id')
    if not signup_user_id:
        messages.error(request, 'Your session expired. Please sign up again.')
        return redirect('store:signup')

    user = get_object_or_404(User, id=signup_user_id, is_active=False)

    if request.method == 'POST':
        form = OTPVerificationForm(request.POST, user=user)
        if form.is_valid():
            latest_otp = user.otps.filter(is_latest=True).first()
            if latest_otp:
                latest_otp.is_used = True
                latest_otp.save()

            request.session['email_verified'] = True
            try:
                success, wait_seconds = send_signup_phone_otp(request, request.session['signup_phone'])
                if success:
                    messages.success(request, 'OTP has been sent to your phone number.')
                else:
                    messages.warning(request, f'Email verified. Please wait {wait_seconds} seconds before requesting a new phone OTP.')
            except Exception:
                logger.exception('Failed to automatically send signup phone OTP for user %s', user.id)
                messages.error(request, 'Email verified, but we could not send the phone OTP right now. Please use resend OTP.')
            return redirect('store:verify_signup_phone_otp')
    else:
        form = OTPVerificationForm(user=user)

    return render(request, 'registration/verify_email_otp.html', {
        'form': form,
        'user_email': user.email,
        'email_delivery_failed': request.session.get('email_otp_delivery_failed', False),
        'debug_email_otp': request.session.get('email_otp_debug_code') if getattr(settings, 'EMAIL_OTP_SHOW_ON_DELIVERY_FAILURE', False) else '',
    })


def get_phone_otp_wait_seconds(phone):
    latest_otp = PhoneOTP.objects.filter(phone=phone).first()
    if not latest_otp or latest_otp.can_resend:
        return 0
    elapsed = int((timezone.now() - latest_otp.created_at).total_seconds())
    return max(0, PHONE_OTP_RESEND_COOLDOWN_SECONDS - elapsed)


def render_phone_otp_page(request, form, phone, status_code=200):
    return render(request, 'registration/verify_phone_otp.html', {
        'form': form,
        'phone': phone,
        'resend_cooldown_seconds': PHONE_OTP_RESEND_COOLDOWN_SECONDS,
        'resend_wait_seconds': get_phone_otp_wait_seconds(phone),
    }, status=status_code)


def send_signup_phone_otp(request, phone, force=False):
    """Send the signup phone OTP and store resend metadata in the session."""
    latest_otp = PhoneOTP.objects.filter(phone=phone).first()
    if latest_otp and not latest_otp.can_resend and not force:
        wait_seconds = get_phone_otp_wait_seconds(phone)
        return False, wait_seconds

    otp_code = generate_otp()
    send_otp_via_twilio(phone, otp_code)
    create_or_update_phone_otp(phone, otp_code)
    request.session['signup_phone_otp_sent_at'] = timezone.now().isoformat()
    request.session['signup_phone_otp_phone'] = phone
    return True, None


def verify_phone_otp_view(request):
    signup_user_id = request.session.get('signup_user_id')
    email_verified = request.session.get('email_verified')
    phone = request.session.get('signup_phone')

    if not signup_user_id or not email_verified or not phone:
        messages.error(request, 'Please complete signup and email verification first.')
        return redirect('store:signup')

    user = get_object_or_404(User, id=signup_user_id, is_active=False)
    normalized_phone = normalize_phone_number(phone)
    if not normalized_phone or normalized_phone != phone:
        messages.error(request, 'Wrong phone number in signup session. Please sign up again.')
        return redirect('store:signup')

    latest_otp = PhoneOTP.objects.filter(phone=phone).first()

    if request.method == 'POST':
        form = PhoneOTPForm(request.POST)
        if form.is_valid():
            otp_input = form.cleaned_data['otp']
            if not latest_otp:
                messages.error(request, 'No OTP request found. Please resend the code.')
                return render_phone_otp_page(request, form, phone)

            if latest_otp.is_expired:
                messages.error(request, 'OTP expired. Please resend a new code.')
                return render_phone_otp_page(request, form, phone)

            if latest_otp.attempts >= PHONE_OTP_MAX_ATTEMPTS:
                messages.error(request, 'Maximum OTP attempts reached. Please resend a new code.')
                return render_phone_otp_page(request, form, phone)

            if otp_input != latest_otp.otp:
                latest_otp.attempts += 1
                latest_otp.save()
                remaining = max(0, PHONE_OTP_MAX_ATTEMPTS - latest_otp.attempts)
                messages.error(request, f'Invalid Phone OTP. You have {remaining} attempt(s) left.')
                return render_phone_otp_page(request, form, phone)

            # Check if phone number is already taken by another user
            existing_profile = Profile.objects.filter(phone_number=phone).exclude(user=user).first()
            if existing_profile:
                messages.error(request, 'This phone number is already registered to another account. Please use a different phone number.')
                return redirect('store:signup')

            latest_otp.attempts += 1
            latest_otp.save()
            user.is_active = True
            user.save()

            try:
                Profile.objects.update_or_create(
                    user=user,
                    defaults={
                        'phone_number': phone,
                        'is_email_verified': True,
                        'is_phone_verified': True,
                    }
                )
            except IntegrityError:
                messages.error(request, 'This phone number is already in use. Please try signing up with a different phone number.')
                return redirect('store:signup')

            user_profile = UserProfile.objects.get_or_create(user=user)[0]
            user_profile.phone_number = phone
            user_profile.save()

            login(request, user)
            request.session.pop('signup_user_id', None)
            request.session.pop('signup_phone', None)
            request.session.pop('email_verified', None)
            request.session.pop('email_otp_resend_at', None)
            request.session.pop('signup_phone_otp_sent_at', None)
            request.session.pop('signup_phone_otp_phone', None)

            messages.success(request, 'Phone verified and account activated. Welcome to GroceryHub!')
            return redirect('store:dashboard')
    else:
        form = PhoneOTPForm()
        otp_sent_for_phone = request.session.get('signup_phone_otp_phone')
        if not latest_otp or otp_sent_for_phone != phone:
            try:
                success, wait_seconds = send_signup_phone_otp(request, phone)
                if not success:
                    messages.warning(request, f'Please wait {wait_seconds} seconds before requesting a new code.')
                else:
                    messages.success(request, 'OTP has been sent to your phone number.')
                latest_otp = PhoneOTP.objects.filter(phone=phone).first()
            except Exception:
                logger.exception('Failed to send signup phone OTP for %s', phone)
                messages.error(request, 'Unable to send phone OTP right now. Please try again later.')

    return render_phone_otp_page(request, form, phone)


def resend_email_otp_view(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required.')

    signup_user_id = request.session.get('signup_user_id')
    if not signup_user_id:
        return JsonResponse({'success': False, 'error': 'Session expired. Please sign up again.'}, status=400)

    user = get_object_or_404(User, id=signup_user_id, is_active=False)
    now = timezone.now()
    last_resend = request.session.get('email_otp_resend_at')
    if last_resend:
        last_resend = timezone.datetime.fromisoformat(last_resend)
        if (now - last_resend).seconds < 30:
            remaining = 30 - (now - last_resend).seconds
            return JsonResponse({'success': False, 'error': f'Please wait {remaining}s before resending.'}, status=429)

    try:
        _, email_sent, _ = deliver_email_otp(user, request=request, create_new=True)
        request.session['email_otp_resend_at'] = now.isoformat()
        if not email_sent:
            return JsonResponse({'success': False, 'error': 'Unable to resend OTP right now.'}, status=503)
        return JsonResponse({'success': True, 'message': 'Email OTP resent successfully.'})
    except Exception:
        logger.exception('Failed to resend email OTP for %s', user.email)
        return JsonResponse({'success': False, 'error': 'Unable to resend OTP right now.'}, status=500)


def resend_phone_otp_view(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required.')

    phone = request.session.get('signup_phone')
    signup_user_id = request.session.get('signup_user_id')
    email_verified = request.session.get('email_verified')
    if not signup_user_id or not email_verified or not phone:
        return JsonResponse({'success': False, 'error': 'Please complete email verification first.'}, status=400)

    normalized_phone = normalize_phone_number(phone)
    if not normalized_phone or normalized_phone != phone:
        return JsonResponse({'success': False, 'error': 'Invalid phone number in signup session.'}, status=400)

    try:
        success, wait_seconds = send_signup_phone_otp(request, phone)
        if not success:
            return JsonResponse({
                'success': False,
                'error': f'Please wait {wait_seconds} seconds before resending.',
                'wait_seconds': wait_seconds,
            }, status=429)
        return JsonResponse({
            'success': True,
            'message': 'OTP has been sent to your phone number.',
            'cooldown_seconds': PHONE_OTP_RESEND_COOLDOWN_SECONDS,
        })
    except Exception:
        logger.exception('Twilio resend failed for %s', phone)
        return JsonResponse({'success': False, 'error': 'Unable to resend OTP right now.'}, status=500)


def verify_otp(request, username):
    try:
        user = User.objects.get(username=username, is_active=False)
    except User.DoesNotExist:
        messages.error(request, 'User not found or already verified.')
        return redirect('store:signup')
    
    if request.method == 'POST':
        form = OTPVerificationForm(request.POST, user=user)
        if form.is_valid():
            # Activate user
            user.is_active = True
            user.save()
            
            # Mark OTP as used
            latest_otp = user.otps.filter(is_latest=True).first()
            if latest_otp:
                latest_otp.is_used = True
                latest_otp.save()
            
            login(request, user)
            messages.success(request, 'Email verified successfully! Welcome to GroceryHub.')
            return redirect('store:profile')
    else:
        form = OTPVerificationForm(user=user)
    
    context = {
        'form': form,
        'username': username,
        'user_email': user.email,
    }
    return render(request, 'registration/verify_otp.html', context)


@require_http_methods(["POST"])
def resend_otp(request):
    username = request.POST.get('username')
    try:
        user = User.objects.get(username=username, is_active=False)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found.'}, status=404)
    
    # Cooldown check (simple session based)
    now = timezone.now()
    last_resend = request.session.get('otp_resend_time', None)
    if last_resend and (now - last_resend).seconds < 30:
        remaining = 30 - (now - last_resend).seconds
        return JsonResponse({
            'success': False, 
            'error': f'Please wait {remaining}s before resending.'
        })
    
    try:
        generate_and_send_otp(user)
        request.session['otp_resend_time'] = now
        return JsonResponse({'success': True, 'message': 'New OTP sent to your email!'})
    except Exception as e:
        logger.error(f"Resend OTP error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Failed to send OTP.'}, status=500)


@login_required
def profile(request):
    """Display user profile with all stored registration details."""
    user_profile = request.user.userprofile
    recent_orders = Order.objects.filter(
        user=request.user
    ).select_related('shipping_address').order_by('-created_at')[:5]
    total_orders = Order.objects.filter(user=request.user).count()
    paid_orders = Order.objects.filter(user=request.user, status='paid').count()
    recent_reviews = Review.objects.filter(
        user=request.user
    ).select_related('product').order_by('-created_at')[:5]

    context = {
        'profile': user_profile,
        'recent_orders': recent_orders,
        'total_orders': total_orders,
        'paid_orders': paid_orders,
        'recent_reviews': recent_reviews,
    }
    return render(request, 'profile.html', context)


@login_required
def edit_profile(request):
    """Allow users to update their profile information."""
    user_profile = request.user.userprofile
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('store:profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProfileForm(instance=user_profile)
    return render(request, 'edit_profile.html', {'form': form, 'profile': user_profile})


@login_required
def profile_dashboard(request):
    """Profile Dashboard showing account overview, recent activity, and statistics."""
    user_profile = request.user.userprofile

    # Optimized queries with select_related/prefetch_related
    recent_orders = Order.objects.filter(
        user=request.user
    ).select_related('shipping_address').order_by('-created_at')[:5]
    total_orders = Order.objects.filter(user=request.user).count()
    paid_orders = Order.objects.filter(user=request.user, status='paid').count()
    total_spent = Order.objects.filter(
        user=request.user, status='paid'
    ).aggregate(total=models.Sum('total_amount'))['total'] or 0

    recent_reviews = Review.objects.filter(
        user=request.user
    ).select_related('product').order_by('-created_at')[:5]
    total_reviews = Review.objects.filter(user=request.user).count()

    recent_activity = []
    # Recent orders as activity
    for order in recent_orders[:3]:
        recent_activity.append({
            'type': 'order',
            'icon': 'bi-bag-check',
            'text': f'Order #{order.id} — Rs. {order.total_amount}',
            'status': order.get_status_display(),
            'status_class': {
                'pending': 'warning',
                'paid': 'success',
                'failed': 'danger',
                'delivered': 'info',
            }.get(order.status, 'secondary'),
            'time': order.created_at,
        })
    # Recent reviews as activity
    for review in recent_reviews[:2]:
        recent_activity.append({
            'type': 'review',
            'icon': 'bi-star',
            'text': f'Reviewed "{review.product.title}" — {review.get_rating_display()}',
            'time': review.created_at,
        })
    # Sort by time descending
    recent_activity.sort(key=lambda x: x['time'], reverse=True)

    # Order status breakdown
    order_status_counts = Order.objects.filter(user=request.user).values('status').annotate(
        count=models.Count('id')
    ).order_by('status')

    context = {
        'profile': user_profile,
        'recent_orders': recent_orders,
        'total_orders': total_orders,
        'paid_orders': paid_orders,
        'total_spent': total_spent,
        'recent_reviews': recent_reviews,
        'total_reviews': total_reviews,
        'recent_activity': recent_activity[:8],
        'order_status_counts': order_status_counts,
    }
    return render(request, 'dashboard.html', context)

@login_required
def checkout(request):
    cart_items = CartItem.objects.filter(user=request.user)
    if not cart_items:
        messages.error(request, 'Your cart is empty.')
        return redirect('store:cart')

    total = sum(item.total_price() for item in cart_items)
    initial_data = dict(request.session.get('checkout_shipping', {}))

    if not initial_data.get('full_name'):
        initial_data['full_name'] = request.user.get_full_name() or request.user.username
    if not initial_data.get('email'):
        initial_data['email'] = request.user.email or ''
    if not initial_data.get('country'):
        initial_data['country'] = 'India'

    if not initial_data.get('phone'):
        profile_phone = None
        user_profile = getattr(request.user, 'userprofile', None)
        if user_profile and user_profile.phone_number:
            profile_phone = user_profile.phone_number
        else:
            phone_profile = getattr(request.user, 'phone_profile', None)
            if phone_profile and phone_profile.phone_number:
                profile_phone = phone_profile.phone_number

        if profile_phone:
            initial_data['phone'] = profile_phone

    if request.method == 'POST':
        form = CheckoutShippingForm(request.POST)
        if form.is_valid():
            checkout_shipping = form.cleaned_data.copy()
            latitude = checkout_shipping.get('latitude')
            longitude = checkout_shipping.get('longitude')
            if isinstance(latitude, Decimal):
                checkout_shipping['latitude'] = str(latitude)
            if isinstance(longitude, Decimal):
                checkout_shipping['longitude'] = str(longitude)

            checkout_shipping['country'] = checkout_shipping.get('country') or 'India'
            request.session['checkout_shipping'] = checkout_shipping
            request.session['checkout_total'] = str(total)
            request.session['checkout_items'] = [
                {'product': item.product.id, 'quantity': item.quantity} for item in cart_items
            ]
            messages.success(request, 'Shipping details saved. Proceed to payment.')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('store:checkout')
        else:
            logger.warning('Checkout form invalid: %s', form.errors.as_json())
            for field, errors in form.errors.items():
                logger.warning('  Field %s: %s', field, ', '.join(errors))
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, 'Please correct shipping details.')
    else:
        form = CheckoutShippingForm(initial=initial_data)

    context = {
        'form': form,
        'total': total,
        'stripe_minimum_amount': get_stripe_minimum_amount(),
        'cart_items': cart_items,
        'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY,
    }
    return render(request, 'checkout.html', context)

@login_required
@require_http_methods(['POST'])
def save_current_location(request):
    """Save the user's current GPS location (from 'Use Current Location' button) to their profile."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
        latitude = payload.get('latitude')
        longitude = payload.get('longitude')

        if latitude is None or longitude is None:
            return JsonResponse({'success': False, 'error': 'Latitude and longitude are required.'}, status=400)

        lat = round(float(latitude), 6)
        lon = round(float(longitude), 6)
        logger.info('[save_current_location] User %s: lat=%s, lon=%s', request.user.id, lat, lon)

        # Reverse geocode via Nominatim
        nominatim_url = (
            f'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&addressdetails=1'
        )
        req = urllib_request.Request(
            nominatim_url,
            headers={'User-Agent': 'GroceryHub/1.0'}
        )
        with urllib_request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        display_name = data.get('display_name', '')
        address_data = data.get('address', {})
        house_number = address_data.get('house_number', '')
        road = address_data.get('road', '')
        suburb = address_data.get('suburb', '') or address_data.get('neighbourhood', '')
        city = address_data.get('city') or address_data.get('town') or address_data.get('village') or ''
        state_name = address_data.get('state') or ''
        postcode = address_data.get('postcode', '')
        country = address_data.get('country', 'India')

        # Build a clean, human-readable full address
        address_parts = []
        if house_number:
            address_parts.append(house_number)
        if road:
            address_parts.append(road)
        if suburb:
            address_parts.append(suburb)
        if city:
            address_parts.append(city)
        if state_name:
            address_parts.append(state_name)
        if postcode:
            address_parts.append(postcode)
        if country:
            address_parts.append(country)
        full_address = ', '.join(address_parts) if address_parts else display_name

        # Save to user profile
        profile = request.user.userprofile
        profile.current_address = full_address
        profile.latitude = lat
        profile.longitude = lon
        profile.city = city
        profile.postal_code = postcode
        profile.country = country
        profile.address_source = 'current_location'
        profile.save()

        return JsonResponse({
            'success': True,
            'address': full_address,
            'display_name': display_name,
            'city': city,
            'state': state_name,
            'postcode': postcode,
            'country': country,
            'latitude': str(lat),
            'longitude': str(lon),
        })
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid coordinates provided.'}, status=400)
    except Exception as exc:
        logger.error(f"[save_current_location] Error: {str(exc)}")
        return JsonResponse({'success': False, 'error': 'Unable to fetch location details. Please enter address manually.'}, status=500)


@login_required
@require_http_methods(['POST'])
def checkout_save_location(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
        latitude = payload.get('latitude')
        longitude = payload.get('longitude')
        accuracy = payload.get('accuracy')

        if latitude is None or longitude is None:
            return JsonResponse({'success': False, 'error': 'Latitude and longitude are required.'}, status=400)

        lat = round(float(latitude), 6)
        lon = round(float(longitude), 6)
        logger.info(
            '[checkout_save_location] Received GPS coordinates: lat=%s, lon=%s, accuracy=%s',
            lat, lon, accuracy,
        )
        nominatim_url = (
            f'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&addressdetails=1'
        )
        request_obj = urllib_request.Request(
            nominatim_url,
            headers={'User-Agent': 'GroceryHub/1.0'}
        )

        with urllib_request.urlopen(request_obj, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        display_name = data.get('display_name', '')
        address_data = data.get('address', {})
        city = address_data.get('city') or address_data.get('town') or address_data.get('village') or ''
        state_name = address_data.get('state') or address_data.get('region') or ''
        pincode = address_data.get('postcode', '')

        location_info = {
            'address_line1': display_name,
            'city': city,
            'pincode': pincode,
            'latitude': str(lat),
            'longitude': str(lon),
        }
        request.session['checkout_location'] = location_info
        checkout_shipping = request.session.get('checkout_shipping', {})
        checkout_shipping.update(location_info)
        request.session['checkout_shipping'] = checkout_shipping

        return JsonResponse({
            'success': True,
            'address': display_name,
            'city': city,
            'state_name': state_name,
            'pincode': pincode,
        })
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid coordinates provided.'}, status=400)
    except Exception as exc:
        logger.error(f"Location save failed: {str(exc)}")
        return JsonResponse({'success': False, 'error': 'Unable to fetch location details. Please enter address manually.'}, status=500)

@login_required
def create_session(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    # Get from session
    shipping_data = request.session.get('checkout_shipping', {})
    items_data = request.session.get('checkout_items', [])
    
    if not items_data:
        return JsonResponse({'error': 'No cart items'}, status=400)
    
    # Get cart_items
    cart_items = CartItem.objects.filter(user=request.user, product_id__in=[item['product'] for item in items_data])
    if len(cart_items) != len(items_data):
        return JsonResponse({'error': 'Cart mismatch'}, status=400)

    total = sum((item.total_price() for item in cart_items), Decimal('0.00')).quantize(Decimal('0.01'))
    stripe_minimum_amount = get_stripe_minimum_amount()
    if total < stripe_minimum_amount:
        return JsonResponse({
            'error': (
                f'Online payments require a minimum order total of Rs {stripe_minimum_amount}. '
                f'Your current total is Rs {total}. Please add more items to continue.'
            )
        }, status=400)
    
    # Stripe setup
    stripe_secret_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    if not stripe_secret_key:
        return JsonResponse({'error': 'Stripe not configured'}, status=500)
    
    import re
    if not re.match(r'^sk_(test|live)_[0-9a-zA-Z]{24,}$', stripe_secret_key):
        logger.error(f"Invalid Stripe key: {stripe_secret_key[:10]}...")
        return JsonResponse({'error': 'Invalid Stripe key'}, status=500)
    
    stripe.api_key = stripe_secret_key
    currency = getattr(settings, 'STRIPE_CURRENCY', 'inr')
    
    latitude = None
    longitude = None
    try:
        latitude = float(shipping_data.get('latitude')) if shipping_data.get('latitude') else None
        longitude = float(shipping_data.get('longitude')) if shipping_data.get('longitude') else None
    except (TypeError, ValueError):
        latitude = None
        longitude = None

    try:
        # Create order
        order = Order.objects.create(
            user=request.user,
            total_amount=total,
            address=shipping_data.get('address_line1', ''),
            latitude=latitude,
            longitude=longitude,
            address_line1=shipping_data.get('address_line1', ''),
            city=shipping_data.get('city', ''),
            state=shipping_data.get('state', ''),
            pincode=shipping_data.get('pincode', ''),
            phone=shipping_data.get('phone', ''),
        )

        OrderAddress.objects.create(
            order=order,
            full_name=shipping_data.get('full_name', request.user.get_full_name() or request.user.username),
            email=shipping_data.get('email', request.user.email or ''),
            phone=shipping_data.get('phone', ''),
            address_line1=shipping_data.get('address_line1', ''),
            address_line2=shipping_data.get('address_line2', ''),
            city=shipping_data.get('city', ''),
            state=shipping_data.get('state', ''),
            postal_code=shipping_data.get('pincode', ''),
            country=shipping_data.get('country', 'India'),
            delivery_instructions=shipping_data.get('delivery_instructions', ''),
            latitude=latitude,
            longitude=longitude,
        )
        
        # Create order items
        for item_data in items_data:
            cart_item = cart_items.get(product_id=item_data['product'])
            if cart_item.quantity != item_data['quantity']:
                raise ValueError('Quantity mismatch')
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                quantity=cart_item.quantity,
                price=cart_item.product.get_price(),
            )
        
        # Stripe session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': currency,
                        'product_data': {
                            'name': f'Order #{order.id} - GroceryHub',
                        },
                        'unit_amount': int(total * 100),

                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            success_url=request.build_absolute_uri(f'/checkout/success/{order.id}/'),
            cancel_url=request.build_absolute_uri('/checkout/cancel/'),
            metadata={
                'user_id': str(request.user.id),
                'order_id': str(order.id),
            },
        )
        
        order.stripe_session_id = session.id
        order.save()
        
        logger.info(f"Stripe session created for order {order.id}")
        
    except stripe.error.InvalidRequestError as e:
        # Handle Stripe errors such as amounts that are too small after conversion
        logger.error(f"Checkout error (Stripe InvalidRequest): {str(e)}")
        if 'order' in locals():
            order.delete()
        msg = str(e)
        if 'must convert to at least' in msg or 'total amount' in msg:
            return JsonResponse({
                'error': 'Order total is too small for Stripe payments. Please increase the order amount.'
            }, status=400)
        return JsonResponse({'error': 'Payment provider rejected the request.'}, status=400)
    except Exception as e:
        logger.error(f"Checkout error: {str(e)}")
        if 'order' in locals():
            order.delete()
        return JsonResponse({'error': 'Checkout failed: ' + str(e)}, status=500)
    
    return JsonResponse({'url': session.url})

def checkout_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status not in ('paid', 'confirmed'):
        messages.warning(request, 'Order payment is still processing.')

    # Notifications are triggered automatically via the signal in signals.py
    # when order status is set to 'confirmed'. No manual trigger needed here.

    notification_msg = ''
    if order.status == 'confirmed':
        notification_msg = (
            'Your order has been confirmed successfully. '
            'A confirmation email and SMS have been sent to your registered contact details.'
        )
        messages.success(request, notification_msg)

    ordered_product_ids = order.items.values_list('product_id', flat=True)
    recommended_products = Product.objects.filter(
        is_out_of_stock=False
    ).exclude(
        id__in=ordered_product_ids
    ).order_by('-created_at')[:8]
    shipping_address = getattr(order, 'shipping_address', None)
    order_items = order.items.select_related('product').all()
    context = {
        'order': order,
        'order_items': order_items,
        'shipping_address': shipping_address,
        'payment': None,
        'recommended_products': recommended_products,
        'notification_msg': notification_msg,
    }
    return render(request, 'payment/success.html', context)

def checkout_cancel(request):
    messages.error(request, 'Payment cancelled.')
    return render(request, 'payment/cancel.html')

def send_order_confirmation_email(order):
    """Send order confirmation email to the customer's registered email address."""
    shipping_address = getattr(order, 'shipping_address', None)
    customer_email = order.user.email
    if not customer_email and shipping_address:
        customer_email = shipping_address.email
    if not customer_email:
        logger.warning('No email address found for order %s (user %s)', order.id, order.user.id)
        return False

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

    order_items = order.items.select_related('product').all()

    subject = f'Order #{order.id} Confirmed - GroceryHub'
    html_message = render_to_string('emails/order_confirmation.html', {
        'order': order,
        'order_items': order_items,
        'shipping_address': shipping_address,
        'customer_name': customer_name,
        'customer_email': customer_email,
        'customer_phone': customer_phone,
    })
    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [customer_email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info('Order confirmation email sent for order %s to %s', order.id, customer_email)
        return True
    except Exception as exc:
        logger.warning('Failed to send order confirmation email for order %s: %s', order.id, exc)
        return False


def send_order_confirmation_sms(order):
    """Send order confirmation SMS to the customer's registered phone number."""
    shipping_address = getattr(order, 'shipping_address', None)
    customer_phone = ''
    if shipping_address and shipping_address.phone:
        customer_phone = shipping_address.phone
    else:
        user_profile = getattr(order.user, 'userprofile', None)
        if user_profile and user_profile.phone_number:
            customer_phone = user_profile.phone_number

    if not customer_phone:
        logger.warning('No phone number found for order %s (user %s)', order.id, order.user.id)
        return False

    customer_name = order.user.get_full_name() or order.user.username
    if shipping_address and shipping_address.full_name:
        customer_name = shipping_address.full_name

    message_text = (
        f"Hi {customer_name}! Your GroceryHub Order #{order.id} "
        f"(Rs. {order.total_amount}) has been confirmed. "
        f"We'll notify you when it's on its way. Thank you!"
    )

    try:
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_PHONE_NUMBER
        if not account_sid or not auth_token or not from_number:
            logger.warning('Twilio not configured, skipping SMS for order %s', order.id)
            return False

        client = Client(account_sid, auth_token)
        client.messages.create(
            body=message_text,
            from_=from_number,
            to=customer_phone,
        )
        logger.info('Order confirmation SMS sent for order %s to %s', order.id, customer_phone)
        return True
    except Exception as exc:
        logger.warning('Failed to send order confirmation SMS for order %s: %s', order.id, exc)
        return False


@csrf_exempt
def stripe_webhook(request):
    stripe_secret_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    if not stripe_secret_key:
        return JsonResponse({'error': 'Config error'}, status=500)
    
    stripe.api_key = stripe_secret_key
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
        )
    except ValueError:
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        try:
            order = Order.objects.select_related('user').get(stripe_session_id=session['id'])
            order.status = 'confirmed'
            order.save()
            CartItem.objects.filter(
                user=order.user,
                product_id__in=order.items.values_list('product_id', flat=True)
            ).delete()

            logger.info(f"Order {order.id} marked as confirmed (notifications will be sent via signal)")
        except Order.DoesNotExist:
            logger.error("Order not found for session")
    
    return JsonResponse({'status': 'success'})


def about(request):
    return render(request, 'about.html')


def contact(request):
    return render(request, 'contact.html')


# ---------- Category & Subcategory Product Pages ----------

def category_products(request, category_slug):
    """Display all products under a specific category. URL: /category/fruits/"""
    sync_products_for_query(CATEGORY_QUERIES.get(category_slug, category_slug), page=request.GET.get('page', 1), limit=24)
    category = get_object_or_404(Category, slug=category_slug, is_active=True)
    products = Product.objects.filter(
        category=category, is_out_of_stock=False
    ).select_related('category', 'subcategory')

    # Optional subcategory filter within this category page
    subcategory_slug = request.GET.get('subcategory')
    active_subcategory = None
    if subcategory_slug:
        active_subcategory = get_object_or_404(Subcategory, slug=subcategory_slug, category=category, is_active=True)
        products = products.filter(subcategory=active_subcategory)

    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Annotate subcategories with active product counts
    subcategories = Subcategory.objects.filter(category=category, is_active=True).annotate(
        active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
    ).order_by('sort_order', 'name')

    context = {
        'category': category,
        'subcategories': subcategories,
        'active_subcategory': active_subcategory,
        'products': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'breadcrumbs': [
            {'label': 'Home', 'url': '/'},
            {'label': category.name, 'url': None},
        ],
    }
    return render(request, 'products/category_products.html', context)


def subcategory_products(request, category_slug, subcategory_slug):
    """Display all products under a specific subcategory. URL: /category/fruits/apple/"""
    category = get_object_or_404(Category, slug=category_slug, is_active=True)
    subcategory = get_object_or_404(
        Subcategory.objects.select_related('category'),
        slug=subcategory_slug, category=category, is_active=True
    )
    products = Product.objects.filter(
        category=category, subcategory=subcategory, is_out_of_stock=False
    ).select_related('category', 'subcategory')

    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Annotate sibling subcategories with active product counts
    subcategories = Subcategory.objects.filter(category=category, is_active=True).annotate(
        active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
    ).order_by('sort_order', 'name')

    context = {
        'category': category,
        'subcategory': subcategory,
        'subcategories': subcategories,
        'products': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'breadcrumbs': [
            {'label': 'Home', 'url': '/'},
            {'label': category.name, 'url': f'/category/{category.slug}/'},
            {'label': subcategory.name, 'url': None},
        ],
    }
    return render(request, 'products/subcategory_products.html', context)


def subsubcategory_products(request, category_slug, subcategory_slug, subsubcategory_slug):
    """Display all products under a specific sub-subcategory. URL: /category/fruits/fresh-fruits/apple/"""
    from .models import SubSubCategory
    category = get_object_or_404(Category, slug=category_slug, is_active=True)
    subcategory = get_object_or_404(
        Subcategory.objects.select_related('category'),
        slug=subcategory_slug, category=category, is_active=True
    )
    subsubcategory = get_object_or_404(
        SubSubCategory.objects.select_related('subcategory__category'),
        slug=subsubcategory_slug, subcategory=subcategory, is_active=True
    )
    products = Product.objects.filter(
        subsubcategory=subsubcategory, is_out_of_stock=False
    ).select_related('category', 'subcategory', 'subsubcategory')

    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Annotate sibling sub-subcategories with active product counts
    subsubcategories = SubSubCategory.objects.filter(subcategory=subcategory, is_active=True).annotate(
        active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
    ).order_by('sort_order', 'name')

    context = {
        'category': category,
        'subcategory': subcategory,
        'subsubcategory': subsubcategory,
        'subsubcategories': subsubcategories,
        'products': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'breadcrumbs': [
            {'label': 'Home', 'url': '/'},
            {'label': category.name, 'url': f'/category/{category.slug}/'},
            {'label': subcategory.name, 'url': f'/category/{category.slug}/{subcategory.slug}/'},
            {'label': subsubcategory.name, 'url': None},
        ],
    }
    return render(request, 'products/subsubcategory_products.html', context)


@require_POST
def newsletter_subscribe(request):
    """
    AJAX endpoint for newsletter subscription.
    Validates email, prevents duplicates, saves to DB, and sends notification.
    Backend validation ensures empty/invalid values cannot be submitted even if frontend is bypassed.
    """
    import json

    # Strictly require application/json content type
    content_type = request.META.get('CONTENT_TYPE', '')
    if 'application/json' not in content_type and 'application/x-www-form-urlencoded' not in content_type:
        return JsonResponse({'success': False, 'message': 'Invalid content type.'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
        email = data.get('email', '').strip()
    except (json.JSONDecodeError, UnicodeDecodeError):
        email = request.POST.get('email', '').strip()

    # Backend validation — reject empty, whitespace-only, or missing email
    if not email:
        return JsonResponse({'success': False, 'message': 'Please enter your email address.'}, status=400)

    # Reject if email is just whitespace after stripping
    if len(email) == 0:
        return JsonResponse({'success': False, 'message': 'Please enter your email address.'}, status=400)

    # Validate email format using Django's built-in validator
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'}, status=400)

    # Additional regex validation for extra safety
    import re
    email_regex = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    if not email_regex.match(email):
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'}, status=400)

    # Reject if email is too long (defense against buffer overflow / long string attacks)
    if len(email) > 254:
        return JsonResponse({'success': False, 'message': 'Email address is too long.'}, status=400)

    # Check for duplicate (case-insensitive)
    if NewsletterSubscriber.objects.filter(email__iexact=email).exists():
        return JsonResponse({'success': False, 'message': 'This email is already subscribed.'}, status=409)

    # Save to database
    subscriber = NewsletterSubscriber.objects.create(email=email)

    # Send notification email asynchronously via Celery so the HTTP response returns immediately.
    # If Celery is not available, fall back to synchronous sending.
    try:
        from .tasks import send_newsletter_notification_task
        # Pass subscribed_at as ISO string for JSON serialization
        send_newsletter_notification_task.delay(
            subscriber.email,
            subscriber.subscribed_at.isoformat(),
        )
        logger.info('✓ Newsletter notification dispatched to Celery for: %s', email)
    except Exception as exc:
        # Fallback: send synchronously if Celery is not available
        logger.warning('Celery not available, sending newsletter notification synchronously: %s', exc)
        try:
            from services.email_service import send_newsletter_notification
            send_newsletter_notification(subscriber.email, subscriber.subscribed_at)
        except Exception as inner_exc:
            logger.exception('Failed to send newsletter notification for %s: %s', email, inner_exc)

    logger.info('✓ New newsletter subscriber: %s', email)
    return JsonResponse({'success': True, 'message': 'Thank you for subscribing to our newsletter.'})


def load_subcategories(request):
    """AJAX endpoint: return subcategories for a given category_id.
    Used in Django admin and product filtering."""
    category_id = request.GET.get('category_id')
    subcategories = Subcategory.objects.filter(category_id=category_id).values('id', 'name', 'slug')
    return JsonResponse(list(subcategories), safe=False)

