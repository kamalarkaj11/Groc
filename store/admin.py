from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import (
    Profile, PhoneOTP, Review, UserProfile, Category,
    Subcategory, SubSubCategory, Product, CartItem, Order, OrderItem, OTP
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
    list_display = ['title', 'category', 'subcategory', 'subsubcategory', 'price', 'discount_price', 'discount_percentage', 'is_out_of_stock', 'image_preview']
    list_filter = ['category', 'subcategory', 'subsubcategory', 'is_out_of_stock']
    list_select_related = ['category', 'subcategory']
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ['title', 'description']
    autocomplete_fields = ['category', 'subcategory', 'subsubcategory']
    readonly_fields = ['discount_percentage']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="60" height="60" style="object-fit:cover;border-radius:6px;" />', obj.image.url)
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
    list_display = ['user', 'age', 'state']
    list_filter = ['state']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    list_select_related = ['product', 'user']


admin.site.register(CartItem)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OTP)
admin.site.register(Profile)
admin.site.register(PhoneOTP)


# Inline profile in User admin
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline, )


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
