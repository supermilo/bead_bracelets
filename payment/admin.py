from django.contrib import admin

from .models import CurrencyExchangeRate, PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('order', 'gateway', 'gateway_id', 'amount', 'status', 'created_at')
    list_filter = ('gateway', 'status')
    search_fields = ('gateway_id', 'order__order_number')
    readonly_fields = ('order', 'gateway', 'gateway_id', 'amount', 'currency', 'status', 'raw_response', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(CurrencyExchangeRate)
class CurrencyExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('currency_code', 'symbol', 'rate', 'created_at')
    list_filter = ('currency_code',)
    readonly_fields = ('currency_code', 'symbol', 'rate', 'created_at')

    def has_add_permission(self, request):
        return False
