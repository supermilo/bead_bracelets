from django.contrib import admin
from django.utils.html import format_html

from .models import (
    BraceletBase,
    BraceletConfiguration,
    BraceletConfigurationItem,
    BraceletItem,
    ItemCategory,
    LeatherBraceletBase,
)


@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'display_order')
    list_editable = ('display_order',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(BraceletItem)
class BraceletItemAdmin(admin.ModelAdmin):
    list_display = (
        'thumbnail', 'name', 'category', 'material', 'price',
        'stock', 'slot_width', 'is_active',
    )
    list_display_links = ('thumbnail', 'name')
    list_editable = ('price', 'stock', 'is_active')
    list_filter = ('category', 'is_active', 'material')
    search_fields = ('name', 'material')
    readonly_fields = ('image_preview',)
    fields = (
        'category', 'name', 'material', 'price', 'image', 'image_preview',
        'stock', 'is_active', 'slot_width',
    )

    @admin.display(description='Preview')
    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:40px;width:40px;object-fit:cover;border-radius:4px;" />',
                obj.image.url,
            )
        return ''

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:200px;max-width:200px;object-fit:contain;" />',
                obj.image.url,
            )
        return '(no image)'


@admin.register(BraceletBase)
class BraceletBaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_slots', 'base_price')
    search_fields = ('name',)


@admin.register(LeatherBraceletBase)
class LeatherBraceletBaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'size', 'base_price', 'slot_count')
    list_filter = ('size',)
    search_fields = ('name',)


class BraceletConfigurationItemInline(admin.TabularInline):
    model = BraceletConfigurationItem
    extra = 0
    ordering = ('position',)
    autocomplete_fields = ('item',)


@admin.register(BraceletConfiguration)
class BraceletConfigurationAdmin(admin.ModelAdmin):
    list_display = ('id', 'base', 'session_key', 'created_at', 'is_finalized')
    list_filter = ('is_finalized', 'base')
    search_fields = ('session_key',)
    inlines = [BraceletConfigurationItemInline]


@admin.register(BraceletConfigurationItem)
class BraceletConfigurationItemAdmin(admin.ModelAdmin):
    list_display = ('configuration', 'position', 'item')
    list_filter = ('configuration',)
    ordering = ('configuration', 'position')
