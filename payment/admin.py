from django.contrib import admin

from .models import PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('order', 'gateway', 'gateway_id', 'amount', 'status', 'created_at')
    list_filter = ('gateway', 'status')
    search_fields = ('gateway_id', 'order__order_number')
    readonly_fields = ('order', 'gateway', 'gateway_id', 'amount', 'currency', 'status', 'raw_response', 'created_at')

    def has_add_permission(self, request):
        return False
