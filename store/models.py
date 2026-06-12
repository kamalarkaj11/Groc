from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='phone_profile')
    # Registered phone numbers are stored in E.164 format and must be unique.
    phone_number = models.CharField(max_length=15, unique=True)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.phone_number})"


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
    # Add all 28 states + 8 UTs
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
    MEGHALAYA = 'ML', 'Meghalaya'
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
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    age = models.PositiveIntegerField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=False)
    address = models.TextField(blank=True)
    state = models.CharField(max_length=2, choices=IndianState.choices, blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    is_latest = models.BooleanField(default=True)  # Only latest valid

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


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.userprofile.save()


@receiver(post_save, sender=User)
def generate_initial_otp(sender, instance, created, **kwargs):
    """Generate OTP for new users if not active."""
    if created and not instance.is_active:
        from .signals import create_otp  # Forward ref
        create_otp(instance)

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    description = models.TextField(blank=True, help_text="Brief description for SEO and display.")
    icon = models.CharField(
        max_length=50, blank=True,
        help_text='Bootstrap Icons class, e.g. "bi-apple" or "bi-cup-straw".'
    )
    is_active = models.BooleanField(default=True, help_text="Inactive categories are hidden from the storefront.")
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first.")

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['is_active', 'sort_order']),
        ]

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
        """Return the number of in-stock products in this category."""
        return self.products.filter(is_out_of_stock=False).count()


class Subcategory(models.Model):
    """Subcategory under a Category. E.g. Fruits -> Apple, Banana."""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='subcategories'
    )
    image = models.ImageField(upload_to='subcategories/', blank=True, null=True)
    description = models.TextField(blank=True, help_text="Brief description for SEO and display.")
    icon = models.CharField(
        max_length=50, blank=True,
        help_text='Bootstrap Icons class, e.g. "bi-apple" or "bi-cup-straw".'
    )
    is_active = models.BooleanField(default=True, help_text="Inactive subcategories are hidden from the storefront.")
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first.")

    class Meta:
        verbose_name_plural = 'subcategories'
        ordering = ['sort_order', 'name']
        # Prevent duplicate subcategory names within the same category
        unique_together = ('name', 'category')
        indexes = [
            models.Index(fields=['is_active', 'sort_order']),
        ]

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

    def product_count(self):
        """Return the number of in-stock products in this subcategory."""
        return self.products.filter(is_out_of_stock=False).count()

    def clean(self):
        """Validate that subcategory name is unique within its category."""
        from django.core.exceptions import ValidationError
        qs = Subcategory.objects.filter(name=self.name, category=self.category)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                f'Subcategory "{self.name}" already exists under "{self.category.name}".'
            )


class SubSubCategory(models.Model):
    """Sub-subcategory under a Subcategory. E.g., Fruits > Fresh Fruits > Apple, Mango."""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    subcategory = models.ForeignKey(
        Subcategory, on_delete=models.CASCADE, related_name='subsubcategories'
    )
    image = models.ImageField(upload_to='subsubcategories/', blank=True, null=True)
    description = models.TextField(blank=True, help_text="Brief description for SEO and display.")
    icon = models.CharField(
        max_length=50, blank=True,
        help_text='Bootstrap Icons class, e.g. "bi-apple" or "bi-cup-straw".'
    )
    is_active = models.BooleanField(default=True, help_text="Inactive sub-subcategories are hidden from the storefront.")
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first.")

    class Meta:
        verbose_name_plural = 'sub-subcategories'
        ordering = ['sort_order', 'name']
        unique_together = ('name', 'subcategory')
        indexes = [
            models.Index(fields=['is_active', 'sort_order']),
        ]

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

    def product_count(self):
        """Return the number of in-stock products in this sub-subcategory."""
        return self.products.filter(is_out_of_stock=False).count()

    def clean(self):
        """Validate that sub-subcategory name is unique within its subcategory."""
        from django.core.exceptions import ValidationError
        qs = SubSubCategory.objects.filter(name=self.name, subcategory=self.subcategory)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                f'Sub-subcategory "{self.name}" already exists under "{self.subcategory.name}".'
            )


class Product(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to='products/')
    external_image_url = models.URLField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    subcategory = models.ForeignKey(
        Subcategory, on_delete=models.CASCADE, related_name='products',
        null=True, blank=True
    )
    subsubcategory = models.ForeignKey(
        'SubSubCategory', on_delete=models.SET_NULL, related_name='products',
        null=True, blank=True
    )
    weight = models.CharField(max_length=50, blank=True, help_text="e.g. 500g, 1kg")
    origin = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    nutrition_info = models.JSONField(default=dict, blank=True, help_text="e.g. {'calories': 85, 'protein': 2.5}")
    highlights = models.JSONField(default=list, blank=True, help_text="e.g. ['100% Fresh', 'Quality Guaranteed']")
    is_out_of_stock = models.BooleanField(default=False)
    availability = models.CharField(max_length=120, blank=True)
    api_source = models.CharField(max_length=50, blank=True)
    api_product_id = models.CharField(max_length=255, blank=True, db_index=True)
    api_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    api_review_count = models.PositiveIntegerField(default=0)
    api_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['api_source', 'api_product_id']),
        ]

    def save(self, *args, **kwargs):
        """Auto-generate slug from title if not provided."""
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
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('delivered', 'Delivered'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Shipping and location fields
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    address_line1 = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, choices=IndianState.choices, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} - {self.user.username}"

class OrderAddress(models.Model):
    order = models.OneToOneField('Order', on_delete=models.CASCADE, related_name='shipping_address')
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

