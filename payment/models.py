from django.db import models
from django.utils import timezone

from checkout.models import GatewayChoice, Order


class TransactionStatus(models.TextChoices):
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'
    PENDING = 'pending', 'Pending'


class PaymentTransaction(models.Model):
    """Audit log of a single gateway charge attempt. Not to be confused with
    Stripe's own "PaymentIntent" object — this just logs what each gateway
    told us, for every gateway."""

    Status = TransactionStatus

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='transactions')
    gateway = models.CharField(max_length=20, choices=GatewayChoice.choices)
    gateway_id = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=TransactionStatus.choices)
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.gateway} {self.gateway_id} ({self.status})'


class CurrencyExchangeRate(models.Model):
    """Daily snapshot of a currency's exchange rate relative to USD, fetched
    from open.er-api.com by payment.tasks.update_currency_rates. Rows are
    appended, never overwritten — real money changes hands based on these
    rates, so keeping one row per currency per day preserves a reconstructable
    history instead of losing yesterday's rate to an in-place update."""

    currency_code = models.CharField(max_length=3)
    symbol = models.CharField(max_length=5)
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    created_at = models.DateField(default=timezone.localdate)

    class Meta:
        unique_together = ('currency_code', 'created_at')
        ordering = ('-created_at', 'currency_code')

    def __str__(self):
        return f'{self.currency_code} = {self.rate} USD ({self.created_at})'
