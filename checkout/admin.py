from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ('bracelet_configuration',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer_email', 'status', 'gateway', 'total', 'created_at')
    list_filter = ('status', 'gateway')
    search_fields = ('order_number', 'customer_email', 'customer_name')
    readonly_fields = ('order_number', 'created_at', 'updated_at', 'paid_at')
    inlines = [OrderItemInline]
