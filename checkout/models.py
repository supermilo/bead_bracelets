import uuid

from django.db import models
from django.utils import timezone

from configurator.models import BraceletConfiguration


class GatewayChoice(models.TextChoices):
    STRIPE = 'stripe', 'Stripe'
    PAYPAL = 'paypal', 'PayPal'
    MERCADOPAGO = 'mercadopago', 'MercadoPago'


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PAID = 'paid', 'Paid'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'


class Order(models.Model):
    """A guest checkout order. No user FK — this project has no login system
    and the whole bracelet-building flow is anonymous/session-based."""

    order_number = models.CharField(max_length=32, unique=True, editable=False, blank=True)
    session_key = models.CharField(max_length=40)

    customer_name = models.CharField(max_length=150)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, blank=True)

    gateway = models.CharField(max_length=20, choices=GatewayChoice.choices, blank=True, default='')
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)

    total = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    payment_reference = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'Order {self.order_number} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f'ORD-{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    def mark_as_paid(self, payment_reference=None):
        self.status = OrderStatus.PAID
        self.paid_at = timezone.now()
        if payment_reference:
            self.payment_reference = payment_reference
        self.save(update_fields=['status', 'paid_at', 'payment_reference'])


class OrderItem(models.Model):
    """A single purchasable line within an Order.

    Only one purchasable type exists today (a finalized BraceletConfiguration),
    so a plain nullable FK is used instead of a generic item_type/item_id
    scheme. To add a second purchasable type later: add another nullable FK
    here (e.g. `gift_card`), and extend `purchasable` below — no rewrite of
    Order/OrderItem needed.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    bracelet_configuration = models.ForeignKey(
        BraceletConfiguration,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='order_items',
    )

    item_title = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f'{self.item_title} (x{self.quantity}) - ${self.total_price}'

    @property
    def purchasable(self):
        return self.bracelet_configuration
