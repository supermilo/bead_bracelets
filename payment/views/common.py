from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from checkout.models import GatewayChoice, Order, OrderStatus


def choose_gateway(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)
    return render(request, 'payment/choose_gateway.html', {'order': order})


def payment_failed(request, order_number):
    """Landing page for a cancelled/failed payment — reached when a customer
    cancels on a gateway's hosted checkout page (e.g. MercadoPago's
    back_urls.failure) or a payment otherwise doesn't go through. The order
    itself is untouched (still PENDING), so "Try again" just goes back to
    choose_gateway."""
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, 'payment/payment_failed.html', {'order': order})


@require_POST
def process_payment(request, order_number):
    """The unified dispatch view: picks a gateway and hands off to its
    gateway-specific checkout view. It does not contain any gateway's
    actual charge logic — that lives in stripe.py/paypal.py/mercadopago.py."""
    order = get_object_or_404(Order, order_number=order_number, status=OrderStatus.PENDING)

    gateway = request.POST.get('gateway')
    if gateway not in GatewayChoice.values:
        return render(
            request, 'payment/choose_gateway.html',
            {'order': order, 'error': 'Please choose a valid payment method.'},
            status=400,
        )

    order.gateway = gateway
    order.save(update_fields=['gateway'])

    if gateway == GatewayChoice.STRIPE:
        return redirect('payment:stripe_checkout', order_number=order.order_number)
    elif gateway == GatewayChoice.PAYPAL:
        return redirect('payment:paypal_checkout', order_number=order.order_number)
    else:
        return redirect('payment:mercadopago_checkout', order_number=order.order_number)
