import logging

from django.db import transaction
from django.db.models import F

from configurator.models import BraceletItem

from .models import PaymentTransaction, TransactionStatus
from .tasks import send_order_confirmation_email

logger = logging.getLogger(__name__)


@transaction.atomic
def finalize_paid_order(order, gateway, reference, amount, raw_response=None):
    """Mark an order paid, log the transaction, decrement stock, and enqueue
    the confirmation email. Shared by all three gateways' success paths so
    this logic exists exactly once."""
    order.gateway = gateway
    order.mark_as_paid(payment_reference=reference)
    order.save(update_fields=['gateway'])

    PaymentTransaction.objects.create(
        order=order,
        gateway=gateway,
        gateway_id=reference,
        amount=amount,
        currency=order.currency,
        status=TransactionStatus.SUCCEEDED,
        raw_response=raw_response or {},
    )

    for order_item in order.items.select_related('bracelet_configuration'):
        configuration = order_item.bracelet_configuration
        if configuration is None:
            continue
        for config_item in configuration.items.select_related('item'):
            updated = BraceletItem.objects.filter(
                pk=config_item.item_id, stock__gte=1
            ).update(stock=F('stock') - 1)
            if not updated:
                logger.warning(
                    "Order %s paid but BraceletItem %s had no stock left to decrement "
                    "(oversold) — order remains PAID, needs manual follow-up.",
                    order.order_number, config_item.item_id,
                )

    send_order_confirmation_email.delay(order.id)

    return order
