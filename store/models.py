from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

class Profile(models.Model):
    VERIFICATION_METHOD_CHOICES = [
        ('email', 'Email Address'),
        ('phone', 'Phone Number'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='phone_profile')
    phone_number = models.CharField(max_length=15, unique=True)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    verification_method = models.CharField(
        max_length=10,
        choices=VERIFICATION_METHOD_CHOICES,
        default='email',
        help_text="Which contact method was chosen for signup verification.",
    )
    verified_at = models.DateTimeField(null=True, blank=True, help_text="When the selected verification was completed.")
    profile_verified_at = models.DateTimeField(null=True, blank=True, help_text="When the user completed profile-level verification.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.phone_number})"

    @property
    def is_selected_method_verified(self):
        """Check if the verification method chosen during registration is verified."""
        if self.verification_method == 'phone':
            return self.is_phone_verified
        return self.is_email_verified


class PhoneOTP(models.Model):
    phone = models.CharField(max_length=15)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP {self.otp} for {self.phone}"

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)

    @property
    def can_resend(self):
        return timezone.now() > self.created_at + timedelta(seconds=30)


class IndianState(models.TextChoices):
    ANDHRA_PRADESH = 'AP', 'Andhra Pradesh'
    TELANGANA = 'TS', 'Telangana'
    MAHARASHTRA = 'MH', 'Maharashtra'
    ANDAMAN_NICOBAR = 'AN', 'Andaman & Nicobar'
    ARUNACHAL_PRADESH = 'AR', 'Arunachal Pradesh'
    ASSAM = 'AS', 'Assam'
    BIHAR = 'BR', 'Bihar'
    CHANDIGARH = 'CH', 'Chandigarh'
    CHHATTISGARH = 'CT', 'Chhattisgarh'
    DADRA_NAGAR_HAVELI_DAMAN_DIU = 'DN', 'Dadra & Nagar Haveli and Daman & Diu'
    DELHI = 'DL', 'Delhi'
    GOA = 'GA', 'Goa'
    GUJARAT = 'GJ', 'Gujarat'
    HARYANA = 'HR', 'Haryana'
    HIMACHAL_PRADESH = 'HP', 'Himachal Pradesh'
    JAMMU_KASHMIR = 'JK', 'Jammu & Kashmir'
    JHARKHAND = 'JH', 'Jharkhand'
    KARNATAKA = 'KA', 'Karnataka'
    KERAL = 'KL', 'Kerala'
    LADAKH = 'LA', 'Ladakh'
    MADHYA_PRADESH = 'MP', 'Madhya Pradesh'
    MANIPUR = 'MN', 'Manipur'
    MEGHALAYA = 'MG', 'Meghalaya'
    MIZORAM = 'MZ', 'Mizoram'
    NAGALAND = 'NL', 'Nagaland'
    ODISHA = 'OR', 'Odisha'
    PUDUCHERRY = 'PY', 'Puducherry'
    PUNJAB = 'PB', 'Punjab'
    RAJASTHAN = 'RJ', 'Rajasthan'
    SIKKIM = 'SK', 'Sikkim'
    TAMIL_NADU = 'TN', 'Tamil Nadu'
    TRIPURA = 'TR', 'Tripura'
    UTTAR_PRADESH = 'UP', 'Uttar Pradesh'
    UTTARAKHAND = 'UK', 'Uttarakhand'
    WEST_BENGAL = 'WB', 'West Bengal'


class UserProfile(models.Model):
    ADDRESS_SOURCE_CHOICES = [
        ('manual', 'Manual Entry'),
        ('current_location', 'Current Location'),
    ]

    ACCOUNT_STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='userprofile')
    age = models.PositiveIntegerField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True, unique=True)
    address = models.TextField(blank=True)
    state = models.CharField(max_length=2, choices=IndianState.choices, blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    account_status = models.CharField(max_length=10, choices=ACCOUNT_STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    current_address = models.TextField(blank=True, help_text="Full address from current location")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=64, default='India', blank=True)
    address_source = models.CharField(
        max_length=20, choices=ADDRESS_SOURCE_CHOICES, default='manual', blank=True
    )

    class Meta:
        indexes = [
            models.Index(fields=['account_status']),
        ]

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def save(self, *args, **kwargs):
        if not self.phone_number:
            self.phone_number = None
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def display_name(self):
        full = self.user.get_full_name()
        return full if full else self.user.username


class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    is_latest = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP {self.otp} for {self.user.username}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired and self.attempts < self.max_attempts and self.is_latest


# ============================================================
# Login Activity Tracking Model
# ============================================================

class LoginActivity(models.Model):
    """Tracks all successful login activities for security monitoring."""
    
    LOGIN_METHOD_CHOICES = [
        ('password', 'Email/Password'),
        ('otp', 'Phone OTP'),
        ('google', 'Google OAuth'),
        ('facebook', 'Facebook'),
        ('twitter', 'Twitter'),
        ('github', 'GitHub'),
        ('other', 'Other'),
    ]
    
    DEVICE_TYPE_CHOICES = [
        ('desktop', 'Desktop'),
        ('mobile', 'Mobile'),
        ('tablet', 'Tablet'),
        ('unknown', 'Unknown'),
    ]
    
    SECURITY_STATUS_CHOICES = [
        ('success', 'Successful Login'),
        ('new_device', 'New Device Login'),
        ('new_browser', 'New Browser Login'),
        ('new_location', 'New Location Login'),
        ('suspicious', 'Suspicious Login'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='login_activities')
    login_date = models.DateField(help_text="Date of login")
    login_time = models.TimeField(help_text="Time of login (user's local timezone)")
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES, default='unknown')
    browser = models.CharField(max_length=100, blank=True, help_text="Browser name and version")
    operating_system = models.CharField(max_length=100, blank=True, help_text="Operating system")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, help_text="City from IP geolocation")
    state = models.CharField(max_length=100, blank=True, help_text="State from IP geolocation")
    country = models.CharField(max_length=100, blank=True, help_text="Country from IP geolocation")
    login_method = models.CharField(max_length=20, choices=LOGIN_METHOD_CHOICES, default='password')
    security_status = models.CharField(max_length=20, choices=SECURITY_STATUS_CHOICES, default='success')
    is_new_device = models.BooleanField(default=False, help_text="First time login from this device")
    is_new_browser = models.BooleanField(default=False, help_text="First time login from this browser")
    is_new_location = models.BooleanField(default=False, help_text="First time login from this city/country")
    email_sent = models.BooleanField(default=False, help_text="Whether login alert email was sent")
    sms_sent = models.BooleanField(default=False, help_text="Whether login alert SMS was sent")
    email_error = models.TextField(blank=True, help_text="Error message if email sending failed")
    sms_error = models.TextField(blank=True, help_text="Error message if SMS sending failed")
    user_agent = models.TextField(blank=True, help_text="Full User-Agent string")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'country', 'city']),
            models.Index(fields=['is_new_device', 'is_new_browser', 'is_new_location']),
            models.Index(fields=['email_sent', 'sms_sent']),
        ]
    
    def __str__(self):
        username = self.user.username if self.user else 'Deleted User'
        return f"Login by {username} on {self.login_date} at {self.login_time} from {self.city or self.country or 'Unknown'}"
    
    @property
    def location_display(self):
        """Return formatted location string."""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.state:
            parts.append(self.state)
        if self.country:
            parts.append(self.country)
        return ', '.join(parts) if parts else 'Unknown Location'
    
    @property
    def is_fully_delivered(self):
        """Check if both email and SMS were sent successfully (if applicable)."""
        return self.email_sent and self.sms_sent
    
    @property
    def has_any_error(self):
        """Check if there were any delivery errors."""
        return bool(self.email_error or self.sms_error)


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['sort_order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def product_count(self):
        return self.products.filter(is_out_of_stock=False).count()


class Subcategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories')
    image = models.ImageField(upload_to='subcategories/', blank=True, null=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'subcategories'
        ordering = ['sort_order', 'name']
        unique_together = ('name', 'category')

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Subcategory.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.name} → {self.name}"


class SubSubCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    subcategory = models.ForeignKey(Subcategory, on_delete=models.CASCADE, related_name='subsubcategories')
    image = models.ImageField(upload_to='subsubcategories/', blank=True, null=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'sub-subcategories'
        ordering = ['sort_order', 'name']
        unique_together = ('name', 'subcategory')

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while SubSubCategory.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subcategory.category.name} → {self.subcategory.name} → {self.name}"


class Product(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to='products/')
    external_image_url = models.URLField(blank=True)
    product_video = models.FileField(upload_to='products/videos/', blank=True, null=True)
    external_video_url = models.URLField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    subcategory = models.ForeignKey(Subcategory, on_delete=models.CASCADE, related_name='products', null=True, blank=True)
    subsubcategory = models.ForeignKey('SubSubCategory', on_delete=models.SET_NULL, related_name='products', null=True, blank=True)
    weight = models.CharField(max_length=50, blank=True)
    origin = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    nutrition_info = models.JSONField(default=dict, blank=True)
    highlights = models.JSONField(default=list, blank=True)
    is_out_of_stock = models.BooleanField(default=False)
    availability = models.CharField(max_length=120, blank=True)
    api_source = models.CharField(max_length=50, blank=True)
    api_product_id = models.CharField(max_length=255, blank=True, db_index=True)
    api_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    api_review_count = models.PositiveIntegerField(default=0)
    api_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['api_source', 'api_product_id'])]

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_price(self):
        return self.discount_price or self.price

    @property
    def discount_percentage(self):
        if self.discount_price and self.discount_price < self.price:
            return round(((self.price - self.discount_price) / self.price) * 100)
        return 0

    def __str__(self):
        return self.title


class Review(models.Model):
    RATING_CHOICES = [
        (1, '★☆☆☆☆'),
        (2, '★★☆☆☆'),
        (3, '★★★☆☆'),
        (4, '★★★★☆'),
        (5, '★★★★★'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=RATING_CHOICES, default=5)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.get_rating_display()} - {self.product.title}"


class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('flat', 'Flat Amount'),
        ('percent', 'Percentage'),
    ]

    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='flat')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def is_valid(self, subtotal=0):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        if subtotal < self.min_order_amount:
            return False
        return True

    def calculate_discount(self, subtotal):
        if self.discount_type == 'percent':
            return min((subtotal * self.discount_value / Decimal('100')).quantize(Decimal('0.01')), subtotal)
        return min(self.discount_value, subtotal)


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.product.title}"

    def total_price(self):
        return self.product.get_price() * self.quantity


class Order(models.Model):
    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('packed', 'Packed'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out For Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
        ('failed', 'Failed'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('stripe', 'Stripe (Card)'),
        ('cod', 'Cash on Delivery'),
        ('razorpay', 'Razorpay'),
        ('phonepe', 'PhonePe'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='stripe')
    transaction_id = models.CharField(max_length=255, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    coupon_code = models.CharField(max_length=20, blank=True)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    address_line1 = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, choices=IndianState.choices, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    delivery_notes = models.TextField(blank=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    email_sent = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)
    notification_sent = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['order_id']),
        ]

    def save(self, *args, **kwargs):
        if not self.order_id:
            last_order = Order.objects.order_by('-id').first()
            next_id = (last_order.id + 1) if last_order else 1
            self.order_id = f"GH{next_id:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_id or self.id} - {self.user.username}"


class OrderAddress(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='shipping_address')
    full_name = models.CharField(max_length=128)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    address_line1 = models.TextField(blank=True)
    address_line2 = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, choices=IndianState.choices, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=64, default='India', blank=True)
    delivery_instructions = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Order Address'
        verbose_name_plural = 'Order Addresses'

    def __str__(self):
        return f"Delivery address for order {self.order.id}"

    @property
    def formatted(self):
        lines = [self.full_name]
        if self.address_line1:
            lines.append(self.address_line1)
        if self.address_line2:
            lines.append(self.address_line2)
        city_line = []
        if self.city:
            city_line.append(self.city)
        if self.state:
            city_line.append(self.get_state_display())
        if city_line:
            lines.append(', '.join(city_line))
        if self.postal_code:
            lines.append(self.postal_code)
        if self.country:
            lines.append(self.country)
        return '\n'.join(lines)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product.title} x{self.quantity}"


class InvoiceHistory(models.Model):
    INVOICE_TYPE_CHOICES = [
        ('original', 'Original'),
        ('regenerated', 'Regenerated'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='invoice_history')
    invoice_number = models.CharField(max_length=50)
    invoice_type = models.CharField(max_length=20, choices=INVOICE_TYPE_CHOICES, default='original')
    generated_by = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Invoice History'
        verbose_name_plural = 'Invoice Histories'
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice {self.invoice_number} - Order {self.order.order_id}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_status_changes')
    changed_by_name = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Order Status History'
        verbose_name_plural = 'Order Status Histories'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order.order_id or self.order.id}: {self.previous_status} → {self.new_status}"


class NotificationLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='notification_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_logs')
    email_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('skipped', 'Skipped')],
        default='pending',
    )
    sms_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('skipped', 'Skipped')],
        default='pending',
    )
    email_sent_at = models.DateTimeField(null=True, blank=True)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    email_error_message = models.TextField(blank=True)
    sms_error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification Log'
        verbose_name_plural = 'Notification Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification #{self.id} - Order #{self.order_id}"


class OrderTracking(models.Model):
    TRACKING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('packed', 'Packed'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out For Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='tracking')
    status = models.CharField(max_length=20, choices=TRACKING_STATUS_CHOICES, default='pending')
    tracking_number = models.CharField(max_length=100, blank=True)
    delivery_partner = models.CharField(max_length=100, blank=True)
    current_location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Order Tracking'
        verbose_name_plural = 'Order Tracking'
        indexes = [models.Index(fields=['status']), models.Index(fields=['tracking_number'])]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._previous_status = self.status

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = OrderTracking.objects.get(pk=self.pk)
                self._previous_status = old.status
            except OrderTracking.DoesNotExist:
                self._previous_status = self.status
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Tracking for Order #{self.order_id} - {self.get_status_display()}"


class OrderTrackingHistory(models.Model):
    tracking = models.ForeignKey(OrderTracking, on_delete=models.CASCADE, related_name='history')
    status = models.CharField(max_length=20, choices=OrderTracking.TRACKING_STATUS_CHOICES)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Order Tracking History'
        verbose_name_plural = 'Order Tracking Histories'
        ordering = ['created_at']

    def __str__(self):
        return f"#{self.tracking.order_id} - {self.get_status_display()} @ {self.created_at.strftime('%d %b %Y %I:%M %p')}"


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('auth', 'Authentication'),
        ('order', 'Order'),
        ('profile', 'Profile'),
        ('system', 'System'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES, default='system')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'is_read', '-created_at'])]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title} - {self.user.username}"


class SavedAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_addresses')
    label = models.CharField(max_length=64, blank=True)
    full_address = models.TextField(blank=True)
    house_number = models.CharField(max_length=100, blank=True)
    street = models.CharField(max_length=255, blank=True)
    area = models.CharField(max_length=255, blank=True)
    locality = models.CharField(max_length=255, blank=True)
    village = models.CharField(max_length=255, blank=True)
    town = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    district = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=255, default='India', blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    place_id = models.CharField(max_length=100, blank=True)
    bounding_box = models.CharField(max_length=255, blank=True)
    display_name = models.TextField(blank=True)
    osm_type = models.CharField(max_length=20, blank=True)
    osm_id = models.CharField(max_length=50, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        verbose_name = 'Saved Address'
        verbose_name_plural = 'Saved Addresses'

    def __str__(self):
        return f"{self.label or 'Address'} - {self.full_address[:60]}"


class ContactMessage(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('read', 'Read'),
        ('replied', 'Replied'),
    ]

    name = models.CharField(max_length=100, verbose_name='Full Name')
    email = models.EmailField(verbose_name='Email Address')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Phone Number')
    subject = models.CharField(max_length=200, verbose_name='Subject')
    message = models.TextField(verbose_name='Message')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new', verbose_name='Status')
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name='IP Address')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submitted At')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Contact Message'
        verbose_name_plural = 'Contact Messages'

    def __str__(self):
        return f"{self.name} - {self.subject}"


class Quotation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved / Priced'),
        ('rejected', 'Rejected'),
        ('ordered', 'Ordered'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quotations')
    quotation_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    full_name = models.CharField(max_length=128, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    address_line1 = models.TextField(blank=True)
    address_line2 = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, choices=IndianState.choices, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    delivery_notes = models.TextField(blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    converted_order = models.OneToOneField('Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='source_quotation')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.quotation_id:
            last_quotation = Quotation.objects.order_by('-id').first()
            next_id = (last_quotation.id + 1) if last_quotation else 1
            self.quotation_id = f"QT{next_id:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Quotation {self.quotation_id or self.id} - {self.user.username}"


class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.title} x {self.quantity} in {self.quotation.quotation_id}"

    def total_price(self):
        return self.unit_price * self.quantity


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Newsletter Subscriber'
        verbose_name_plural = 'Newsletter Subscribers'
        ordering = ['-subscribed_at']

    def __str__(self):
        return self.email


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'userprofile'):
        instance.userprofile.save()


@receiver(post_save, sender=Profile)
def sync_profile_phone_to_user_profile(sender, instance, **kwargs):
    """Automatically sync Profile.phone_number → UserProfile.phone_number."""
    try:
        user_profile = UserProfile.objects.get(user=instance.user)
        if instance.phone_number and instance.phone_number != 'pending':
            if user_profile.phone_number != instance.phone_number:
                user_profile.phone_number = instance.phone_number
                user_profile.save(update_fields=['phone_number'])
    except UserProfile.DoesNotExist:
        pass


@receiver(post_save, sender=User)
def generate_initial_otp(sender, instance, created, **kwargs):
    """Generate OTP for new users if not active."""
    if created and not instance.is_active:
        from .signals import create_otp
        create_otp(instance)