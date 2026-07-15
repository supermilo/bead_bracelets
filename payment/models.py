from django.db import models

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
